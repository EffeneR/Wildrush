"""WILDRUSH UI / announcer cues (mono, 2D). Musical, crisp and short; the match-state cues are
designed to be mutually distinct:

  zone_activate   brassy open-fifth horn swell (D4/A4/D5), ~1.4 s
  zone_reveal     soft ascending 2-note marimba chime (E5 -> B5)
  zone_ally       bright ascending major arpeggio (C) + warm pad  -> positive
  zone_enemy      low tritone/minor-9th brass stab bending down    -> tense
  zone_contested  6 fast alternating square-wave pulses A5/F5      -> pulsing alert
  score_warning_n bell motif with 2 / 3 / 4 rising notes, faster and brighter per level
"""
from __future__ import annotations

import numpy as np

from dsp import (TWO_PI, add_reverb, db2a, env_ad, env_pts, fade_edges, fm_tone, glide, hp, hz, lp, mix_at, ns,
                 osc_sine, osc_square, osc_tri, rng_for, synth_ir, tvec, white)
from instruments import (bell, brass, clap, crash, epiano, fm_pluck, glass, marimba, nrm, reverse_swell, riser,
                         saw_pad, sub_boom, taiko, timpani)

REGISTRY: dict = {}


def cue(name):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


def mk(dur):
    return np.zeros(ns(dur))


def put(out, x, t, gain_db=0.0):
    mix_at(out, x, ns(t) if t > 0 else 0, float(db2a(gain_db)))


def verb(x, t60=1.2, wet=0.2, key="ui_ir"):
    ir = synth_ir(rng_for(key, t60), t60=t60, stereo=False, predelay=0.012)
    return add_reverb(x, ir, wet=wet)


def click(rng, dur=0.004, lo=2500.0):
    n = ns(dur)
    return nrm(hp(white(n, rng), lo, 2) * env_ad(n, 0.0001, dur / 4))


def blip(f, dur, tau, harm=0.15, attack=0.001):
    n = ns(dur)
    y = osc_sine(f, n) + harm * osc_sine(2 * f, n)
    return fade_edges(y * env_ad(n, attack, tau), 0.0, 0.2 * dur)


# --------------------------------------------------------------------------- zone / score (essential)
@cue("zone_activate")
def zone_activate(v, rng):
    out = mk(2.2)
    put(out, brass([hz("D4"), hz("A4"), hz("D5")], 1.0, rng, attack=0.08, release=0.45,
                   bright=(500.0, 3200.0, 1800.0)), 0.0, 0)
    put(out, timpani(rng, hz("D2"), 1.2), 0.0, -8)
    put(out, bell(hz("A5"), 1.2, tau=0.5, bright=0.6), 0.02, -16)
    return verb(out, 1.4, 0.22, "zone_act")


@cue("zone_reveal")
def zone_reveal(v, rng):
    out = mk(1.6)
    put(out, marimba(hz("E5"), 0.9, tau=0.35), 0.0, 0)
    put(out, marimba(hz("B5"), 1.0, tau=0.4), 0.18, -1)
    put(out, bell(hz("B6"), 0.9, tau=0.35, bright=0.3), 0.18, -18)
    return verb(out, 1.2, 0.2, "zone_rev")


@cue("zone_ally")
def zone_ally(v, rng):
    out = mk(1.9)
    for k, note in enumerate(["C5", "E5", "G5", "C6"]):
        put(out, fm_pluck(hz(note), 0.7, index=2.0, ratio=2.0, decay=0.35), 0.06 * k, -1.5 * (k < 3))
    put(out, bell(hz("C6"), 1.2, tau=0.5, bright=0.5), 0.18, -8)
    put(out, saw_pad([hz("C4"), hz("E4"), hz("G4")], 0.7, rng, cutoff=1800, attack=0.12, release=0.5,
                     stereo=False), 0.0, -9)
    return verb(out, 1.2, 0.18, "zone_ally")


@cue("zone_enemy")
def zone_enemy(v, rng):
    out = mk(1.9)
    bend = lambda t: -90.0 * np.clip((t - 0.15) / 0.5, 0, 1)
    put(out, brass([hz("C3"), hz("F#3"), hz("C#4")], 0.75, rng, attack=0.03, release=0.4,
                   bright=(900.0, 2600.0, 1100.0), bend=bend, vib_depth=0.0), 0.0, 0)
    put(out, taiko(rng, 70.0, 0.9), 0.0, -6)
    put(out, bell(hz("F#5"), 1.0, tau=0.4, bright=0.8), 0.02, -15)
    put(out, bell(hz("G5"), 1.0, tau=0.4, bright=0.8), 0.02, -15)
    return verb(out, 1.2, 0.18, "zone_enemy")


@cue("zone_contested")
def zone_contested(v, rng):
    out = mk(0.9)
    period = 0.11
    for k in range(6):
        f = hz("A5") if k % 2 == 0 else hz("F5")
        n = ns(0.075)
        tone = osc_square(f, n, 0.0, duty=0.4) * 0.6 + osc_sine(f, n)
        tone = lp(tone, 3500.0, 2) * env_pts(n, [(0, 0), (0.003, 1), (0.05, 0.8), (0.075, 0)])
        put(out, nrm(tone), k * period, 0)
        m = ns(0.07)
        low = lp(osc_square(hz("A3"), m, 0.0), 1200.0, 2) * env_pts(m, [(0, 0), (0.004, 1), (0.07, 0)])
        put(out, nrm(low), k * period, -10)
    return verb(out, 0.6, 0.1, "zone_cont")


def _score_warning(level, rng):
    notes = [["C5", "G5"], ["D5", "A5", "D6"], ["E5", "B5", "E6", "B6"]][level - 1]
    step = [0.17, 0.13, 0.1][level - 1]
    bright = [0.4, 0.8, 1.2][level - 1]
    out = mk(1.8)
    for k, note in enumerate(notes):
        n = ns(0.6)
        t = tvec(n)
        tone = fm_tone(hz(note), n, 3.0, (0.4 + bright) * np.exp(-t / 0.05)) * env_ad(n, 0.002, 0.22)
        tone += 0.5 * osc_tri(hz(note), n) * env_ad(n, 0.002, 0.18)
        put(out, nrm(fade_edges(tone, 0.0, 0.1)), step * k, -1.0 * (k != len(notes) - 1))
        if level >= 2:
            m = ns(0.12)
            low = osc_sine(hz(notes[0]) / 4, m) * env_ad(m, 0.002, 0.04)
            put(out, nrm(low), step * k, -9)
    if level == 3:
        n = ns(0.55)
        t = tvec(n)
        sus = osc_tri(hz("B6"), n) * (0.6 + 0.4 * np.sin(TWO_PI * 12 * t)) * env_pts(n, [(0, 0), (0.02, 1), (0.55, 0)])
        put(out, nrm(sus), step * 3 + 0.05, -8)
        put(out, taiko(rng, 80.0, 0.6), 0.0, -8)
    return verb(out, 0.9, 0.15, f"sw{level}")


@cue("score_warning_1")
def score_warning_1(v, rng):
    return _score_warning(1, rng)


@cue("score_warning_2")
def score_warning_2(v, rng):
    return _score_warning(2, rng)


@cue("score_warning_3")
def score_warning_3(v, rng):
    return _score_warning(3, rng)


# --------------------------------------------------------------------------- match flow
@cue("countdown_tick")
def countdown_tick(v, rng):
    out = mk(0.25)
    put(out, blip(hz("C6"), 0.22, 0.05, harm=0.2), 0.0, 0)
    put(out, click(rng), 0.0, -12)
    return out


@cue("countdown_go")
def countdown_go(v, rng):
    out = mk(1.5)
    put(out, brass([hz("C5"), hz("E5"), hz("G5"), hz("C6")], 0.45, rng, attack=0.015, release=0.35,
                   bright=(2500.0, 5000.0, 2600.0), vib_depth=0.0, scoop=0.0), 0.0, 0)
    put(out, bell(hz("C7"), 0.9, tau=0.35, bright=0.4), 0.0, -12)
    put(out, blip(hz("C6"), 0.3, 0.08, harm=0.3), 0.0, -6)
    put(out, taiko(rng, 90.0, 0.6), 0.0, -8)
    return verb(out, 1.0, 0.18, "go")


@cue("rotation_tick")
def rotation_tick(v, rng):
    """Wood-block tick (distinct from the tonal countdown beep)."""
    from sfx import knock
    return knock(rng, 0.14, [(1250.0, 0.03, 1.0), (3120.0, 0.012, 0.4), (4700.0, 0.006, 0.15)],
                 exc_tau=0.0005, exc_lp=7000.0)


@cue("victory")
def victory(v, rng):
    out = mk(4.4)
    put(out, timpani(rng, hz("D2"), 1.4), 0.0, -3)
    put(out, brass([hz("D4"), hz("F#4"), hz("A4"), hz("D5")], 0.9, rng, attack=0.05, release=0.3), 0.0, -1)
    for k, note in enumerate(["D5", "F#5", "A5", "D6"]):
        put(out, fm_pluck(hz(note), 0.7, index=1.8, decay=0.3), 0.7 + 0.08 * k, -8)
    put(out, brass([hz("D4"), hz("G4"), hz("B4"), hz("D5")], 0.55, rng, attack=0.04, release=0.25), 1.05, -2)
    put(out, reverse_swell(rng, 0.5), 1.25, -18)
    put(out, timpani(rng, hz("A1"), 1.2), 1.75, -5)
    put(out, brass([hz("D4"), hz("A4"), hz("E5"), hz("F#5")], 1.1, rng, attack=0.05, release=0.6,
                   bright=(800.0, 3400.0, 2000.0)), 1.75, 0)
    put(out, crash(rng, 2.0, tau=0.6), 1.75, -17)
    put(out, bell(hz("D6"), 1.6, tau=0.6, bright=0.5), 1.75, -12)
    return verb(out, 1.8, 0.22, "victory")


@cue("defeat")
def defeat(v, rng):
    out = mk(4.2)
    chords = [(["D3", "F3", "A3", "D4"], 0.0), (["Bb2", "D3", "F3", "Bb3"], 0.75),
              (["G2", "D3", "Bb3", "E4"], 1.5), (["D3", "A3", "E4", "F4"], 2.25)]
    for notes, t0 in chords:
        for k, nt in enumerate(notes):
            put(out, epiano(hz(nt), 0.9 if t0 < 2 else 1.3, vel=0.55, decay=1.1), t0 + 0.012 * k, -2)
    put(out, saw_pad([hz("D3"), hz("A3"), hz("F4")], 2.6, rng, cutoff=900, attack=0.8, release=0.9,
                     stereo=False), 0.0, -12)
    return verb(out, 1.8, 0.25, "defeat")


@cue("sudden_death")
def sudden_death(v, rng):
    out = mk(4.2)
    put(out, taiko(rng, 58.0, 1.1), 0.0, 0)
    put(out, taiko(rng, 58.0, 1.1), 0.42, -2)
    bend = lambda t: 220.0 * np.clip(t / 1.9, 0, 1) ** 1.5
    br = brass([hz("C3"), hz("Db3"), hz("Gb3"), hz("C4")], 1.9, rng, attack=1.2, release=0.25,
               bright=(400.0, 2600.0, 2600.0), bend=bend, vib_depth=0.0, scoop=0.0)
    put(out, br, 0.2, -3)
    put(out, riser(rng, 1.9, 300.0, 5000.0), 0.2, -13)
    put(out, taiko(rng, 52.0, 1.2), 2.2, 1)
    put(out, sub_boom(1.4, 60.0, 40.0), 2.2, -4)
    put(out, bell(hz("C#6"), 1.3, tau=0.5, bright=1.0), 2.2, -14)
    put(out, bell(hz("G6"), 1.3, tau=0.5, bright=1.0), 2.2, -16)
    return verb(out, 1.6, 0.2, "sudden")


# --------------------------------------------------------------------------- menus
@cue("ui_hover")
def ui_hover(v, rng):
    out = mk(0.05)
    put(out, blip(2637.0, 0.04, 0.008, harm=0.0), 0.0, 0)
    put(out, click(rng, 0.003, 4000.0), 0.0, -10)
    return out


@cue("ui_select")
def ui_select(v, rng):
    out = mk(0.2)
    for k, f in enumerate((hz("E6"), hz("A6"))):
        n = ns(0.1)
        t = tvec(n)
        tone = fm_tone(f, n, 2.0, 0.8 * np.exp(-t / 0.02)) * env_ad(n, 0.001, 0.035)
        put(out, nrm(fade_edges(tone, 0, 0.02)), 0.045 * k, -1.0 * (k == 0))
    put(out, click(rng), 0.0, -12)
    return out


@cue("ui_back")
def ui_back(v, rng):
    out = mk(0.2)
    put(out, blip(hz("E6"), 0.09, 0.03, harm=0.1), 0.0, 0)
    put(out, blip(hz("B5"), 0.12, 0.035, harm=0.1), 0.05, -2)
    return out


@cue("ui_error")
def ui_error(v, rng):
    out = mk(0.3)
    for k in range(2):
        n = ns(0.09)
        tone = osc_square(220.0, n, 0.0) + osc_square(233.1, n, 0.3)
        tone = lp(tone, 1500.0, 2) * env_pts(n, [(0, 0), (0.004, 1), (0.065, 0.9), (0.09, 0)])
        put(out, nrm(tone), 0.13 * k, 0)
    return out


@cue("ui_lockin")
def ui_lockin(v, rng):
    from sfx import knock, thud
    out = mk(0.75)
    put(out, knock(rng, 0.08, [(950.0, 0.018, 1.0), (2150.0, 0.012, 0.6), (3300.0, 0.007, 0.3)],
                   exc_tau=0.0006, exc_lp=8000.0), 0.0, 0)
    put(out, thud(rng, 0.12, 150.0, 90.0, 0.01, 0.025, noise=0.5, noise_lp=800.0), 0.0, -5)
    for k, note in enumerate(["C6", "E6", "G6"]):
        put(out, bell(hz(note), 0.55, tau=0.22, bright=0.7), 0.02 + 0.012 * k, -6)
    return verb(out, 0.8, 0.15, "lockin")


@cue("ui_ready")
def ui_ready(v, rng):
    out = mk(0.5)
    for k, note in enumerate(["G5", "B5", "D6"]):
        put(out, bell(hz(note), 0.4, tau=0.13, bright=0.6), 0.015 * k, 0)
    put(out, click(rng), 0.0, -12)
    return out


@cue("ui_match_found")
def ui_match_found(v, rng):
    out = mk(2.0)
    for k, note in enumerate(["A4", "C#5", "E5", "A5", "E6"]):
        put(out, fm_pluck(hz(note), 0.8, index=2.2, ratio=2.0, decay=0.4), 0.055 * k, -1)
    put(out, saw_pad([hz("A3"), hz("E4"), hz("A4"), hz("C#5")], 1.1, rng, cutoff=2000, attack=0.15, release=0.6,
                     stereo=False), 0.0, -8)
    n = ns(0.6)
    put(out, nrm(hp(white(n, rng), 6000, 2) * env_pts(n, [(0, 0), (0.3, 1), (0.6, 0)])), 0.1, -22)
    put(out, bell(hz("A6"), 1.0, tau=0.4, bright=0.4), 0.22, -14)
    return verb(out, 1.3, 0.2, "match_found")


@cue("ui_notify")
def ui_notify(v, rng):
    out = mk(0.8)
    put(out, bell(hz("B5"), 0.6, tau=0.25, bright=0.5, attack=0.003), 0.0, -1)
    put(out, bell(hz("E6"), 0.7, tau=0.3, bright=0.5, attack=0.003), 0.11, 0)
    return verb(out, 0.9, 0.12, "notify")


@cue("ui_chat")
def ui_chat(v, rng):
    out = mk(0.16)
    n = ns(0.07)
    put(out, nrm(osc_sine(glide(n, 1700.0, 1800.0, 0.02), n) * env_ad(n, 0.002, 0.02)), 0.0, 0)
    put(out, blip(2217.0, 0.06, 0.018, harm=0.0), 0.06, -6)
    return out


@cue("ui_ping")
def ui_ping(v, rng):
    out = mk(0.75)
    n = ns(0.35)
    t = tvec(n)
    f = 880.0 * 2 ** np.clip(t / 0.05, 0, 1)
    tone = osc_sine(f, n) + 0.2 * osc_sine(2 * f, n)
    tone = nrm(tone * env_pts(n, [(0, 0), (0.004, 1), (0.06, 0.8), (0.35, 0)]))
    for k, g in enumerate((0, -9, -18)):
        put(out, tone, 0.16 * k, g)
    return out
