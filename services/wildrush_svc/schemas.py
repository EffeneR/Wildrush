"""Request bodies (pydantic v2). Unknown fields are rejected (422) everywhere."""

from __future__ import annotations

import ipaddress
import re
import uuid
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from .mastery import ALL_BADGES

# --- shared field types ------------------------------------------------------------------

Username = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{3,16}$")]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Region = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{2,20}$")]
FighterName = Literal["nyx", "bruno", "vex", "hops", "scrap"]
PaletteName = Literal["default", "dusk", "ember", "frost"]
BadgeName = Literal[ALL_BADGES]  # type: ignore[valid-type]
TeamIndex = Annotated[StrictInt, Field(ge=0, le=1)]
Port = Annotated[StrictInt, Field(ge=1, le=65535)]

_HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)


def _display_name(value: str) -> str:
    value = value.strip()
    if not 3 <= len(value) <= 20:
        raise ValueError("display_name must be 3..20 characters")
    if not value.isprintable():
        raise ValueError("display_name must contain printable characters only")
    return value


def _host(value: str) -> str:
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if not _HOSTNAME_RE.fullmatch(value):
        raise ValueError("host must be a hostname or IP address")
    return value


def _printable_text(value: str) -> str:
    if not value.isprintable():
        raise ValueError("must contain printable characters only")
    return value


DisplayName = Annotated[str, StringConstraints(max_length=64), AfterValidator(_display_name)]
HostName = Annotated[str, StringConstraints(min_length=1, max_length=253), AfterValidator(_host)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyBody(Body):
    pass


# --- accounts ------------------------------------------------------------------------------

class RegisterReq(Body):
    username: Username
    password: Password
    display_name: DisplayName | None = None


class LoginReq(Body):
    username: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


# --- profile ----------------------------------------------------------------------------

class ProfilePatchReq(Body):
    display_name: DisplayName | None = None
    selected_badge: BadgeName | None = None
    selected_palettes: Annotated[dict[FighterName, PaletteName], Field(max_length=5)] | None = None

    @model_validator(mode="after")
    def _no_null_display_name(self) -> ProfilePatchReq:
        if "display_name" in self.model_fields_set and self.display_name is None:
            raise ValueError("display_name cannot be null")
        if "selected_palettes" in self.model_fields_set and self.selected_palettes is None:
            raise ValueError("selected_palettes cannot be null")
        return self


# --- parties ------------------------------------------------------------------------------

class InviteReq(Body):
    username: Username


class AccountRefReq(Body):
    account_id: uuid.UUID


# --- queue --------------------------------------------------------------------------------

class QueueJoinReq(Body):
    mode: Literal["casual", "ranked"]
    roster_prefs: Annotated[list[FighterName], Field(max_length=5)] = Field(default_factory=list)
    region: Region
    latency_ms: Annotated[
        dict[Region, Annotated[StrictInt, Field(ge=0, le=10000)]], Field(max_length=32)
    ] = Field(default_factory=dict)
    allow_bots: StrictBool = False

    @field_validator("roster_prefs")
    @classmethod
    def _unique_prefs(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("roster_prefs must be unique")
        return v


# --- private matches ---------------------------------------------------------------------

class PrivateCreateReq(Body):
    region: Region


class PrivateJoinReq(Body):
    join_code: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9]{8}$")]
    role: Literal["player", "observer"] = "player"


# --- servers / allocator -----------------------------------------------------------------

class HeartbeatMatch(Body):
    match_id: uuid.UUID
    port: Port
    players: Annotated[StrictInt, Field(ge=0, le=64)]
    state: Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,20}$")]


class HeartbeatReq(Body):
    name: Annotated[str, StringConstraints(min_length=1, max_length=64), AfterValidator(_printable_text)]
    region: Region
    host: HostName
    port_min: Annotated[StrictInt, Field(ge=1024, le=65535)]
    port_max: Annotated[StrictInt, Field(ge=1024, le=65535)]
    capacity: Annotated[StrictInt, Field(ge=0, le=256)]
    build_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._+-]{1,64}$")]
    protocol: Annotated[StrictInt, Field(ge=0, le=1_000_000)]
    status: Literal["online", "draining"]
    matches: Annotated[list[HeartbeatMatch], Field(max_length=256)] = Field(default_factory=list)

    @model_validator(mode="after")
    def _port_range(self) -> HeartbeatReq:
        if self.port_min > self.port_max:
            raise ValueError("port_min must be <= port_max")
        if self.port_max - self.port_min > 1000:
            raise ValueError("port range may span at most 1001 ports")
        return self


class PollReq(Body):
    free_ports: Annotated[list[Port], Field(max_length=1001)] = Field(default_factory=list)


class AllocationStartedReq(Body):
    allocation_id: uuid.UUID
    match_id: uuid.UUID
    port: Port
    pid: Annotated[StrictInt, Field(ge=1, le=2**31 - 1)]


class AllocationEndedReq(Body):
    allocation_id: uuid.UUID
    match_id: uuid.UUID
    exit_code: Annotated[StrictInt, Field(ge=-1000, le=1000)]
    reason: Annotated[str, StringConstraints(max_length=200), AfterValidator(_printable_text)] = ""


class RedeemReq(Body):
    ticket_id: uuid.UUID
    match_id: uuid.UUID


# --- results -------------------------------------------------------------------------------

class ResultPlayer(Body):
    account_id: uuid.UUID
    team: TeamIndex
    fighter: FighterName
    kos: Annotated[StrictInt, Field(ge=0, le=10000)]
    knocked_out: Annotated[StrictInt, Field(ge=0, le=10000)]
    damage_dealt: Annotated[StrictFloat, Field(ge=0, le=1e7, allow_inf_nan=False)]
    control_seconds: Annotated[StrictFloat, Field(ge=0, le=86400, allow_inf_nan=False)]
    abandoned: StrictBool
    afk: StrictBool


class ResultBot(Body):
    team: TeamIndex
    fighter: FighterName


class ResultReq(Body):
    match_id: uuid.UUID
    winner_team: TeamIndex
    score: Annotated[list[Annotated[StrictInt, Field(ge=0, le=100000)]], Field(min_length=2, max_length=2)]
    duration_s: Annotated[StrictFloat, Field(ge=0, le=86400, allow_inf_nan=False)]
    sudden_death: StrictBool
    ended_reason: Literal["score_limit", "time", "sudden_death", "forfeit"]
    players: Annotated[list[ResultPlayer], Field(min_length=1, max_length=10)]
    bots: Annotated[list[ResultBot], Field(max_length=10)] = Field(default_factory=list)
    replay_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")] | None = None

    def canonical(self) -> dict[str, Any]:
        """Normalized form used for idempotency comparison and storage: key order,
        number formatting and the order of the players/bots lists do not matter."""
        data = self.model_dump(mode="json")
        data["players"] = sorted(data["players"], key=lambda p: p["account_id"])
        data["bots"] = sorted(data["bots"], key=lambda b: (b["team"], b["fighter"]))
        return data
