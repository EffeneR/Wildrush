"""Synthesized instruments shared by the UI stings and the music (numpy/scipy only).

Every instrument returns a float array; mono unless it says otherwise. Tones use band-limited
oscillators (polyBLEP), FM or modal (decaying-sine) synthesis; drums are built from pitched sines
and filtered noise. Nothing here is sampled.
"""
from __future__ import annotations

import numpy as np

from dsp import (SR, TWO_PI, band_gain, bp, curve, env_ad, env_pts, fade_edges, fm_tone, hp, lp, lp_gain,
                 modal_sines, ns, osc_saw, osc_sine, osc_square, osc_tri, stft_shape, tvec, white)


def nrm(x):
    p = float(np.max(np.abs(x))) if x.size else 0.0
    return x / p if p > 0 else x


# --------------------------------------------------------------------------- tonal
def bell(f, dur, tau=0.6, bright=1.0, attack=0.002, chorus=0.3, ratios=None):
    """Soft bell / chime (mostly harmonic partials, gentle mallet attack)."""
    rs = ratios or [(1.0, 1.0, 1.0), (2.0, 0.34 * bright, 0.5), (3.0, 0.13 * bright, 0.3),
                    (4.2, 0.05 * bright, 0.18)]
    modes = [(f * r, tau * tm, a) for r, a, tm in rs]
    if chorus:
        modes.append((f * 1.0021, tau, chorus))
    return fade_edges(nrm(modal_sines(ns(dur), modes, attack=attack)), 0.0, min(0.35 * dur, 0.4))


def marimba(f, dur=0.8, tau=0.32, attack=0.001):
    """Tuned-bar tone (partials 1 : 4 : 10)."""
    modes = [(f, tau, 1.0), (4.0 * f, tau * 0.22, 0.28), (10.0 * f, tau * 0.07, 0.07)]
    return fade_edges(nrm(modal_sines(ns(dur), modes, attack=attack)), 0.0, min(0.3 * dur, 0.3))


def glass(f, dur=1.0, tau=0.35, attack=0.0008):
    """Bright crystalline ring (free-bar inharmonic ratios)."""
    modes = [(f, tau, 1.0), (f * 1.0031, tau, 0.4), (f * 2.76, tau * 0.45, 0.4), (f * 5.40, tau * 0.2, 0.15)]
    return fade_edges(nrm(modal_sines(ns(dur), modes, attack=attack)), 0.0, min(0.3 * dur, 0.3))


def fm_pluck(f, dur=0.5, index=2.5, ratio=2.0, idx_tau=0.08, decay=0.25, attack=0.002):
    n = ns(dur)
    t = tvec(n)
    y = fm_tone(f, n, ratio, index * np.exp(-t / idx_tau)) * env_ad(n, attack, decay)
    return fade_edges(y, 0.0, min(0.05, 0.2 * dur))


def epiano(f, dur, vel=0.8, decay=1.3, release=0.25):
    """FM electric piano: 1:1 body pair + fast-decaying high 'tine' pair."""
    n = ns(dur + release)
    t = tvec(n)
    idx1 = (0.5 + 1.4 * vel) * np.exp(-t / 0.35) + 0.2
    body = fm_tone(f, n, 1.0, idx1)
    tine = fm_tone(f, n, 14.0, 1.1 * vel * np.exp(-t / 0.02)) * np.exp(-t / 0.1)
    amp = env_ad(n, 0.002, decay) * env_pts(n, [(0, 1), (dur, 1), (dur + release, 0)])
    return (body + 0.22 * tine) * amp * (0.6 + 0.4 * vel)


def brass(freqs, dur, rng, attack=0.06, release=0.3, bright=(600.0, 3000.0, 1500.0), vib_depth=0.004,
          vib_rate=5.2, scoop=0.03, bend=None, detune=6.0, formant=1100.0):
    """Synth brass: detuned saws with a pitch scoop, delayed vibrato, a brightness envelope
    (time-varying low-pass) and a broad formant bump. ``bend(t)`` returns cents."""
    n = ns(dur + release)
    t = tvec(n)
    y = np.zeros(n)
    vib = 1 + vib_depth * np.sin(TWO_PI * vib_rate * t + rng.uniform(0, TWO_PI)) * np.clip((t - 0.25) / 0.3, 0, 1)
    bnd = 2 ** (bend(t) / 1200.0) if bend is not None else 1.0
    for f in freqs:
        for dc in (-detune, detune):
            pitch = f * 2 ** (dc / 1200.0) * (1 - scoop * np.exp(-t / 0.035)) * vib * bnd
            y += osc_saw(pitch, n, rng.uniform())
    fc = curve([0, attack, attack + 0.25, dur + release], [bright[0], bright[1], bright[2], bright[2] * 0.7], log=True)
    y = stft_shape(y, lambda f_, t_: lp_gain(f_, fc(t_), 2.0) * (1 + 0.8 * band_gain(f_, formant, 0.5)),
                   nfft=1024, hop=256)
    amp = env_pts(n, [(0, 0), (attack, 1), (attack + 0.1, 0.9), (dur, 0.85), (dur + release, 0)])
    return nrm(y * amp)


def saw_pad(freqs, dur, rng, cutoff=1500.0, attack=0.4, release=1.0, detune=9.0, voices=3, stereo=True,
            cutoff_end=None, order=2):
    """Detuned saw-stack pad through a low-pass (optionally sweeping from cutoff to cutoff_end).
    Returns (2, n) when stereo (independent detune/phases per side) else mono."""
    n = ns(dur + release)
    chans = []
    for _ in range(2 if stereo else 1):
        y = np.zeros(n)
        for f in freqs:
            for k in range(voices):
                spread = (k - (voices - 1) / 2) / max(1.0, (voices - 1) / 2)
                dc = detune * spread + rng.normal(0, 1.5)
                y += osc_saw(f * 2 ** (dc / 1200.0), n, rng.uniform())
        if cutoff_end is None:
            y = lp(y, cutoff, order)
        else:
            fc = curve([0, dur + release], [cutoff, cutoff_end], log=True)
            y = stft_shape(y, lambda f_, t_: lp_gain(f_, fc(t_), float(order)), nfft=2048, hop=512)
        chans.append(y / np.sqrt(len(freqs) * voices))
    a = min(attack, dur)
    amp = env_pts(n, [(0, 0), (a, 1), (dur, 1), (dur + release, 0)])
    amp = np.sin(0.5 * np.pi * amp) ** 2
    out = np.stack(chans) * amp
    return out if stereo else out[0]


def sine_pad(freqs, dur, attack=0.5, release=1.0, tremolo=0.0, rate=0.3):
    n = ns(dur + release)
    t = tvec(n)
    y = sum(osc_sine(f, n) + 0.25 * osc_sine(2 * f, n) + 0.1 * osc_tri(f * 1.001, n) for f in freqs)
    amp = env_pts(n, [(0, 0), (min(attack, dur), 1), (dur, 1), (dur + release, 0)])
    amp = np.sin(0.5 * np.pi * amp) ** 2
    if tremolo:
        amp = amp * (1 - tremolo * (0.5 + 0.5 * np.sin(TWO_PI * rate * t)))
    return y * amp / max(1, len(freqs))


def sub_bass(f, dur, attack=0.004, release=0.08, drive=1.3, harm=0.25, cutoff=500.0, rng=None):
    """Clean sine sub with a little saturated saw on top (low-passed) for definition."""
    n = ns(dur + release)
    y = osc_sine(f, n) + harm * lp(osc_saw(f, n, 0.0), cutoff, 2)
    y = np.tanh(drive * y) / np.tanh(drive)
    amp = env_pts(n, [(0, 0), (attack, 1), (max(attack, dur - 0.01), 0.9), (dur + release, 0)])
    return y * amp


def pluck_bass(f, dur, cutoff0=1800.0, cutoff1=250.0, tau=0.09, release=0.06):
    """Filter-enveloped saw + sine bass note (the 'driving' 8th-note bass)."""
    n = ns(dur + release)
    t = tvec(n)
    raw = 0.7 * osc_saw(f, n, 0.0) + 0.6 * osc_sine(f, n)
    fc = cutoff1 + (cutoff0 - cutoff1) * np.exp(-t / tau)
    y = stft_shape(raw, lambda f_, t_: lp_gain(f_, np.interp(t_, t, fc), 2.0), nfft=512, hop=128)
    y = np.tanh(1.4 * y) / np.tanh(1.4)
    amp = env_pts(n, [(0, 0), (0.003, 1), (dur, 0.75), (dur + release, 0)])
    return y * amp


# --------------------------------------------------------------------------- drums
def kick(rng, dur=0.5, f0=110.0, f1=44.0, pitch_tau=0.035, amp_tau=0.16, click=0.25, drive=1.2):
    n = ns(dur)
    t = tvec(n)
    f = f1 + (f0 - f1) * np.exp(-t / pitch_tau)
    body = osc_sine(f, n) * env_ad(n, 0.0015, amp_tau)
    body = np.tanh(drive * body) / np.tanh(drive)
    if click:
        m = ns(0.008)
        c = bp(white(m, rng), 1500.0, 5000.0, 4) * env_ad(m, 0.0004, 0.002)  # soft beater click
        body[:m] += click * nrm(c)
    return fade_edges(body, 0.0, 0.05)


def snare(rng, dur=0.3, f=185.0, tone=0.55, noise_tau=0.08, bright=5000.0):
    n = ns(dur)
    t = tvec(n)
    body = osc_sine(f * (1 + 0.15 * np.exp(-t / 0.01)), n) * env_ad(n, 0.0008, 0.05)
    body += 0.5 * osc_sine(f * 1.62, n) * env_ad(n, 0.0008, 0.03)
    nz = bp(white(n, rng), 900.0, 9000.0, 2) * env_ad(n, 0.0008, noise_tau)
    nz = nz + 0.5 * hp(white(n, rng), bright, 2) * env_ad(n, 0.0005, noise_tau * 0.6)
    return fade_edges(tone * nrm(body) + nrm(nz), 0.0, 0.05)


def clap(rng, dur=0.35, fc=1500.0):
    n = ns(dur)
    y = np.zeros(n)
    for k, t0 in enumerate((0.0, 0.009, 0.019, 0.028)):
        m = ns(0.03)
        b = bp(white(m, rng), fc * 0.6, fc * 2.2, 2) * env_ad(m, 0.0003, 0.004)
        s = ns(t0)
        y[s:s + m] += b[: n - s] * (0.8 if k < 3 else 1.0)
    tail = bp(white(n, rng), fc * 0.6, fc * 2.5, 2) * env_ad(n, 0.0005, 0.06)
    s = ns(0.028)
    y[s:] += 0.8 * tail[: n - s]
    return fade_edges(nrm(y), 0.0, 0.05)


_HAT_FREQS = (205.3, 304.4, 369.6, 522.7, 540.0, 800.0)


def hat(rng, dur=0.08, open_=False, tone=0.5):
    """808-style metallic hat: six detuned squares band-passed high, plus noise."""
    n = ns(dur)
    metal = sum(osc_square(f * 1.8, n, rng.uniform()) for f in _HAT_FREQS)
    y = tone * nrm(bp(metal, 7000.0, 13000.0, 2)) + nrm(hp(white(n, rng), 8000.0, 2))
    y *= env_ad(n, 0.0003, 0.25 if open_ else 0.022)
    return fade_edges(nrm(y), 0.0, 0.2 * dur)


def shaker(rng, dur=0.09):
    n = ns(dur)
    y = bp(white(n, rng), 4500.0, 11000.0, 2) * env_pts(n, [(0, 0), (0.008, 1), (0.02, 0.6), (dur, 0)])
    return nrm(y)


def tom(rng, f0=110.0, dur=0.5):
    n = ns(dur)
    t = tvec(n)
    y = osc_sine(f0 * (1 + 0.35 * np.exp(-t / 0.04)), n) * env_ad(n, 0.001, 0.14)
    y += 0.3 * lp(white(n, rng), 1200.0, 2) * env_ad(n, 0.0005, 0.02)
    return fade_edges(nrm(y), 0.0, 0.1)


def taiko(rng, f0=62.0, dur=1.1):
    n = ns(dur)
    t = tvec(n)
    body = osc_sine(f0 * (1 + 0.4 * np.exp(-t / 0.03)), n) * env_ad(n, 0.002, 0.28)
    body += 0.35 * osc_sine(f0 * 1.52 * (1 + 0.3 * np.exp(-t / 0.03)), n) * env_ad(n, 0.002, 0.12)
    skin = lp(white(n, rng), 900.0, 2) * env_ad(n, 0.001, 0.035)
    return fade_edges(nrm(nrm(body) + 0.45 * nrm(skin)), 0.0, 0.25)


def timpani(rng, f, dur=1.4):
    n = ns(dur)
    t = tvec(n)
    modes = [(f, 0.55, 1.0), (f * 1.5, 0.35, 0.45), (f * 1.98, 0.28, 0.3), (f * 2.44, 0.2, 0.18)]
    y = modal_sines(n, modes, attack=0.003) * (1 + 0.06 * np.exp(-t / 0.05))
    y += 0.4 * lp(white(n, rng), 700.0, 2) * env_ad(n, 0.001, 0.03)
    return fade_edges(nrm(y), 0.0, 0.3)


def crash(rng, dur=2.0, tau=0.7, soft=True):
    n = ns(dur)
    metal = sum(osc_square(f * 3.1, n, rng.uniform()) for f in _HAT_FREQS)
    y = 0.4 * nrm(bp(metal, 4000.0, 12000.0, 2)) + nrm(hp(white(n, rng), 3000.0, 2))
    att = 0.02 if soft else 0.001
    y *= env_ad(n, att, tau)
    return fade_edges(nrm(lp(y, 11000.0, 2)), 0.0, 0.3 * dur)


def riser(rng, dur, f0=400.0, f1=6000.0, bw=0.8, curve_pow=2.0):
    """Noise riser: band moving up exponentially with a crescendo."""
    n = ns(dur)
    fcf = curve([0, dur], [f0, f1], log=True)
    y = stft_shape(white(n, rng), lambda f, t: band_gain(f, fcf(t), bw), nfft=1024, hop=256)
    amp = np.linspace(0.0, 1.0, n) ** curve_pow
    amp[-ns(0.01):] *= np.linspace(1, 0, ns(0.01))
    return nrm(y) * amp


def reverse_swell(rng, dur=0.8, lo=2500.0):
    n = ns(dur)
    y = hp(white(n, rng), lo, 2) * np.exp((np.linspace(0, 1, n) - 1) * 5.0)
    y[-ns(0.008):] *= np.linspace(1, 0, ns(0.008))
    return nrm(y)


def sub_boom(dur=1.2, f0=58.0, f1=38.0):
    n = ns(dur)
    t = tvec(n)
    y = osc_sine(f1 + (f0 - f1) * np.exp(-t / 0.15), n) * env_ad(n, 0.004, 0.35)
    return fade_edges(y, 0.0, 0.3)
