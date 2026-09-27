"""WILDRUSH positional SFX generators (mono). Every sound is synthesized from noise, oscillators,
resonators and envelopes - no samples. Each generator is ``fn(v, rng) -> mono float array`` where
``v`` is the 0-based variation index; levels are normalised later by build.py.

Design notes (see docs/AUDIO_CONTRACT.md):
* impacts are padded thumps + small snaps (no gore); guard is a dull forearm "thock" (modal
  wood-like knock with short decays - never metallic ringing);
* the essential cues occupy distinct spectral/temporal regions:
    hit_light   short 120-250 Hz padded thump + 2.5-4 kHz snap (~0.15 s)
    hit_heavy   55-150 Hz deep thump + 0.9-4 kHz resonant crack (~0.3 s)
    guard_block 300/700/1200 Hz hollow knock + 1.7-3 kHz slide (~0.2 s)
    guard_break multi-click crack + 1.1 kHz -> 0.2 kHz descending tone (~0.8 s)
    parry       1.8-10 kHz bright inharmonic ring + upward flash (~0.8 s)
    knockout    soft 55-95 Hz thud + descending two-note chime (~1.4 s)
"""
from __future__ import annotations

import numpy as np

from dsp import (SR, TWO_PI, band_gain, bp, curve, db2a, env_ad, fade_edges, env_pts, env_swell, glide, harmonic_tone,
                 hp, hz, impulses, lp, mix_at, modal_bank, modal_sines, ns, osc_saw, osc_sine, resonator,
                 softclip, stft_shape, synth_ir, add_reverb, tvec, white, rng_for)

REGISTRY: dict = {}


def cue(name):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


# --------------------------------------------------------------------------- helpers
def nrm(x):
    p = float(np.max(np.abs(x))) if len(x) else 0.0
    return x / p if p > 0 else x


def mk(dur):
    return np.zeros(ns(dur))


def put(out, x, t, gain_db=0.0):
    mix_at(out, x, ns(t) if t > 0 else 0, float(db2a(gain_db)))


def pick(v, seq):
    return seq[v % len(seq)]


def thud(rng, dur, f0, f1, pitch_tau, amp_tau, attack=0.001, noise=0.4, noise_lp=500.0, drive=0.0):
    """Padded low body thump: pitch-dropping sine + low-passed noise puff."""
    n = ns(dur)
    f = glide(n, f0, f1, pitch_tau)
    body = osc_sine(f, n) * env_ad(n, attack, amp_tau)
    if noise > 0:
        nz = lp(white(n, rng), noise_lp, 2)
        nz = nz / (np.std(nz) + 1e-12) * 0.5
        body = body + noise * nz * env_ad(n, attack, amp_tau * 0.55)
    body = nrm(body)
    if drive > 0:
        body = nrm(softclip(body, drive))
    return fade_edges(body, 0.0, 0.15 * dur)


def snap(rng, dur, fc, tau=0.003, bw_oct=1.0, attack=0.0002):
    """Short band-limited click (fabric/air snap, small crack)."""
    n = ns(dur)
    lo, hi = fc / 2 ** (bw_oct / 2), fc * 2 ** (bw_oct / 2)
    return fade_edges(nrm(bp(white(n, rng), lo, hi, 2) * env_ad(n, attack, tau)), 0.0, 0.2 * dur)


def whoosh(rng, dur, fc_pts, fc_vals, bw=1.0, peak=0.4, rise=2.0, fall=1.6, env=None, whistle=0.0,
           nfft=512, air=0.0):
    """Air movement: white noise through a moving log-Gaussian band (STFT shaped) + swell envelope.
    ``fc_pts`` are fractions of the duration; ``whistle`` adds a narrow resonant band on top."""
    n = ns(dur)
    fcf = curve(np.asarray(fc_pts, dtype=float) * dur, fc_vals, log=True)
    bwf = (lambda t: bw) if np.isscalar(bw) else curve(np.asarray(bw[0]) * dur, bw[1])
    y = stft_shape(white(n, rng), lambda f, t: band_gain(f, fcf(t), bwf(t)), nfft=nfft, hop=nfft // 4)
    e = env if env is not None else env_swell(n, peak, rise, fall)
    y = nrm(y) * e
    if whistle > 0:
        w = stft_shape(white(n, rng), lambda f, t: band_gain(f, fcf(t) * 1.15, 0.09), nfft=1024, hop=256)
        y = y + whistle * nrm(w) * e
    if air > 0:  # low air-mass component
        a = lp(white(n, rng), 260.0, 2)
        y = y + air * nrm(a) * e
    return nrm(y)


def cloth(rng, dur, rate=140.0, fc=2200.0, bw=1.3, grain_tau=0.004, base=0.25, env=None):
    """Fabric rustle: band-passed noise gated by an irregular crackle envelope."""
    n = ns(dur)
    imp = np.abs(impulses(n, rng, rate, 0.6))
    k = ns(grain_tau * 6)
    am = np.convolve(imp, np.exp(-tvec(k) / grain_tau))[:n]
    am = am / (am.max() + 1e-12)
    lo, hi = fc / 2 ** (bw / 2), fc * 2 ** (bw / 2)
    y = bp(white(n, rng), lo, hi, 2) * (base + am)
    y = y * (env if env is not None else env_swell(n, 0.3, 1.5, 1.2))
    return nrm(y)


def flutter(rng, dur, rate=26.0, fc=1400.0, bw=1.4, depth=0.8):
    """Cloth flap: noise band with fast periodic amplitude flutter (jittered)."""
    n = ns(dur)
    t = tvec(n)
    jit = np.cumsum(rng.normal(0, 0.02, n)) / np.sqrt(n)
    am = (1 - depth) + depth * (0.5 + 0.5 * np.sin(TWO_PI * rate * t + 6 * jit)) ** 2
    lo, hi = fc / 2 ** (bw / 2), fc * 2 ** (bw / 2)
    return nrm(bp(white(n, rng), lo, hi, 2) * am * env_swell(n, 0.35, 1.3, 1.5))


def grit(rng, dur, rate=500.0, lo=2000.0, hi=7000.0, env=None):
    """Granular grit / scrape texture: dense random clicks, band-passed."""
    n = ns(dur)
    y = bp(impulses(n, rng, rate, 0.7), lo, hi, 4)  # 4th order: no HF tick leakage above the band
    if env is not None:
        y = y * env
    return fade_edges(nrm(y), 0.001, 0.1 * dur)


def knock(rng, dur, modes, exc_tau=0.0015, exc_lp=4000.0):
    """Resonator bank struck by a short noise burst (wood / hollow knock, plates)."""
    n = ns(dur)
    exc = lp(white(n, rng) * env_ad(n, 0.0002, exc_tau), exc_lp, 2)
    return fade_edges(nrm(modal_bank(exc, modes)), 0.0, 0.2 * dur)


def bubble(f0, dur, rise_oct=0.5, tau=None, attack=0.0005):
    """Minnaert-style bubble / droplet: sine with rising pitch and exponential decay."""
    n = ns(dur)
    t = tvec(n)
    f = f0 * 2 ** (rise_oct * t / dur)
    return fade_edges(osc_sine(f, n) * env_ad(n, attack, tau if tau else dur / 4), 0.0, 0.25 * dur)


def bell(f, dur, tau=0.6, bright=1.0, attack=0.002, chorus=0.3, ratios=None):
    """Soft bell / chime (mostly harmonic partials, gentle mallet attack)."""
    rs = ratios or [(1.0, 1.0, 1.0), (2.0, 0.34 * bright, 0.5), (3.0, 0.13 * bright, 0.3),
                    (4.2, 0.05 * bright, 0.18)]
    modes = [(f * r, tau * tm, a) for r, a, tm in rs]
    if chorus:
        modes.append((f * 1.0021, tau, chorus))
    return fade_edges(nrm(modal_sines(ns(dur), modes, attack=attack)), 0.0, min(0.35 * dur, 0.4))


def dust(rng, dur, attack=0.015, tau=0.09, lo=2200.0):
    n = ns(dur)
    return fade_edges(nrm(hp(white(n, rng), lo, 2) * env_ad(n, attack, tau)), 0.0, 0.2 * dur)


def glide_exp(n, f_start, f_end, dur_glide):
    """Exponential (log-linear) glide from f_start to f_end over dur_glide, then hold."""
    t = tvec(n)
    u = np.clip(t / dur_glide, 0.0, 1.0)
    return f_start * (f_end / f_start) ** u


# --------------------------------------------------------------------------- surfaces
def surf_stone(rng, pitch, weight):
    """Soft paw on stone. weight 0 = step, 1 = jump landing."""
    dur = 0.16 + 0.3 * weight
    out = mk(dur)
    body = thud(rng, 0.1 + 0.2 * weight, 175 * pitch * (1 - 0.3 * weight), 95 * pitch * (1 - 0.35 * weight),
                0.012 + 0.01 * weight, 0.02 + 0.035 * weight, attack=0.0015, noise=0.85 + 0.3 * weight,
                noise_lp=650 * pitch)
    put(out, body, 0.0)
    d2 = rng.uniform(0.018, 0.04) if weight < 0.5 else rng.uniform(0.012, 0.03)
    body2 = thud(rng, 0.08 + 0.1 * weight, 210 * pitch, 120 * pitch, 0.008, 0.012 + 0.02 * weight,
                 attack=0.001, noise=0.9, noise_lp=900)
    put(out, body2, d2, rng.uniform(-11, -7) + 6 * weight)
    g = grit(rng, 0.06, rate=900, lo=2500, hi=8000, env=env_ad(ns(0.06), 0.0005, 0.01))
    put(out, g, 0.002, rng.uniform(-25, -19))
    if weight > 0.5:
        put(out, dust(rng, 0.35, 0.012, 0.08), 0.01, -21)
        put(out, cloth(rng, 0.22, rate=110, fc=1900), 0.015, -22)
    elif rng.uniform() < 0.5:
        sc = bp(white(ns(0.05), rng), 1000, 4000, 2) * env_swell(ns(0.05), 0.4)
        put(out, nrm(sc), rng.uniform(0.02, 0.05), -24)
    return out


def surf_wood(rng, pitch, weight):
    """Hollow plank (bridge / dock)."""
    dur = 0.34 + 0.2 * weight
    out = mk(dur)
    p = pitch * (1 - 0.18 * weight)
    modes = [(185 * p, 0.045 + 0.03 * weight, 1.0), (395 * p * rng.uniform(0.97, 1.03), 0.035, 0.6),
             (690 * p, 0.03, 0.33), (1120 * p, 0.018, 0.18), (1850 * p, 0.01, 0.08)]
    put(out, knock(rng, dur, modes, exc_tau=0.002, exc_lp=2500), 0.0, 0)
    put(out, thud(rng, 0.14, 150 * p, 90 * p, 0.01, 0.025 + 0.02 * weight, attack=0.0015, noise=0.6,
                  noise_lp=700), 0.0, -3)
    d2 = rng.uniform(0.018, 0.04)
    put(out, knock(rng, 0.15, [(m[0] * 1.04, m[1] * 0.6, m[2]) for m in modes], exc_tau=0.0015, exc_lp=2000),
        d2, rng.uniform(-12, -8) + 5 * weight)
    put(out, knock(rng, 0.06, [(2400 * p, 0.008, 1.0), (3300 * p, 0.005, 0.5)], exc_tau=0.0004, exc_lp=6000),
        rng.uniform(0.05, 0.09), -24 + 4 * weight)
    if weight > 0.5:
        put(out, cloth(rng, 0.22, rate=110, fc=1900), 0.015, -20)
    return out


def surf_metal(rng, pitch, weight):
    """Grate / plate (loading platforms): thud + dull plate modes + small rattles."""
    dur = 0.4 + 0.2 * weight
    out = mk(dur)
    p = pitch * (1 - 0.1 * weight)
    base = 540 * p
    ratios = [1.0, 1.63, 2.27, 2.92, 3.79, 4.61]
    taus = [0.07, 0.055, 0.045, 0.035, 0.028, 0.02]
    amps = [1.0, 0.7, 0.5, 0.35, 0.25, 0.15]
    modes = [(base * r * rng.uniform(0.985, 1.015), t * (1 + 0.3 * weight), a) for r, t, a in zip(ratios, taus, amps)]
    plate = lp(knock(rng, dur, modes, exc_tau=0.0008, exc_lp=6000), 4500, 2)
    put(out, thud(rng, 0.12 + 0.1 * weight, 165 * p, 100 * p, 0.01, 0.02 + 0.025 * weight, noise=0.6,
                  noise_lp=800), 0.0, 0)
    put(out, nrm(plate), 0.0, -7 + 2 * weight)
    for k in range(int(rng.integers(2, 4)) + int(2 * weight)):
        r = rng.uniform(0.9, 1.15)
        put(out, knock(rng, 0.06, [(3100 * r, 0.012, 1.0), (4700 * r, 0.008, 0.6)], exc_tau=0.0003,
                       exc_lp=9000), rng.uniform(0.02, 0.09 + 0.1 * weight), rng.uniform(-20, -14))
    if weight > 0.5:
        put(out, cloth(rng, 0.22, rate=110, fc=1900), 0.015, -20)
    return out


def surf_wet(rng, pitch, weight):
    """Puddle splash-step."""
    dur = 0.26 + 0.3 * weight
    out = mk(dur)
    n = ns(0.2 + 0.2 * weight)
    put(out, thud(rng, 0.12 + 0.1 * weight, 150 * pitch, 90 * pitch, 0.01, 0.02 + 0.03 * weight, noise=0.7,
                  noise_lp=600), 0.0, -2)
    spl = bp(white(n, rng), 700, 6500, 2) * env_ad(n, 0.003, rng.uniform(0.035, 0.055) * (1 + weight))
    spl = stft_shape(spl, lambda f, t: band_gain(f, 2400 * np.exp(-t / 0.2) + 1200, 1.4, 0.25), nfft=512, hop=128)
    put(out, nrm(spl), 0.002, 0)
    put(out, snap(rng, 0.03, 3200 * pitch, tau=0.006, bw_oct=1.5), 0.0, -8)
    put(out, bubble(320 * pitch * rng.uniform(0.9, 1.1), 0.06, 0.7, 0.02), 0.01, -9)
    for k in range(int(rng.integers(3, 7)) + int(4 * weight)):
        put(out, bubble(rng.uniform(900, 3200), rng.uniform(0.02, 0.04), rng.uniform(0.3, 0.8)),
            rng.uniform(0.02, 0.15 + 0.15 * weight), rng.uniform(-20, -11))
    if weight > 0.5:
        put(out, thud(rng, 0.1, 170 * pitch, 110 * pitch, 0.01, 0.02, noise=0.8, noise_lp=700), 0.022, -6)
    return out


_STEP_PITCH = [1.0, 0.92, 1.08, 0.96, 1.05, 0.88]
_LAND_PITCH = [1.0, 0.9, 1.08]

for _name, _fn in (("stone", surf_stone), ("wood", surf_wood), ("metal", surf_metal), ("wet", surf_wet)):
    REGISTRY[f"foot_{_name}"] = (lambda fn: (lambda v, rng: fn(rng, pick(v, _STEP_PITCH), 0.0)))(_fn)
    REGISTRY[f"land_{_name}"] = (lambda fn: (lambda v, rng: fn(rng, pick(v, _LAND_PITCH), 1.0)))(_fn)


# --------------------------------------------------------------------------- movement
@cue("jump")
def jump(v, rng):
    p = pick(v, [1.0, 0.93, 1.07])
    out = mk(0.42)
    put(out, thud(rng, 0.1, 140 * p, 80 * p, 0.01, 0.02, noise=1.0, noise_lp=900), 0.0, -2)
    put(out, grit(rng, 0.05, 900, 2000, 7000, env_ad(ns(0.05), 0.0005, 0.012)), 0.0, -16)
    put(out, cloth(rng, 0.26, rate=150, fc=2100 * p), 0.02, -6)
    put(out, whoosh(rng, 0.3, [0, 0.5, 1], [500 * p, 1500 * p, 1100 * p], bw=1.0, peak=0.5), 0.03, -5)
    return out


@cue("dodge")
def dodge(v, rng):
    dur = pick(v, [0.26, 0.24, 0.3, 0.22])
    p = pick(v, [1.0, 1.1, 0.9, 1.05])
    out = mk(dur + 0.08)
    put(out, whoosh(rng, dur, [0, 0.4, 1], [380 * p, 1300 * p, 650 * p], bw=1.1, peak=0.4, rise=1.6, fall=1.4,
                    air=0.3), 0.0, 0)
    put(out, flutter(rng, 0.13, rate=pick(v, [24, 30, 21, 33]), fc=1500 * p), 0.03, -5)
    put(out, grit(rng, 0.05, 700, 1500, 6000, env_ad(ns(0.05), 0.001, 0.015)), 0.0, -16)
    return out


@cue("swing_light")
def swing_light(v, rng):
    dur = pick(v, [0.17, 0.15, 0.19, 0.16, 0.18])
    fc = pick(v, [(800, 2600, 1400), (950, 3000, 1600), (700, 2300, 1200), (1000, 3300, 1800), (850, 2800, 1300)])
    out = mk(dur + 0.03)
    put(out, whoosh(rng, dur, [0, 0.35, 1], fc, bw=0.9, peak=0.35, rise=1.4, fall=1.8, whistle=0.15), 0.0, 0)
    n = ns(dur * 0.6)
    claw = hp(white(n, rng), 5000, 2) * env_swell(n, 0.5, 1.5, 1.5)
    put(out, nrm(claw), dur * 0.2, -15)
    return out


@cue("swing_heavy")
def swing_heavy(v, rng):
    p = pick(v, [1.0, 0.9, 1.1])
    out = mk(0.68)
    put(out, cloth(rng, 0.2, rate=90, fc=1500 * p), 0.0, -10)
    n = ns(0.22)
    put(out, whoosh(rng, 0.22, [0, 1], [250 * p, 460 * p], bw=1.0,
                    env=env_pts(n, [(0, 0), (0.17, 0.85), (0.22, 0.0)]) ** 1.3), 0.0, -9)
    put(out, whoosh(rng, 0.44, [0, 0.4, 1], [260 * p, 900 * p, 380 * p], bw=1.3, peak=0.4, rise=1.8, fall=1.5,
                    whistle=0.1, air=0.55), 0.17, 0)
    return out


@cue("kick_whoosh")
def kick_whoosh(v, rng):
    p = pick(v, [1.0, 0.9, 1.1, 0.95])
    out = mk(0.3)
    put(out, whoosh(rng, 0.23, [0, 0.45, 1], [520 * p, 1700 * p, 850 * p], bw=1.0, peak=0.45, air=0.25), 0.0, 0)
    put(out, snap(rng, 0.03, 2400 * p, tau=0.004, bw_oct=1.2), pick(v, [0.17, 0.16, 0.18, 0.19]), -11)
    put(out, flutter(rng, 0.08, rate=30, fc=1800), 0.12, -14)
    return out


@cue("knock_skid")
def knock_skid(v, rng):
    dur = pick(v, [0.5, 0.45, 0.56])
    n = ns(dur)
    out = mk(dur + 0.05)
    e = env_pts(n, [(0, 0), (0.015, 1.0), (dur * 0.55, 0.8), (dur, 0.0)])
    scr = grit(rng, dur, rate=380, lo=900, hi=4200) * e
    band = stft_shape(white(n, rng), lambda f, t: band_gain(f, 2600 * np.exp(-t / (dur * 0.8)) + 900, 0.8),
                      nfft=512, hop=128) * e
    put(out, nrm(scr + 0.8 * nrm(band)), 0.0, 0)
    put(out, nrm(lp(white(n, rng), 250, 2) * e), 0.0, -5)
    put(out, dust(rng, dur, 0.04, 0.15), 0.02, -12)
    put(out, thud(rng, 0.1, 130, 80, 0.01, 0.02, noise=0.8, noise_lp=700), 0.0, -6)
    return out


@cue("body_fall")
def body_fall(v, rng):
    p = pick(v, [1.0, 0.92, 1.08])
    out = mk(0.5)
    put(out, thud(rng, 0.32, 110 * p, 55 * p, 0.02, 0.065, attack=0.002, noise=0.7, noise_lp=450, drive=1.2), 0.0)
    put(out, thud(rng, 0.15, 160 * p, 95 * p, 0.012, 0.03, attack=0.001, noise=0.8, noise_lp=700),
        pick(v, [0.08, 0.1, 0.07]), -7)
    put(out, cloth(rng, 0.3, rate=100, fc=1800), 0.0, -12)
    put(out, dust(rng, 0.35, 0.02, 0.1), 0.02, -18)
    return out


@cue("grab")
def grab(v, rng):
    p = pick(v, [1.0, 0.9])
    out = mk(0.22)
    put(out, cloth(rng, 0.14, rate=260, fc=2600 * p, bw=1.4, env=env_ad(ns(0.14), 0.005, 0.05)), 0.0, 0)
    put(out, thud(rng, 0.08, 180 * p, 130 * p, 0.006, 0.015, noise=0.9, noise_lp=1200), 0.004, -4)
    put(out, whoosh(rng, 0.05, [0, 1], [1300 * p, 2800 * p], bw=0.4, peak=0.6), 0.03, -8)
    return out


# --------------------------------------------------------------------------- hits / defence (essential)
@cue("hit_light")
def hit_light(v, rng):
    p = pick(v, [1.0, 0.93, 1.07, 0.97, 1.1])
    out = mk(0.2)
    put(out, thud(rng, 0.16, 230 * p, 125 * p, 0.008, 0.03, attack=0.0008, noise=0.5, noise_lp=900), 0.0, 0)
    n = ns(0.05)
    pap = bp(white(n, rng), 450, 1300, 2) * env_ad(n, 0.0003, 0.009)
    put(out, nrm(pap), 0.0, -5)
    put(out, snap(rng, 0.03, pick(v, [3200, 2800, 3600, 3000, 3400]), tau=0.0025, bw_oct=1.0), 0.001, -6)
    exc = np.zeros(ns(0.05))
    exc[0] = 1.0
    put(out, nrm(resonator(exc, pick(v, [1900, 2100, 1750, 2000, 2250]), 0.006)), 0.001, -12)
    return nrm(softclip(nrm(out), 1.3))


@cue("hit_heavy")
def hit_heavy(v, rng):
    p = pick(v, [1.0, 0.92, 1.06, 0.97])
    q = pick(v, [1.0, 1.08, 0.94, 1.03])
    out = mk(0.36)
    put(out, thud(rng, 0.34, 150 * p, 52 * p, 0.028, 0.085, attack=0.001, noise=0.45, noise_lp=380, drive=2.0), 0.0)
    n = ns(0.1)
    put(out, nrm(bp(white(n, rng), 250, 800, 2) * env_ad(n, 0.0005, 0.022)), 0.0, -7)
    crack_modes = [(900 * q, 0.016, 1.0), (1650 * q, 0.012, 0.7), (2750 * q, 0.009, 0.5), (4100 * q, 0.006, 0.3)]
    put(out, knock(rng, 0.12, crack_modes, exc_tau=0.0006, exc_lp=9000), 0.0005, -5)
    n = ns(0.04)
    put(out, nrm(hp(white(n, rng), 1500, 2) * env_ad(n, 0.0002, 0.005)), 0.0, -7)
    put(out, nrm(hp(white(n, rng), 2000, 2) * env_ad(n, 0.0002, 0.004)), pick(v, [0.008, 0.01, 0.007, 0.009]), -13)
    return nrm(softclip(nrm(out), 1.4))


@cue("guard_block")
def guard_block(v, rng):
    """Forearm deflect: dull wood-like 'thock' + short cloth slide. Deliberately NOT metallic:
    low modal frequencies, short decays, top end rolled off."""
    p = pick(v, [1.0, 0.94, 1.06, 0.9, 1.1])
    out = mk(0.24)
    modes = [(300 * p, 0.05, 1.0), (705 * p, 0.028, 0.55), (1180 * p, 0.016, 0.28), (1720 * p, 0.009, 0.12)]
    put(out, knock(rng, 0.24, modes, exc_tau=0.0012, exc_lp=3500), 0.0, 0)
    put(out, thud(rng, 0.12, 160 * p, 110 * p, 0.01, 0.022, attack=0.0008, noise=0.6, noise_lp=700), 0.0, -4)
    n = ns(0.14)
    sl = stft_shape(white(n, rng), lambda f, t: band_gain(f, 3000 * np.exp(-t / 0.12), 0.6), nfft=512, hop=128)
    sl = nrm(sl) * env_pts(n, [(0, 0), (0.012, 1), (0.05, 0.6), (0.14, 0)])
    put(out, nrm(sl), pick(v, [0.012, 0.015, 0.01, 0.018, 0.013]), -13)
    return nrm(lp(out, 6000, 2))


def _descending_tone(n, f_start, f_end, glide_dur, rng):
    f = glide_exp(n, f_start, f_end, glide_dur)
    t = tvec(n)
    vib = 1 + 0.012 * np.sin(TWO_PI * 11 * t) * np.exp(-t / 0.25)
    amps = [1.0, 0.35, 0.18, 0.08]
    a = harmonic_tone(f * vib, n, amps)
    b = harmonic_tone(f * vib * 0.985, n, amps)
    return nrm(a + 0.6 * b)


@cue("guard_break")
def guard_break(v, rng):
    p = pick(v, [1.0, 0.88])
    out = mk(0.85)
    times = np.array([0.0, 0.004, 0.011, 0.019]) + np.concatenate([[0], rng.uniform(-0.001, 0.001, 3)])
    for t0, g in zip(times, [0, -3, -5, -9]):
        n = ns(0.02)
        put(out, nrm(hp(white(n, rng), 1800, 2) * env_ad(n, 0.0001, 0.0025)), t0, g)
    put(out, knock(rng, 0.1, [(2300 * p, 0.02, 1.0), (3650 * p, 0.015, 0.7), (5200 * p, 0.01, 0.5)],
                   exc_tau=0.0005, exc_lp=10000), 0.001, -9)
    put(out, thud(rng, 0.25, 140, 60, 0.02, 0.06, attack=0.0008, noise=0.5, noise_lp=500), 0.0, -3)
    n = ns(0.72)
    tone = _descending_tone(n, 1150 * p, 210 * p, 0.46, rng)
    tone *= env_pts(n, [(0, 0), (0.006, 1), (0.3, 0.8), (0.72, 0)])
    put(out, nrm(tone), 0.012, -4)
    return out


@cue("parry")
def parry(v, rng):
    """Scrap's parry: precise bright inharmonic ring + upward 'flash'."""
    f0 = pick(v, [1760.0, 1975.5])
    out = mk(1.1)
    ring = modal_sines(ns(1.1), [(f0, 0.3, 1.0), (f0 * 1.0031, 0.3, 0.5), (f0 * 2.76, 0.14, 0.42),
                                  (f0 * 5.40, 0.07, 0.18), (f0 * 0.5, 0.2, 0.12)], attack=0.0006)
    put(out, nrm(ring), 0.002, 0)
    n = ns(0.04)
    ch = osc_sine(glide_exp(n, 2000, 7000, 0.025), n) * env_ad(n, 0.001, 0.01)
    put(out, nrm(ch), 0.0, -12)
    n = ns(0.06)
    put(out, nrm(hp(white(n, rng), 5000, 2) * env_ad(n, 0.0003, 0.012)), 0.0, -9)
    put(out, thud(rng, 0.06, 200, 140, 0.005, 0.012, noise=0.8, noise_lp=1200), 0.0, -9)
    return out


@cue("knockout")
def knockout(v, rng):
    """Soft thud + descending two-note chime (non-graphic)."""
    n1, n2 = pick(v, [("E5", "A4"), ("D5", "G4")])
    out = mk(2.0)
    put(out, thud(rng, 0.42, 95, 55, 0.02, 0.09, attack=0.004, noise=0.6, noise_lp=300), 0.0, 0)
    ch = mk(1.9)
    put(ch, bell(hz(n1), 1.2, tau=0.45), 0.0, 0)
    put(ch, bell(hz(n2), 1.3, tau=0.5), 0.23, 0)
    ch = add_reverb(ch, synth_ir(rng_for("ko_ir"), t60=0.9, stereo=False), wet=0.18)[: ns(1.9)]
    put(out, nrm(ch), 0.07, -3)
    return out


# --------------------------------------------------------------------------- Nyx
@cue("nyx_pounce_leap")
def nyx_pounce_leap(v, rng):
    p = pick(v, [1.0, 1.08])
    out = mk(0.5)
    put(out, thud(rng, 0.1, 150 * p, 90 * p, 0.01, 0.02, noise=1.0, noise_lp=900), 0.0, -2)
    put(out, grit(rng, 0.05, 900, 2000, 7000, env_ad(ns(0.05), 0.0005, 0.012)), 0.0, -14)
    put(out, whoosh(rng, 0.42, [0, 0.7, 1], [420 * p, 2300 * p, 1500 * p], bw=1.0, peak=0.65, rise=1.5, fall=2.5,
                    air=0.3), 0.02, 0)
    put(out, flutter(rng, 0.25, rate=28, fc=1700), 0.1, -9)
    return out


@cue("nyx_pounce_land")
def nyx_pounce_land(v, rng):
    p = pick(v, [1.0, 0.92])
    out = mk(0.34)
    put(out, thud(rng, 0.16, 170 * p, 95 * p, 0.01, 0.028, attack=0.0012, noise=0.8, noise_lp=800), 0.0, 0)
    put(out, thud(rng, 0.12, 190 * p, 110 * p, 0.008, 0.02, noise=0.9, noise_lp=900), 0.03, -6)
    n = ns(0.18)
    e = env_ad(n, 0.003, 0.05)
    scr = grit(rng, 0.18, 700, 2500, 7000, e)
    band = stft_shape(white(n, rng), lambda f, t: band_gain(f, 5000 * np.exp(-t / 0.15) + 1800, 0.6),
                      nfft=512, hop=128) * e
    put(out, nrm(scr + nrm(band)), 0.008, -5)
    return out


def _slash(rng, dur, fcs, bw=0.75):
    n = ns(dur)
    w = whoosh(rng, dur, [0, 0.3, 1], fcs, bw=bw, peak=0.3, rise=1.1, fall=1.8)
    top = hp(white(n, rng), 5500, 2) * env_swell(n, 0.3, 1.2, 2.0)
    return nrm(w + 0.3 * nrm(top))


@cue("nyx_crosscut")
def nyx_crosscut(v, rng):
    out = mk(0.4)
    s = pick(v, [1.0, 1.07])
    put(out, _slash(rng, 0.1, (1800 * s, 5200 * s, 3200 * s)), 0.0, 0)
    put(out, _slash(rng, 0.1, (3500 * s, 5600 * s, 2000 * s)), pick(v, [0.17, 0.19]), 0)
    return out


@cue("nyx_slip")
def nyx_slip(v, rng):
    p = pick(v, [1.0, 1.1])
    out = mk(0.24)
    put(out, whoosh(rng, 0.16, [0, 0.35, 1], [700 * p, 2100 * p, 1100 * p], bw=0.9, peak=0.35), 0.01, 0)
    put(out, grit(rng, 0.05, 900, 1800, 6500, env_ad(ns(0.05), 0.0005, 0.012)), 0.0, -9)
    put(out, thud(rng, 0.08, 190, 120, 0.008, 0.015, noise=0.9, noise_lp=900), 0.13, -10)
    return out


# --------------------------------------------------------------------------- Bruno
@cue("bruno_rush_start")
def bruno_rush_start(v, rng):
    p = pick(v, [1.0, 0.92])
    out = mk(0.48)
    put(out, thud(rng, 0.3, 120 * p, 48 * p, 0.02, 0.07, attack=0.0015, noise=0.8, noise_lp=500, drive=1.6), 0.0)
    put(out, grit(rng, 0.08, 800, 1500, 6000, env_ad(ns(0.08), 0.0005, 0.02)), 0.0, -12)
    put(out, dust(rng, 0.3, 0.015, 0.08), 0.01, -16)
    put(out, whoosh(rng, 0.36, [0, 0.8, 1], [220 * p, 650 * p, 500 * p], bw=1.2, peak=0.75, rise=1.3, fall=3.0,
                    air=0.5), 0.04, -4)
    put(out, cloth(rng, 0.25, rate=80, fc=1400), 0.05, -12)
    return out


@cue("bruno_rush_impact")
def bruno_rush_impact(v, rng):
    """Heavy shoulder impact: big padded whump, no sharp crack (differs from hit_heavy)."""
    p = pick(v, [1.0, 0.9])
    out = mk(0.48)
    put(out, thud(rng, 0.42, 125 * p, 44 * p, 0.03, 0.11, attack=0.0015, noise=0.6, noise_lp=350, drive=2.2), 0.0)
    n = ns(0.15)
    put(out, nrm(bp(white(n, rng), 220, 650, 2) * env_ad(n, 0.0008, 0.035)), 0.0, -6)
    put(out, knock(rng, 0.15, [(235 * p, 0.05, 1.0), (560 * p, 0.025, 0.4)], exc_tau=0.002, exc_lp=1800), 0.0, -7)
    put(out, cloth(rng, 0.12, rate=200, fc=1600, env=env_ad(ns(0.12), 0.002, 0.04)), 0.004, -10)
    return nrm(softclip(nrm(out), 1.3))


def _bark(rng, f_peak, f_end, dur, rough, fshift):
    """Synthesized dog bark ("woof"): harmonic glottal source with an explosive onset, a quick
    pitch rise then drop, strong jitter/shimmer and a subharmonic for the rough chaotic quality
    of real barks, breath noise, and dog-like formants (~17 cm tract) that close towards the end."""
    n = ns(dur)
    t = tvec(n)
    rise = 0.015
    f0 = np.where(t < rise, f_peak * (0.85 + 0.15 * t / rise),
                  f_end + (f_peak - f_end) * np.exp(-(t - rise) / (dur * 0.38)))
    jit = lp(white(n, rng), 120.0, 2)
    f0 = f0 * (1 + 0.045 * jit / (np.std(jit) + 1e-12))
    src = harmonic_tone(f0, n, [1.0 / k ** 1.0 for k in range(1, 48)])
    shim = lp(white(n, rng), 200.0, 2)
    src = src * (1 + 0.35 * shim / (np.std(shim) + 1e-12))
    sub_env = env_pts(n, [(0, 0), (0.012, 0.3), (0.04, 1), (dur * 0.75, 1), (dur, 0.4)])
    sub = harmonic_tone(f0 * 0.5, n, [(1.0 / k ** 1.1 if k % 2 else 0.0) for k in range(1, 70)])
    asp = white(n, rng) * env_pts(n, [(0, 1.0), (0.02, 0.6), (dur * 0.6, 0.5), (dur, 0.9)])
    source = nrm(src) + rough * sub_env * nrm(sub) + 0.8 * nrm(asp)

    def formants(f, tt):
        u = np.clip(tt / dur, 0.0, 1.0)
        F = [(820 - 330 * u ** 1.2) * fshift, (1650 - 520 * u) * fshift, (2600 - 250 * u) * fshift,
             3600.0 * fshift]
        B = [190.0, 240.0, 320.0, 420.0]
        A = [1.0, 0.75, 0.4, 0.2]
        g = 0.0
        for Fi, Bi, Ai in zip(F, B, A):
            g = g + Ai / np.sqrt(1.0 + ((f - Fi) / (Bi / 2.0)) ** 2)
        tilt = 1.0 / np.sqrt(1.0 + (f / 5000.0) ** 4)
        return g * tilt

    y = stft_shape(source, formants, nfft=512, hop=128)
    env = env_pts(n, [(0, 0.0), (0.004, 1.0), (dur * 0.35, 0.85), (dur * 0.7, 0.35), (dur, 0.0)])
    y = nrm(y) * env
    out = mk(dur + 0.1)
    put(out, y, 0.0, 0)
    put(out, thud(rng, 0.08, 180, 120, 0.01, 0.018, noise=0.6, noise_lp=700), 0.0, -8)
    room = synth_ir(rng_for("bark_room"), t60=0.3, stereo=False, predelay=0.004, er_gain=0.6)
    wet = add_reverb(out, room, wet=0.1)[: out.size]
    return nrm(wet)


@cue("bruno_bark")
def bruno_bark(v, rng):
    fp, fe, dur, rough, fs = pick(v, [(440, 250, 0.19, 0.55, 1.0), (400, 215, 0.22, 0.65, 0.93),
                                      (480, 280, 0.16, 0.5, 1.06)])
    return _bark(rng, fp, fe, dur, rough, fs)


def _creak(rng, dur, r0=25.0, r1=55.0, modes=((820, 0.006, 1.0), (1650, 0.004, 0.6), (2900, 0.003, 0.3))):
    """Stick-slip fabric/rope creak: jittered pulse train through small resonators."""
    n = ns(dur)
    rate = np.linspace(r0, r1, n) * (1 + 0.15 * lp(white(n, rng), 8.0, 1) / 0.05)
    ph = np.cumsum(np.maximum(rate, 1.0)) / SR
    pulses = np.zeros(n)
    idx = np.nonzero(np.diff(np.floor(ph)) > 0)[0]
    pulses[idx] = rng.uniform(0.4, 1.0, idx.size)
    return nrm(modal_bank(pulses, modes))


@cue("bruno_stand_firm")
def bruno_stand_firm(v, rng):
    p = pick(v, [1.0, 0.9])
    out = mk(0.7)
    put(out, thud(rng, 0.3, 110 * p, 50 * p, 0.02, 0.06, attack=0.0015, noise=0.8, noise_lp=500, drive=1.5), 0.0)
    put(out, grit(rng, 0.07, 700, 1500, 6000, env_ad(ns(0.07), 0.0005, 0.02)), 0.0, -14)
    put(out, dust(rng, 0.3, 0.015, 0.08), 0.01, -18)
    n = ns(0.5)
    cr = _creak(rng, 0.5, 22 * p, 50 * p) * env_swell(n, 0.7, 1.2, 1.0)
    cl = cloth(rng, 0.5, rate=70, fc=1500, env=env_swell(n, 0.7, 1.5, 1.2))
    put(out, nrm(cr + 0.7 * cl), 0.08, -12)
    put(out, nrm(lp(white(n, rng), 180, 2) * env_swell(n, 0.4)), 0.05, -12)
    return out


# --------------------------------------------------------------------------- Vex
@cue("vex_feint")
def vex_feint(v, rng):
    """Wind-up swish that is cut off abruptly, then a tail flick."""
    out = mk(0.5)
    dur = pick(v, [0.25, 0.22])
    n = ns(dur)
    env = np.linspace(0, 1, n) ** 1.5
    env[-ns(0.006):] *= np.linspace(1, 0, ns(0.006))
    put(out, whoosh(rng, dur, [0, 1], [300, pick(v, [1500, 1700])], bw=1.0, env=env, air=0.3), 0.0, 0)
    # tail flick(s): v0 = double flick (2 x 70 ms), v1 = single longer flick (100 ms)
    flicks = pick(v, [[(0.30, -6, 0.07), (0.36, -10, 0.07)], [(0.29, -5, 0.10)]])
    for t0, g, fdur in flicks:
        m = ns(fdur)
        fl = stft_shape(white(m, rng), lambda f, t: band_gain(f, 5200, 0.7), nfft=256, hop=64)
        put(out, nrm(fl * env_swell(m, 0.3, 1.2, 1.6)), t0, g)
    return out


@cue("vex_sidewinder")
def vex_sidewinder(v, rng):
    dur = 0.56
    n = ns(dur)
    fcs = pick(v, [[480, 1700, 850, 2100, 900], [550, 1500, 700, 2300, 1000]])
    env = 0.6 * env_swell(n, 0.25, 1.5, 1.5) + env_swell(n, 0.72, 1.6, 1.4)
    out = mk(dur + 0.04)
    put(out, whoosh(rng, dur, [0, 0.25, 0.5, 0.75, 1], fcs, bw=0.6, env=env / env.max(), whistle=0.45, air=0.2), 0.0)
    return out


@cue("vex_tail_sweep")
def vex_tail_sweep(v, rng):
    dur = 0.6
    n = ns(dur)
    p = pick(v, [1.0, 0.9])
    t = tvec(n)
    rot = 1 - 0.35 * (0.5 + 0.5 * np.cos(TWO_PI * pick(v, [7.0, 6.2]) * t))
    out = mk(dur + 0.04)
    put(out, whoosh(rng, dur, [0, 0.5, 1], [240 * p, 650 * p, 300 * p], bw=0.9, peak=0.5, air=0.8) * rot, 0.0)
    fur = hp(white(n, rng), 3000, 2) * env_swell(n, 0.45) * rot
    put(out, nrm(fur), 0.0, -17)
    put(out, grit(rng, 0.25, 400, 1200, 3500, env_swell(ns(0.25), 0.5)), 0.2, -16)
    return out


# --------------------------------------------------------------------------- Hops
@cue("hops_bound_takeoff")
def hops_bound_takeoff(v, rng):
    p = pick(v, [1.0, 1.08])
    out = mk(0.48)
    put(out, thud(rng, 0.12, 95 * p, 70 * p, 0.02, 0.03, attack=0.001, noise=0.8, noise_lp=700), 0.0, -1)
    n = ns(0.12)
    t = tvec(n)
    spring = osc_sine(90 * p + 190 * p * (1 - np.exp(-t / 0.02)), n) * env_ad(n, 0.001, 0.03)
    put(out, nrm(spring), 0.0, -5)
    put(out, whoosh(rng, 0.4, [0, 0.7, 1], [450 * p, 2600 * p, 1800 * p], bw=1.0, peak=0.6, air=0.3), 0.02, -1)
    put(out, flutter(rng, 0.22, rate=34, fc=2000), 0.06, -11)
    return out


@cue("hops_bound_land")
def hops_bound_land(v, rng):
    p = pick(v, [1.0, 0.92])
    out = mk(0.3)
    put(out, thud(rng, 0.18, 140 * p, 85 * p, 0.012, 0.035, attack=0.003, noise=0.9, noise_lp=700), 0.0, 0)
    put(out, thud(rng, 0.12, 150 * p, 90 * p, 0.012, 0.025, attack=0.002, noise=0.9, noise_lp=700), 0.025, -4)
    put(out, dust(rng, 0.25, 0.01, 0.07), 0.01, -18)
    return out


def _kick_snap(rng, s):
    out = mk(0.14)
    put(out, whoosh(rng, 0.1, [0, 0.6, 1], [700 * s, 2300 * s, 1500 * s], bw=0.9, peak=0.6), 0.0, 0)
    put(out, snap(rng, 0.03, 3000 * s, tau=0.003, bw_oct=1.0), 0.085, -2)
    put(out, thud(rng, 0.05, 200 * s, 150 * s, 0.005, 0.01, noise=0.8, noise_lp=1500), 0.085, -9)
    return out


@cue("hops_double_kick")
def hops_double_kick(v, rng):
    out = mk(0.42)
    put(out, _kick_snap(rng, 1.0), 0.0)
    put(out, _kick_snap(rng, 1.1), pick(v, [0.2, 0.18]))
    return out


@cue("hops_dropkick")
def hops_dropkick(v, rng):
    p = pick(v, [1.0, 0.92])
    out = mk(0.6)
    put(out, whoosh(rng, 0.55, [0, 0.35, 0.8, 1], [380 * p, 1900 * p, 1100 * p, 800 * p], bw=1.2, peak=0.35,
                    rise=1.5, fall=1.3, whistle=0.1, air=0.45), 0.0)
    put(out, flutter(rng, 0.3, rate=30, fc=1700), 0.1, -10)
    return out


@cue("hops_dropkick_crash")
def hops_dropkick_crash(v, rng):
    p = pick(v, [1.0, 0.9])
    out = mk(0.7)
    put(out, thud(rng, 0.36, 120 * p, 50 * p, 0.025, 0.08, attack=0.001, noise=0.6, noise_lp=400, drive=1.8), 0.0)
    put(out, thud(rng, 0.15, 150 * p, 90 * p, 0.012, 0.03, noise=0.8, noise_lp=700), 0.12, -7)
    put(out, thud(rng, 0.15, 140 * p, 85 * p, 0.012, 0.03, noise=0.8, noise_lp=700), 0.22, -10)
    n = ns(0.35)
    e = env_pts(n, [(0, 0), (0.02, 1), (0.2, 0.7), (0.35, 0)])
    put(out, nrm(grit(rng, 0.35, 380, 900, 4000) * e), 0.05, -10)
    put(out, dust(rng, 0.4, 0.03, 0.12), 0.03, -17)
    return out


# --------------------------------------------------------------------------- Scrap
@cue("scrap_parry_stance")
def scrap_parry_stance(v, rng):
    p = pick(v, [1.0, 1.06])
    out = mk(0.17)
    put(out, knock(rng, 0.08, [(2150 * p, 0.012, 1.0), (3400 * p, 0.008, 0.55), (5200 * p, 0.005, 0.3)],
                   exc_tau=0.0004, exc_lp=9000), 0.0, 0)
    put(out, thud(rng, 0.05, 220, 170, 0.005, 0.01, noise=0.6, noise_lp=1500), 0.0, -8)
    n = ns(0.15)
    put(out, nrm(osc_sine(pick(v, [3520.0, 3951.1]), n) * env_ad(n, 0.001, 0.04)), 0.004, -17)
    return out


@cue("scrap_leg_sweep")
def scrap_leg_sweep(v, rng):
    p = pick(v, [1.0, 0.9])
    out = mk(0.45)
    put(out, whoosh(rng, 0.4, [0, 0.5, 1], [190 * p, 560 * p, 280 * p], bw=0.9, peak=0.5, air=0.8), 0.0, 0)
    put(out, grit(rng, 0.25, 500, 900, 3200, env_swell(ns(0.25), 0.5)), 0.12, -13)
    put(out, cloth(rng, 0.3, rate=100, fc=1700), 0.02, -13)
    return out


@cue("scrap_turnabout")
def scrap_turnabout(v, rng):
    p = pick(v, [1.0, 0.92])
    out = mk(0.62)
    put(out, cloth(rng, 0.14, rate=260, fc=2400, bw=1.4, env=env_ad(ns(0.14), 0.005, 0.05)), 0.0, -2)
    put(out, thud(rng, 0.08, 180, 130, 0.006, 0.015, noise=0.9, noise_lp=1200), 0.004, -6)
    put(out, whoosh(rng, 0.4, [0, 0.5, 1], [300 * p, 1250 * p, 520 * p], bw=1.2, peak=0.5, air=0.4), 0.1, 0)
    put(out, cloth(rng, 0.1, rate=150, fc=1800), 0.48, -14)
    return out


# --------------------------------------------------------------------------- spawn
@cue("respawn")
def respawn(v, rng):
    out = mk(2.0)
    for k, note in enumerate(["A4", "C#5", "E5", "A5"]):
        put(out, bell(hz(note), 1.1, tau=0.5, bright=0.8), 0.07 * k, -2 * (k == 3))
    n = ns(0.5)
    put(out, nrm(hp(white(n, rng), 6000, 2) * env_swell(n, 0.7)), 0.1, -22)
    m = ns(1.0)
    pad = sum(osc_saw(hz(nt) * d, m, rng.uniform()) for nt in ("A3", "E4") for d in (0.997, 1.003))
    put(out, nrm(lp(pad, 1200, 2) * env_swell(m, 0.35, 1.5, 1.5)), 0.0, -12)
    return nrm(add_reverb(out, synth_ir(rng_for("respawn_ir"), t60=1.1, stereo=False), wet=0.2)[: out.size])


@cue("spawn_protect_end")
def spawn_protect_end(v, rng):
    out = mk(0.2)
    put(out, knock(rng, 0.03, [(2600, 0.006, 1.0)], exc_tau=0.0003, exc_lp=8000), 0.0, -6)
    n = ns(0.14)
    put(out, nrm(osc_sine(glide(n, 1250, 780, 0.03), n) * env_ad(n, 0.002, 0.035)), 0.003, 0)
    return out
