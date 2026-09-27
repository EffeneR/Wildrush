"""WILDRUSH ambience loops (stereo, exactly 60.000 s, seamless).

Seamless by construction: noise beds are filtered circularly, every modulation curve is periodic
with the loop length, one-shot events are rendered past the loop end and their tails wrapped to
the start, and reverb is a circular convolution. Tonal bells/horns/pulses are deliberately
avoided so ambience never imitates an essential gameplay cue.

  amb_harbor  water wash + laps against the quay with droplets, distant synthetic gull-like
              calls, soft hull knocks and mooring-rope creaks, light wind
  amb_market  fountain trickle (bubble cloud + splash hiss), awnings flapping, wordless
              murmur texture (granular vowel-like grains, heavily blurred), soft crate knocks
  amb_yard    gusty wind with faint whistle, distant metal clanks, chain rattles and creaks,
              low distant rumble
"""
from __future__ import annotations

import numpy as np

from dsp import (SR, TWO_PI, band_gain, bp, bq, conv_circular, curve, db2a, env_ad, env_pts, env_swell,
                 fade_edges, harmonic_tone, hp, lp, mix_at, modal_bank, ns, osc_sine, pan, periodic_curve,
                 rng_for, sos, sos_circular, stft_shape, synth_ir, tvec, white, wrap_to)
from instruments import nrm

REGISTRY: dict = {}
LOOP_S = 60.0
N = ns(LOOP_S)


def cue(name):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


class Layer:
    """Stereo event layer rendered past the loop end, then wrapped (tails continue at the start)."""

    def __init__(self, tail_s=8.0):
        self.buf = np.zeros((2, N + ns(tail_s)))

    def add(self, x, t, gain_db=0.0, p=0.0):
        st = pan(x, p) if x.ndim == 1 else x
        mix_at(self.buf, st, ns(t) % N, float(db2a(gain_db)))

    def loop(self):
        return wrap_to(self.buf, N)


def times(rng, mean_gap, jitter=0.5):
    out = []
    t = rng.uniform(0, mean_gap)
    while t < LOOP_S:
        out.append(t)
        t += mean_gap * rng.uniform(1 - jitter, 1 + jitter)
    return out


def circ(kind, f, x, order=2):
    return sos_circular(sos(kind, f, order), x)


def noise_bed(rng, lo, hi, order=2, width=0.8):
    """Stereo band-limited noise bed with partial L/R correlation (natural width)."""
    common = circ("bandpass", [lo, hi], white(N, rng), order)
    sides = [circ("bandpass", [lo, hi], white(N, rng), order) for _ in range(2)]
    y = np.stack([common * (1 - width) + s * width for s in sides])
    return y / (np.std(y) + 1e-12)


def per_fn(rng, harmonics, lo, hi, rate=20.0):
    """Periodic control curve as a function of time (s) - for circular STFT shaping."""
    m = int(LOOP_S * rate)
    k = np.arange(1, harmonics + 1)
    coef = (rng.standard_normal(harmonics) + 1j * rng.standard_normal(harmonics)) / k
    spec = np.zeros(m // 2 + 1, dtype=complex)
    spec[1:harmonics + 1] = coef
    c = np.fft.irfft(spec, m)
    c = lo + (hi - lo) * (c - c.min()) / (c.max() - c.min() + 1e-15)
    grid = np.arange(m) * (LOOP_S / m)
    return lambda t: np.interp(t, grid, c, period=LOOP_S)


def distant(x_stereo, rng_key, t60=1.8, wet=0.45, lp_hz=3500.0):
    """Distance treatment for a wrapped stereo layer: circular low-pass + circular reverb."""
    y = circ("lowpass", lp_hz, x_stereo, 2)
    ir = synth_ir(rng_for(rng_key), t60=t60, stereo=True, predelay=0.03, er_gain=0.3)
    return (1 - wet) * y + wet * conv_circular(y, ir)


# --------------------------------------------------------------------------- sources
def wind(rng, depth=0.6, whistle=0.0, lo=120.0, hi=2600.0, gust_h=10):
    bed = noise_bed(rng, lo, hi, 2, 0.8)
    gust = periodic_curve(N, rng, gust_h, 1 - depth, 1.0)
    bed *= gust ** 1.5
    if whistle > 0:
        fc = per_fn(rng, 5, 650.0, 1150.0)
        chans = []
        for _ in range(2):
            w = stft_shape(white(N, rng), lambda f, t: band_gain(f, fc(t), 0.05), nfft=4096, hop=1024,
                           circular=True)
            chans.append(w / (np.std(w) + 1e-12))
        bed = bed + whistle * np.stack(chans) * gust ** 3
    return bed


def bubble(f0, dur, rise_oct, tau=None):
    n = ns(dur)
    t = tvec(n)
    y = osc_sine(f0 * 2 ** (rise_oct * t / dur), n) * env_ad(n, 0.0004, tau or dur / 4)
    return fade_edges(y, 0.0, 0.25 * dur)


def lap(rng, dur):
    """One wave lapping against stone: swelling band-passed noise with a moving centre + droplets."""
    n = ns(dur)
    fcf = curve([0, 0.3 * dur, dur], [350.0, rng.uniform(900, 1600), 500.0], log=True)
    y = stft_shape(white(n, rng), lambda f, t: band_gain(f, fcf(t), 1.0, 0.02), nfft=1024, hop=256)
    y = nrm(y) * env_swell(n, rng.uniform(0.2, 0.35), 1.6, 1.3)
    for _ in range(int(rng.integers(4, 12))):
        b = bubble(rng.uniform(500, 2400), rng.uniform(0.015, 0.05), rng.uniform(0.3, 1.0))
        mix_at(y, b, ns(rng.uniform(0.25, 0.85) * dur), float(db2a(rng.uniform(-22, -12))))
    return y


def gull_call(rng, fp, dur):
    """Synthetic gull-like 'kee-ow': fast rise then long fall, nasal harmonic tone + breath."""
    n = ns(dur)
    t = tvec(n)
    rise = 0.04
    f = np.where(t < rise, fp * (0.75 + 0.25 * t / rise), fp * (0.62 + 0.38 * np.exp(-(t - rise) / (dur * 0.45))))
    f = f * (1 + 0.012 * np.sin(TWO_PI * 28 * t))
    tone = harmonic_tone(f, n, [1.0, 0.8, 0.55, 0.35, 0.22, 0.12, 0.06])
    tone = bq(tone, "peak", 2600.0, 1.2, 8.0)
    breath = bp(white(n, rng), 1500.0, 4000.0, 2)
    y = nrm(tone) + 0.12 * nrm(breath)
    return fade_edges(y * env_pts(n, [(0, 0), (0.02, 1), (dur * 0.5, 0.8), (dur, 0)]), 0.0, 0.02)


def knock_modes(rng, modes, dur, exc_tau=0.0015, exc_lp=3000.0):
    n = ns(dur)
    exc = lp(white(n, rng) * env_ad(n, 0.0002, exc_tau), exc_lp, 2)
    return fade_edges(nrm(modal_bank(exc, modes)), 0.0, 0.2 * dur)


def creak(rng, dur, r0, r1, modes):
    n = ns(dur)
    rate = np.linspace(r0, r1, n) * (1 + 0.2 * lp(white(n, rng), 6.0, 1) / 0.05)
    ph = np.cumsum(np.maximum(rate, 1.0)) / SR
    pulses = np.zeros(n)
    idx = np.nonzero(np.diff(np.floor(ph)) > 0)[0]
    pulses[idx] = rng.uniform(0.3, 1.0, idx.size)
    return fade_edges(nrm(modal_bank(pulses, modes)) * env_swell(n, rng.uniform(0.3, 0.6), 1.3, 1.2), 0.0, 0.05)


# --------------------------------------------------------------------------- harbor
@cue("amb_harbor")
def amb_harbor(v, rng):
    wash = noise_bed(rng, 60.0, 900.0, 2, 0.7)
    wash = circ("lowpass", 700.0, wash, 2)
    wash *= periodic_curve(N, rng, 8, 0.45, 1.0) ** 1.3
    wash /= np.std(wash) + 1e-12

    laps = Layer(3.0)
    for t0 in times(rng, 3.4, 0.5):
        laps.add(lap(rng, rng.uniform(0.9, 1.8)), t0, rng.uniform(-6, 0), rng.uniform(-0.6, 0.6))
    laps = laps.loop()

    gulls = Layer(3.0)
    for t0 in times(rng, 11.0, 0.45):
        fp = rng.uniform(1100, 1600)
        p = rng.uniform(-0.8, 0.8)
        t = t0
        for _ in range(int(rng.integers(1, 5))):
            d = rng.uniform(0.25, 0.4)
            gulls.add(gull_call(rng, fp * rng.uniform(0.94, 1.06), d), t, rng.uniform(-5, 0), p)
            t += d + rng.uniform(0.08, 0.3)
    gulls = distant(gulls.loop(), "harbor_gull_ir", t60=2.2, wet=0.55, lp_hz=3200.0)

    hull = Layer(3.0)
    for t0 in times(rng, 13.0, 0.5):
        r = rng.uniform(0.9, 1.1)
        hull.add(knock_modes(rng, [(92 * r, 0.16, 1.0), (215 * r, 0.08, 0.6), (390 * r, 0.05, 0.3)], 0.8),
                 t0, rng.uniform(-6, 0), rng.uniform(-0.5, 0.5))
    for t0 in times(rng, 17.0, 0.5):
        hull.add(creak(rng, rng.uniform(0.7, 1.4), 14, 30, [(420, 0.012, 1.0), (980, 0.008, 0.5), (1850, 0.005, 0.2)]),
                 t0, rng.uniform(-10, -4), rng.uniform(-0.7, 0.7))
    hull = distant(hull.loop(), "harbor_hull_ir", t60=1.2, wet=0.35, lp_hz=2500.0)

    air = wind(rng, depth=0.55, whistle=0.0, lo=150.0, hi=3000.0)
    mix = (1.0 * wash + 0.55 * laps / (np.std(laps) + 1e-12) + 0.2 * gulls / (np.std(gulls) + 1e-12)
           + 0.25 * hull / (np.std(hull) + 1e-12) + 0.3 * air)
    return mix


# --------------------------------------------------------------------------- market
VOWELS = [(300, 870, 2240), (400, 2000, 2550), (530, 1840, 2480), (660, 1720, 2410), (730, 1090, 2440),
          (570, 840, 2410), (440, 1020, 2240), (490, 1350, 1690)]


def murmur_grain(rng, dur):
    """Wordless voiced grain: harmonic source weighted by a random vowel-like formant envelope."""
    n = ns(dur)
    f0 = rng.uniform(95, 250)
    f0t = f0 * (1 + rng.uniform(-0.1, 0.1) * np.linspace(0, 1, n))
    F = np.array(VOWELS[int(rng.integers(len(VOWELS)))], dtype=float) * rng.uniform(0.9, 1.1)
    B = np.array([90.0, 120.0, 170.0])
    kmax = int(2000 // f0)
    amps = []
    for k in range(1, kmax + 1):
        fk = k * f0
        g = sum(a / np.sqrt(1 + ((fk - Fi) / (Bi / 2)) ** 2) for Fi, Bi, a in zip(F, B, (1.0, 0.6, 0.25)))
        amps.append(g / k ** 0.6)
    y = harmonic_tone(f0t, n, amps)
    return nrm(y) * np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5


@cue("amb_market")
def amb_market(v, rng):
    # fountain: bubble cloud + splash hiss + pool rumble, near the centre of the image
    fountain = Layer(0.5)
    count = int(rng.poisson(170 * LOOP_S))
    for t0 in rng.uniform(0, LOOP_S, count):
        f0 = float(np.exp(rng.uniform(np.log(900), np.log(4500))))
        d = rng.uniform(0.008, 0.03)
        fountain.add(bubble(f0, d, rng.uniform(0.2, 0.8)), t0, float(rng.normal(-8, 4)),
                     float(np.clip(rng.normal(0, 0.3), -0.8, 0.8)))
    fountain = fountain.loop()
    fountain /= np.std(fountain) + 1e-12
    hiss = noise_bed(rng, 1200.0, 9000.0, 2, 0.5)
    am = circ("lowpass", 25.0, white(N, rng))
    hiss *= 0.7 + 0.3 * am / (np.max(np.abs(am)) + 1e-12)
    pool = noise_bed(rng, 40.0, 300.0, 2, 0.4)

    awn = Layer(2.5)
    for t0 in times(rng, 8.0, 0.5):
        d = rng.uniform(0.6, 1.6)
        n = ns(d)
        t = tvec(n)
        rate = rng.uniform(9, 16)
        wob = np.cumsum(rng.normal(0, 1.0, n)) / SR * 6.0
        am_f = (0.5 + 0.5 * np.sin(TWO_PI * rate * t + wob)) ** 3
        flap = bp(white(n, rng), 120.0, 1400.0, 2) * (0.3 + am_f) * env_swell(n, 0.3, 1.2, 1.4)
        m = ns(0.06)
        snapx = bp(white(m, rng), 200.0, 2000.0, 2) * env_ad(m, 0.001, 0.015)
        flap[:m] += 1.5 * snapx * np.std(flap) / (np.std(snapx) + 1e-12)
        awn.add(fade_edges(nrm(flap), 0.005, 0.05), t0, rng.uniform(-6, 0), rng.uniform(-0.75, 0.75))
    awn = distant(awn.loop(), "market_awning_ir", t60=0.9, wet=0.25, lp_hz=4000.0)

    crowd = Layer(1.0)
    count = int(rng.poisson(48 * LOOP_S))
    for t0 in rng.uniform(0, LOOP_S, count):
        crowd.add(murmur_grain(rng, rng.uniform(0.08, 0.3)), t0, float(rng.normal(-6, 3)),
                  float(rng.uniform(-0.85, 0.85)))
    crowd = crowd.loop()
    crowd *= periodic_curve(N, rng, 6, 0.6, 1.0)
    crowd = distant(crowd, "market_crowd_ir", t60=1.6, wet=0.6, lp_hz=1600.0)

    crates = Layer(2.0)
    for t0 in times(rng, 9.0, 0.6):
        r = rng.uniform(0.85, 1.2)
        crates.add(knock_modes(rng, [(160 * r, 0.06, 1.0), (410 * r, 0.03, 0.5), (820 * r, 0.015, 0.25)], 0.4),
                   t0, rng.uniform(-8, 0), rng.uniform(-0.8, 0.8))
    crates = distant(crates.loop(), "market_crate_ir", t60=1.0, wet=0.4, lp_hz=3000.0)

    air = wind(rng, depth=0.4, lo=150.0, hi=2500.0)
    s = lambda x: x / (np.std(x) + 1e-12)
    return (0.55 * s(fountain) + 0.35 * hiss + 0.25 * pool + 0.35 * s(awn) + 0.45 * s(crowd)
            + 0.12 * s(crates) + 0.15 * air)


# --------------------------------------------------------------------------- yard
def clank(rng):
    base = rng.uniform(170, 420)
    ratios = np.array([1.0, 2.32, 3.87, 5.1, 6.9, 8.4]) * rng.uniform(0.97, 1.03, 6)
    taus = np.array([1.0, 0.6, 0.45, 0.3, 0.2, 0.15]) * rng.uniform(0.6, 1.2)
    amps = [1.0, 0.6, 0.5, 0.35, 0.25, 0.15]
    y = knock_modes(rng, [(base * r, t, a) for r, t, a in zip(ratios, taus, amps)], 1.8, exc_tau=0.0006,
                    exc_lp=6000.0)
    n = y.size
    y += 0.4 * nrm(osc_sine(base * 0.5, n) * env_ad(n, 0.001, 0.05))
    return nrm(y)


def rattle(rng, dur):
    n = ns(dur + 0.2)
    y = np.zeros(n)
    k = int(rng.integers(10, 30))
    for i, t0 in enumerate(np.sort(rng.uniform(0, dur, k))):
        r = rng.uniform(0.85, 1.2)
        tick = knock_modes(rng, [(2400 * r, 0.02, 1.0), (3700 * r, 0.012, 0.6), (5600 * r, 0.008, 0.3)], 0.08,
                           exc_tau=0.0003, exc_lp=9000.0)
        mix_at(y, tick, ns(t0), float(db2a(rng.uniform(-10, 0) - 6 * i / k)))
    return nrm(y)


@cue("amb_yard")
def amb_yard(v, rng):
    air = wind(rng, depth=0.75, whistle=0.18, lo=100.0, hi=2800.0, gust_h=14)
    rumble = noise_bed(rng, 25.0, 140.0, 2, 0.5)
    rumble *= periodic_curve(N, rng, 4, 0.6, 1.0)

    clanks = Layer(4.0)
    for t0 in times(rng, 6.0, 0.55):
        p = rng.uniform(-0.8, 0.8)
        clanks.add(clank(rng), t0, rng.uniform(-8, 0), p)
        if rng.uniform() < 0.35:
            clanks.add(clank(rng), t0 + rng.uniform(0.15, 0.4), rng.uniform(-12, -4), p)
    clanks = distant(clanks.loop(), "yard_clank_ir", t60=2.4, wet=0.6, lp_hz=3000.0)

    chains = Layer(3.0)
    for t0 in times(rng, 8.0, 0.5):
        p = rng.uniform(-0.8, 0.8)
        if rng.uniform() < 0.5:
            chains.add(rattle(rng, rng.uniform(0.4, 1.0)), t0, rng.uniform(-8, -2), p)
        else:
            r = rng.uniform(0.8, 1.2)
            chains.add(creak(rng, rng.uniform(0.6, 1.4), 15, 35, [(420 * r, 0.012, 1.0), (980 * r, 0.008, 0.5),
                                                                  (1850 * r, 0.005, 0.25)]), t0,
                       rng.uniform(-8, -2), p)
    chains = distant(chains.loop(), "yard_chain_ir", t60=1.8, wet=0.5, lp_hz=4500.0)

    s = lambda x: x / (np.std(x) + 1e-12)
    return 0.55 * air + 0.3 * rumble + 0.35 * s(clanks) + 0.25 * s(chains)
