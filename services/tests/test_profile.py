"""Profile, cosmetics unlock validation, mastery math."""

from __future__ import annotations

from sqlalchemy import update

from helpers import ctx_of, make_account
from wildrush_svc import mastery
from wildrush_svc.models import FighterMastery


def set_xp(app, acct, fighter: str, xp: int) -> None:
    with ctx_of(app).tx() as db:
        db.execute(
            update(FighterMastery)
            .where(FighterMastery.account_id == acct.id, FighterMastery.fighter == fighter)
            .values(xp=xp)
        )


def test_default_profile(client, app):
    acct = make_account(app, "Fresh")
    p = client.get("/v1/profile", headers=acct.headers).json()
    assert p["display_name"] == "Fresh" and p["selected_badge"] is None and p["badges"] == []
    assert list(p["fighters"]) == ["nyx", "bruno", "vex", "hops", "scrap"]
    for f in p["fighters"].values():
        assert f["xp"] == 0 and f["level"] == 1 and f["palettes"] == ["default"] and f["selected_palette"] == "default"


def test_patch_display_name_and_locked_cosmetics(client, app):
    acct = make_account(app, "Painter")
    r = client.patch("/v1/profile", json={"display_name": "Paint Brush"}, headers=acct.headers)
    assert r.status_code == 200 and r.json()["display_name"] == "Paint Brush"

    r = client.patch("/v1/profile", json={"selected_palettes": {"nyx": "dusk"}}, headers=acct.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_unlocked"
    r = client.patch("/v1/profile", json={"selected_badge": "nyx_initiate"}, headers=acct.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_unlocked"

    # unknown names / fighters / nulls are validation errors
    for body in (
        {"selected_palettes": {"nyx": "gold"}},
        {"selected_palettes": {"wolf": "dusk"}},
        {"selected_badge": "wolf_master"},
        {"display_name": None},
        {"display_name": "x"},
        {"nickname": "x"},
    ):
        r = client.patch("/v1/profile", json=body, headers=acct.headers)
        assert r.status_code == 422, (body, r.text)


def test_palettes_unlock_by_level_all_or_nothing(client, app):
    acct = make_account(app, "Leveled")
    set_xp(app, acct, "vex", 2400)  # level 5 -> default, dusk, ember
    p = client.get("/v1/profile", headers=acct.headers).json()["fighters"]["vex"]
    assert p["level"] == 5 and p["palettes"] == ["default", "dusk", "ember"]
    r = client.patch("/v1/profile", json={"selected_palettes": {"vex": "ember"}}, headers=acct.headers)
    assert r.status_code == 200 and r.json()["fighters"]["vex"]["selected_palette"] == "ember"
    # one locked entry rejects the whole patch
    r = client.patch("/v1/profile", json={"selected_palettes": {"vex": "dusk", "nyx": "frost"}}, headers=acct.headers)
    assert r.status_code == 409
    assert client.get("/v1/profile", headers=acct.headers).json()["fighters"]["vex"]["selected_palette"] == "ember"


def test_badge_selection_requires_unlock(client, app):
    from wildrush_svc.models import AccountBadge

    acct = make_account(app, "Badger")
    with ctx_of(app).tx() as db:
        db.add(AccountBadge(account_id=acct.id, badge="pack_debut", unlocked_at=ctx_of(app).clock.now(), match_id=None))
    r = client.patch("/v1/profile", json={"selected_badge": "pack_debut"}, headers=acct.headers)
    assert r.status_code == 200 and r.json()["selected_badge"] == "pack_debut"
    r = client.patch("/v1/profile", json={"selected_badge": None}, headers=acct.headers)
    assert r.status_code == 200 and r.json()["selected_badge"] is None


def test_mastery_math():
    assert [mastery.level_for_xp(x) for x in (0, 299, 300, 799, 800, 9999, 10000, 50000)] == [1, 1, 2, 2, 3, 9, 10, 10]
    # 100 base + 50 win + min(2*61, 200) + min(10*4, 100) = 312
    assert mastery.match_xp(won=True, control_seconds=61.9, kos=4, private=False, abandoned=False, afk=False) == 312
    # caps: control 2*150=300 -> 200, kos 10*20=200 -> 100
    assert mastery.match_xp(won=False, control_seconds=150, kos=20, private=False, abandoned=False, afk=False) == 400
    assert mastery.match_xp(won=True, control_seconds=61, kos=4, private=True, abandoned=False, afk=False) == 156
    assert mastery.match_xp(won=True, control_seconds=61, kos=4, private=False, abandoned=True, afk=False) == 0
    assert mastery.unlocked_palettes(7) == ["default", "dusk", "ember", "frost"]
    assert mastery.fighter_badges_for_level("hops", 6) == ["hops_initiate", "hops_adept", "hops_veteran"]
    assert len(mastery.ALL_BADGES) == 21
