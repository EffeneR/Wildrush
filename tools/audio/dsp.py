"""WILDRUSH procedural audio - DSP primitives (numpy / scipy only).

Conventions
-----------
* Sample rate is fixed at 44.1 kHz (``SR``).
* Mono signals are 1-D float64 arrays; stereo signals have shape ``(2, n)``.
* Every random choice goes through ``rng_for(...)`` so builds are reproducible
  (seed = CRC32 of a stable key string, never Python's randomised ``hash``).
* Loop helpers (``wrap_to``, ``sos_circular``, ``stft_shape`` with
  ``circular=True``, ``conv_circular``, ``periodic_curve``) treat the signal as
  periodic, so a loop rendered with them has no seam at the loop point.
"""
from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf
from scipy.ndimage import minimum_filter1d, uniform_filter1d

SR = 44100
TWO_PI = 2.0 * np.pi


# --------------------------------------------------------------------------- basics
def ns(sec: float) -> int:
    """Seconds -> sample count (at least 1)."""
    return max(1, int(round(float(sec) * SR)))


def tvec(n: int) -> np.ndarray:
    return np.arange(int(n), dtype=np.float64) / SR


def rng_for(*keys) -> np.random.Generator:
    """Deterministic RNG from a stable key (CRC32 of the joined key string)."""
    seed = zlib.crc32("::".join(str(k) for k in keys).encode("utf-8"))
    return np.random.default_rng(seed)


def db2a(db):
    return 10.0 ** (np.asarray(db, dtype=np.float64) / 20.0)


def a2db(a):
    return 20.0 * np.log10(np.maximum(np.asarray(a, dtype=np.float64), 1e-12))


_NOTE_IDX = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name: str) -> int:
    """'C#4' / 'Bb2' / 'A4' -> MIDI note number (A4 = 69)."""
    name = name.strip()
    idx = _NOTE_IDX[name[0].upper()]
    rest = name[1:]
    while rest and rest[0] in "#b":
        idx += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + idx


def hz(note) -> float:
    """Note name or MIDI number -> frequency in Hz (equal temperament, A4 = 440)."""
    m = midi(note) if isinstance(note, str) else float(note)
    return float(440.0 * 2.0 ** ((m - 69) / 12.0))


def pad_to(x: np.ndarray, n: int) -> np.ndarray:
    if x.shape[-1] >= n:
        return x[..., :n]
    pad = [(0, 0)] * (x.ndim - 1) + [(0, n - x.shape[-1])]
    return np.pad(x, pad)


def mix_at(dst: np.ndarray, src: np.ndarray, start: int, gain: float = 1.0) -> None:
    """Add ``src`` into ``dst`` at sample ``start`` (clipped to dst length). Works for mono/stereo."""
    start = int(start)
    if start >= dst.shape[-1]:
        return
    if start < 0:
        src = src[..., -start:]
        start = 0
    m = min(src.shape[-1], dst.shape[-1] - start)
    if m <= 0:
        return
    dst[..., start:start + m] += gain * src[..., :m]


def pan(x: np.ndarray, p: float) -> np.ndarray:
    """Equal-power pan of a mono signal, p in [-1 (L), +1 (R)] -> (2, n)."""
    ang = (np.clip(p, -1.0, 1.0) + 1.0) * np.pi / 4.0
    return np.stack([np.cos(ang) * x, np.sin(ang) * x])


# --------------------------------------------------------------------------- envelopes
def env_ad(n: int, attack: float, decay: float, hold: float = 0.0) -> np.ndarray:
    """Raised-cosine attack (s), optional hold (s), exponential decay (time constant, s)."""
    t = tvec(n)
    e = np.ones(n)
    if attack > 0:
        m = t < attack
        e[m] = 0.5 - 0.5 * np.cos(np.pi * t[m] / attack)
    e *= np.exp(-np.maximum(t - attack - hold, 0.0) / max(decay, 1e-6))
    return e


def env_pts(n: int, pts, db: bool = False) -> np.ndarray:
    """Piecewise-linear envelope through (time_s, value) points. With db=True the values are
    dB and are interpolated in dB (i.e. exponential segments)."""
    t = tvec(n)
    ts = np.array([p[0] for p in pts], dtype=np.float64)
    vs = np.array([p[1] for p in pts], dtype=np.float64)
    e = np.interp(t, ts, vs)
    return db2a(e) if db else e


def env_swell(n: int, peak: float = 0.4, rise: float = 2.0, fall: float = 1.6) -> np.ndarray:
    """Single-hump envelope: smooth sine-power rise to 1 at ``peak`` (fraction of n), then an
    exponential-style release that reaches exactly 0 at the end (steeper for larger ``fall``)."""
    u = np.linspace(0.0, 1.0, n)
    peak = float(np.clip(peak, 0.02, 0.98))
    up = np.sin(0.5 * np.pi * np.clip(u / peak, 0.0, 1.0)) ** rise
    s = np.clip((u - peak) / (1.0 - peak), 0.0, 1.0)
    a = 1.0 + 2.2 * fall
    down = (np.exp(-a * s) - np.exp(-a)) / (1.0 - np.exp(-a))
    return np.where(u < peak, up, down)


def fade_edges(x: np.ndarray, fin: float = 0.002, fout: float = 0.01) -> np.ndarray:
    """Raised-cosine fade-in/out so the first and last samples are exactly zero."""
    x = np.array(x, dtype=np.float64, copy=True)
    n = x.shape[-1]
    ni = min(ns(fin), n // 2) if fin > 0 else 0
    no = min(ns(fout), n // 2) if fout > 0 else 0
    if ni > 0:
        x[..., :ni] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(ni) / ni)
    if no > 0:
        x[..., n - no:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(1, no + 1) / no)
    return x


# --------------------------------------------------------------------------- noise
def white(n: int, rng) -> np.ndarray:
    return rng.standard_normal(int(n))


def colored(n: int, rng, slope_db_oct: float = -3.0, f_lo: float = 15.0, f_hi: float | None = None) -> np.ndarray:
    """Unit-RMS noise with a spectral slope (dB/octave). Periodic with period n."""
    n = int(n)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    mag = (np.maximum(f, f_lo) / 1000.0) ** (slope_db_oct / 6.0206)
    mag[0] = 0.0
    if f_hi is not None:
        mag *= 1.0 / np.sqrt(1.0 + (f / f_hi) ** 8)
    spec = (rng.standard_normal(f.size) + 1j * rng.standard_normal(f.size)) * mag
    x = np.fft.irfft(spec, n)
    return x / (np.std(x) + 1e-15)


def pink(n: int, rng) -> np.ndarray:
    return colored(n, rng, -3.0)


def brown(n: int, rng) -> np.ndarray:
    return colored(n, rng, -6.0)


def impulses(n: int, rng, rate: float, amp_sigma: float = 0.5) -> np.ndarray:
    """Sparse Poisson impulse train (rate per second) with log-normal amplitudes and random sign."""
    n = int(n)
    k = rng.poisson(rate * n / SR)
    x = np.zeros(n)
    if k:
        pos = rng.integers(0, n, k)
        amp = np.exp(rng.normal(0.0, amp_sigma, k)) * rng.choice([-1.0, 1.0], k)
        np.add.at(x, pos, amp)
    return x


# --------------------------------------------------------------------------- filters
def _clampf(f):
    nyq = SR / 2.0
    if np.ndim(f):
        return [float(min(max(fi, 1.0), nyq * 0.98)) for fi in f]
    return float(min(max(f, 1.0), nyq * 0.98))


def sos(kind: str, f, order: int = 2):
    return ss.butter(order, _clampf(f), btype=kind, fs=SR, output="sos")


def lp(x, f, order: int = 2):
    return ss.sosfilt(sos("lowpass", f, order), x, axis=-1)


def hp(x, f, order: int = 2):
    return ss.sosfilt(sos("highpass", f, order), x, axis=-1)


def bp(x, lo, hi, order: int = 2):
    return ss.sosfilt(sos("bandpass", [lo, hi], order), x, axis=-1)


def biquad(kind: str, f0: float, q: float = 0.707, gain_db: float = 0.0):
    """RBJ cookbook biquad coefficients (b, a)."""
    f0 = _clampf(f0)
    w0 = TWO_PI * f0 / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * q)
    A = 10.0 ** (gain_db / 40.0)
    if kind == "bp":  # constant 0 dB peak gain
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "notch":
        b = [1, -2 * cw, 1]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "lowshelf":
        sq = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sq)]
        a = [(A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sq]
    elif kind == "highshelf":
        sq = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sq)]
        a = [(A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sq]
    elif kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    else:
        raise ValueError(kind)
    b = np.asarray(b, dtype=np.float64)
    a = np.asarray(a, dtype=np.float64)
    return b / a[0], a / a[0]


def bq(x, kind: str, f0: float, q: float = 0.707, gain_db: float = 0.0):
    b, a = biquad(kind, f0, q, gain_db)
    return ss.lfilter(b, a, x, axis=-1)


def resonator(x, f0: float, tau: float):
    """Two-pole resonator; impulse response ~ sin(2*pi*f0*t) * exp(-t/tau) (unit amplitude)."""
    if f0 >= SR * 0.45:
        return np.zeros_like(x)
    r = np.exp(-1.0 / (max(tau, 1e-5) * SR))
    w = TWO_PI * f0 / SR
    return ss.lfilter([np.sin(w)], [1.0, -2.0 * r * np.cos(w), r * r], x, axis=-1)


def modal_bank(exc, modes):
    """Excite a bank of resonators. modes = [(freq_hz, tau_s, gain), ...]."""
    y = np.zeros_like(np.asarray(exc, dtype=np.float64))
    for f, tau, g in modes:
        y += g * resonator(exc, f, tau)
    return y


def modal_sines(n: int, modes, rng=None, attack: float = 0.0004) -> np.ndarray:
    """Direct sum of exponentially decaying sines. modes = [(freq, tau, amp), ...]."""
    t = tvec(n)
    y = np.zeros(n)
    for f, tau, a in modes:
        if f >= SR * 0.45:
            continue
        ph = 0.0 if rng is None else rng.uniform(0, TWO_PI)
        y += a * np.sin(TWO_PI * f * t + ph) * np.exp(-t / tau)
    if attack > 0:
        na = min(ns(attack), n)
        y[:na] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    return y


def sos_circular(sos_coefs, x, settle_s: float = 2.0):
    """Filter a periodic signal so the output is also periodic (pre-rolls with the signal's own end)."""
    n = x.shape[-1]
    p = min(n, ns(settle_s))
    ext = np.concatenate([x[..., n - p:], x], axis=-1)
    return ss.sosfilt(sos_coefs, ext, axis=-1)[..., p:]


def lfilter_circular(b, a, x, settle_s: float = 2.0):
    n = x.shape[-1]
    p = min(n, ns(settle_s))
    ext = np.concatenate([x[..., n - p:], x], axis=-1)
    return ss.lfilter(b, a, ext, axis=-1)[..., p:]


# --------------------------------------------------------------------------- time-varying spectral shaping
def stft_shape(x, gain_fn, nfft: int = 1024, hop: int = 256, circular: bool = False):
    """Apply a time-varying magnitude response. ``gain_fn(f, t)`` receives f (F,1) in Hz and t (1,T)
    in seconds (frame centres, in the signal's own timeline) and returns gains broadcastable to (F,T).
    With circular=True the signal is treated as periodic (gain_fn must then be periodic too)."""
    x = np.asarray(x, dtype=np.float64)
    n = x.shape[-1]
    if circular:
        p = min(n, 2 * nfft)
        xe = np.concatenate([x[..., n - p:], x, x[..., :p]], axis=-1)
        off = p
    else:
        xe = x
        off = 0
    f, t, Z = ss.stft(xe, fs=SR, window="hann", nperseg=nfft, noverlap=nfft - hop,
                      boundary="zeros", padded=True, axis=-1)
    t_sig = t - off / SR
    if circular:
        t_sig = np.mod(t_sig, n / SR)
    G = gain_fn(f[:, None], t_sig[None, :])
    _, y = ss.istft(Z * G, fs=SR, window="hann", nperseg=nfft, noverlap=nfft - hop, boundary=True,
                    time_axis=-1, freq_axis=-2)
    y = pad_to(y, xe.shape[-1])
    return y[..., off:off + n]


def band_gain(f, fc, bw_oct, floor: float = 0.0):
    """Log-Gaussian band centred on fc with a bandwidth (std-dev) in octaves."""
    lf = np.log2(np.maximum(f, 1.0) / np.maximum(fc, 1.0))
    return floor + (1.0 - floor) * np.exp(-0.5 * (lf / bw_oct) ** 2)


def lp_gain(f, fc, slope_oct: float = 2.0):
    """Smooth low-pass magnitude (Butterworth-like of order ``slope_oct``)."""
    return 1.0 / np.sqrt(1.0 + (np.maximum(f, 0.0) / np.maximum(fc, 1.0)) ** (2 * slope_oct))


def curve(times, values, log: bool = False):
    """Return a function t -> interpolated value (log-domain interpolation when log=True)."""
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if log:
        lv = np.log(values)
        return lambda t: np.exp(np.interp(t, times, lv))
    return lambda t: np.interp(t, times, values)


# --------------------------------------------------------------------------- oscillators
def _as_freq(freq, n):
    f = np.asarray(freq, dtype=np.float64)
    if f.ndim == 0:
        return np.full(int(n), float(f))
    return pad_to(f, int(n)) if f.size != n else f


def phase_cycles(freq, n: int, ph0: float = 0.0) -> np.ndarray:
    """Instantaneous phase in cycles for a (possibly time-varying) frequency, starting at ph0."""
    f = _as_freq(freq, n)
    ph = np.empty(n)
    ph[0] = 0.0
    np.cumsum(f[:-1] / SR, out=ph[1:])
    return ph + ph0


def osc_sine(freq, n: int, ph0: float = 0.0) -> np.ndarray:
    return np.sin(TWO_PI * phase_cycles(freq, n, ph0))


def _polyblep(t, dt):
    y = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    y[m] = x + x - x * x - 1.0
    m = t > 1.0 - dt
    x = (t[m] - 1.0) / dt[m]
    y[m] = x * x + x + x + 1.0
    return y


def osc_saw(freq, n: int, ph0: float = 0.0) -> np.ndarray:
    """Band-limited (polyBLEP) sawtooth in [-1, 1]."""
    f = _as_freq(freq, n)
    dt = np.clip(f / SR, 1e-9, 0.5)
    t = np.mod(phase_cycles(f, n, ph0), 1.0)
    return 2.0 * t - 1.0 - _polyblep(t, dt)


def osc_square(freq, n: int, ph0: float = 0.0, duty: float = 0.5) -> np.ndarray:
    """Band-limited (polyBLEP) pulse wave."""
    f = _as_freq(freq, n)
    dt = np.clip(f / SR, 1e-9, 0.5)
    t = np.mod(phase_cycles(f, n, ph0), 1.0)
    y = np.where(t < duty, 1.0, -1.0)
    y += _polyblep(t, dt)
    y -= _polyblep(np.mod(t + 1.0 - duty, 1.0), dt)
    return y


def osc_tri(freq, n: int, ph0: float = 0.0) -> np.ndarray:
    """Naive triangle (continuous waveform, harmonics fall at 12 dB/oct, so aliasing is low)."""
    f = _as_freq(freq, n)
    t = np.mod(phase_cycles(f, n, ph0), 1.0)
    return 4.0 * np.abs(t - 0.5) - 1.0


def harmonic_tone(f0, n: int, amps, phases=None, fmax: float = 0.45 * SR) -> np.ndarray:
    """Additive band-limited tone; harmonics above ``fmax`` (instantaneous) are muted."""
    f = _as_freq(f0, n)
    base = TWO_PI * phase_cycles(f, n)
    y = np.zeros(n)
    fmin_, fmax_ = float(np.min(f)), float(np.max(f))
    for k, a in enumerate(amps, start=1):
        if a == 0.0:
            continue
        if k * fmin_ >= fmax:
            break
        ph = 0.0 if phases is None else phases[k - 1]
        comp = a * np.sin(k * base + ph)
        if k * fmax_ > fmax:
            comp *= np.clip((fmax - k * f) / (0.02 * fmax), 0.0, 1.0)
        y += comp
    return y


def fm_tone(freq, n: int, ratio: float, index, ph0: float = 0.0) -> np.ndarray:
    """Two-operator FM (phase modulation). ``index`` may be an array (envelope)."""
    f = _as_freq(freq, n)
    mod = np.sin(TWO_PI * phase_cycles(f * ratio, n)) * index
    return np.sin(TWO_PI * phase_cycles(f, n, ph0) + mod)


def glide(n: int, f_start: float, f_end: float, tau: float) -> np.ndarray:
    """Exponential frequency glide from f_start towards f_end with time constant tau."""
    t = tvec(n)
    return f_end + (f_start - f_end) * np.exp(-t / max(tau, 1e-6))


# --------------------------------------------------------------------------- reverb
def synth_ir(rng, t60: float = 1.2, dur: float | None = None, predelay: float = 0.01, stereo: bool = True,
             damp_hz: float = 7000.0, early: int = 8, er_span: float = 0.045, er_gain: float = 0.5,
             lo_mult: float = 1.2, hi_mult: float = 0.5) -> np.ndarray:
    """Synthetic room impulse response: sparse early reflections + exponentially decaying noise
    tail with frequency-dependent decay (low band longer, high band shorter). Unit energy."""
    dur = dur if dur is not None else min(t60 * 1.15 + predelay, 8.0)
    n = ns(dur)
    t = tvec(n)
    chans = 2 if stereo else 1
    out = np.zeros((chans, n))
    npd = ns(predelay)
    for c in range(chans):
        nz = rng.standard_normal(n)
        lo = lp(nz, 500.0, 2)
        mid = bp(nz, 500.0, 4000.0, 2)
        hi = hp(nz, 4000.0, 2)
        tail = (lo * 10 ** (-3 * t / (t60 * lo_mult)) + mid * 10 ** (-3 * t / t60)
                + hi * 10 ** (-3 * t / (t60 * hi_mult)))
        tail = lp(tail, damp_hz, 1)
        tail *= np.clip(t / 0.025, 0.0, 1.0) ** 2
        er = np.zeros(n)
        for _ in range(early):
            d = rng.uniform(0.003, er_span)
            k = ns(d)
            if k < n:
                er[k] += rng.uniform(0.35, 1.0) * rng.choice([-1.0, 1.0]) * np.exp(-d / 0.04)
        er = lp(er, damp_hz * 0.8, 1)
        tail /= np.sqrt(np.sum(tail ** 2)) + 1e-12
        if np.any(er):
            er /= np.sqrt(np.sum(er ** 2)) + 1e-12
        ir = (1.0 - er_gain) * tail + er_gain * er
        out[c, npd:] = ir[: n - npd]
    out /= np.sqrt(np.sum(out ** 2) / chans) + 1e-12
    return out if stereo else out[0]


def convolve(x, ir):
    """Linear convolution. mono x + mono ir -> mono; mono x + stereo ir -> stereo; stereo x + stereo ir -> stereo."""
    x = np.asarray(x, dtype=np.float64)
    ir = np.asarray(ir, dtype=np.float64)
    if x.ndim == 1 and ir.ndim == 1:
        return ss.fftconvolve(x, ir)
    if x.ndim == 1:
        return np.stack([ss.fftconvolve(x, ir[c]) for c in range(ir.shape[0])])
    if ir.ndim == 1:
        return np.stack([ss.fftconvolve(x[c], ir) for c in range(x.shape[0])])
    return np.stack([ss.fftconvolve(x[c], ir[c]) for c in range(x.shape[0])])


def conv_circular(x, ir):
    """Circular convolution (tail wraps to the start): for seamless loops."""
    n = x.shape[-1]
    return wrap_to(convolve(x, ir), n)


def add_reverb(x, ir, wet: float, dry: float = 1.0, tail: bool = True):
    """Dry + wet (linear conv). Output is extended by the IR length when tail=True."""
    w = convolve(x, ir)
    if x.ndim == 1 and w.ndim == 2:
        d = np.stack([x, x])
    else:
        d = x
    out = wet * w
    out[..., : d.shape[-1]] += dry * d
    return out if tail else out[..., : x.shape[-1]]


# --------------------------------------------------------------------------- dynamics
def softclip(x, drive: float = 1.5):
    return np.tanh(drive * x) / np.tanh(drive)


def limiter(x, ceiling: float, win_ms: float = 1.5, circular: bool = False):
    """Zero-overshoot look-ahead limiter: box-minimum of the required gain followed by a box
    average (guarantees |y| <= ceiling). Stereo is gain-linked."""
    x = np.asarray(x, dtype=np.float64)
    a = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), axis=0)
    g = np.minimum(1.0, ceiling / np.maximum(a, 1e-12))
    if np.all(g >= 1.0):
        return x.copy()
    w = max(1, int(win_ms * 1e-3 * SR))
    mode = "wrap" if circular else "nearest"
    gmin = minimum_filter1d(g, size=2 * w + 1, mode=mode)
    h = max(1, w // 2)
    gs = uniform_filter1d(gmin, size=2 * h + 1, mode=mode)
    gs = np.minimum(gs, g)  # numerical safety
    return x * gs


def envelope_follow(x, tau: float):
    """Smoothed RMS envelope (one-pole on the power)."""
    a = np.exp(-1.0 / (tau * SR))
    p = x ** 2 if x.ndim == 1 else np.mean(x ** 2, axis=0)
    return np.sqrt(np.maximum(ss.lfilter([1 - a], [1, -a], p), 0.0))


# --------------------------------------------------------------------------- measurement
def gated_rms_db(x, block_s: float = 0.02, hop_s: float = 0.005, gate_db: float = -15.0) -> float:
    """'RMS of the loud part': mean power of the blocks within ``gate_db`` of the loudest block."""
    x = np.asarray(x, dtype=np.float64)
    p = x ** 2 if x.ndim == 1 else np.mean(x ** 2, axis=0)
    b = ns(block_s)
    h = ns(hop_s)
    if p.size <= b:
        return float(10 * np.log10(np.mean(p) + 1e-20))
    cs = np.concatenate([[0.0], np.cumsum(p)])
    starts = np.arange(0, p.size - b + 1, h)
    bpow = (cs[starts + b] - cs[starts]) / b
    sel = bpow >= bpow.max() * 10 ** (gate_db / 10.0)
    return float(10 * np.log10(np.mean(bpow[sel]) + 1e-20))


def peak_db(x) -> float:
    return float(a2db(np.max(np.abs(x))))


# --------------------------------------------------------------------------- loops
def wrap_to(buf, n: int):
    """Fold everything beyond sample n back onto the start (loop tail wrap)."""
    n = int(n)
    out = np.array(buf[..., :n], dtype=np.float64, copy=True)
    if out.shape[-1] < n:
        return pad_to(out, n)
    k = n
    total = buf.shape[-1]
    while k < total:
        seg = buf[..., k:k + n]
        out[..., : seg.shape[-1]] += seg
        k += n
    return out


def periodic_curve(n: int, rng, harmonics: int = 6, lo: float = 0.0, hi: float = 1.0,
                   slope: float = 1.0, rate: float = 100.0) -> np.ndarray:
    """Smooth random periodic curve (period = n samples) scaled to [lo, hi]."""
    m = max(8, int(n / SR * rate))
    k = np.arange(1, harmonics + 1)
    coef = (rng.standard_normal(harmonics) + 1j * rng.standard_normal(harmonics)) / k ** slope
    spec = np.zeros(m // 2 + 1, dtype=complex)
    kk = min(harmonics, spec.size - 1)
    spec[1:kk + 1] = coef[:kk]
    c = np.fft.irfft(spec, m)
    c = (c - c.min()) / (c.max() - c.min() + 1e-15)
    xs = np.arange(m + 1) * (n / m)
    full = np.interp(np.arange(n), xs, np.append(c, c[0]))
    return lo + (hi - lo) * full


def seam_stats(x) -> dict:
    """Loop-seam statistics for a (channels, n) or mono signal."""
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    res = []
    for ch in x:
        d = np.abs(np.diff(ch))
        jump = abs(ch[0] - ch[-1])
        res.append((jump, float(np.percentile(d, 99.9)), float(np.median(d))))
    return {"jump": max(r[0] for r in res), "p999": min(r[1] for r in res), "median": min(r[2] for r in res)}


# --------------------------------------------------------------------------- file output
def write_wav16(path, x) -> None:
    """Write mono/stereo float [-1,1] as 16-bit PCM WAV (explicit rounding, deterministic)."""
    x = np.asarray(x, dtype=np.float64)
    data = x.T if x.ndim == 2 else x
    q = np.clip(np.round(data * 32767.0), -32768, 32767).astype(np.int16)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), q, SR, subtype="PCM_16", format="WAV")


_BITREV8 = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def _bitrev32(v: int) -> int:
    return int(f"{v:032b}"[::-1], 2)


def ogg_crc(page: bytes) -> int:
    """Ogg page CRC (poly 0x04C11DB7, init 0, no reflection, no final xor) computed via zlib's
    reflected CRC-32 on bit-reversed bytes."""
    raw = zlib.crc32(page.translate(_BITREV8), 0xFFFFFFFF) ^ 0xFFFFFFFF
    return _bitrev32(raw)


def normalize_ogg_serial(path, serial: int = 0x57524131) -> int:
    """Rewrite the (randomly chosen) Ogg bitstream serial number to a constant and recompute each
    page CRC, making the encoded file byte-reproducible. Verifies every original CRC first."""
    b = bytearray(Path(path).read_bytes())
    i = 0
    pages = 0
    while i < len(b):
        if b[i:i + 4] != b"OggS":
            raise ValueError(f"{path}: bad Ogg capture pattern at byte {i}")
        nseg = b[i + 26]
        body = sum(b[i + 27:i + 27 + nseg])
        length = 27 + nseg + body
        stored = int.from_bytes(b[i + 22:i + 26], "little")
        b[i + 22:i + 26] = b"\0\0\0\0"
        if ogg_crc(bytes(b[i:i + length])) != stored:
            raise ValueError(f"{path}: Ogg CRC self-test failed on page {pages}")
        b[i + 14:i + 18] = int(serial).to_bytes(4, "little")
        b[i + 22:i + 26] = ogg_crc(bytes(b[i:i + length])).to_bytes(4, "little")
        i += length
        pages += 1
    Path(path).write_bytes(bytes(b))
    return pages


def write_ogg(path, x, quality_level: float = 0.5, title: str | None = None) -> None:
    """Write a (2, n) float signal as Ogg Vorbis (libsndfile) with a fixed stream serial.
    ``quality_level`` is soundfile's compression_level (0 = best quality, 1 = smallest)."""
    x = np.asarray(x, dtype=np.float64)
    data = x.T if x.ndim == 2 else x
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sf.SoundFile(str(path), "w", samplerate=SR, channels=data.shape[1] if data.ndim == 2 else 1,
                      format="OGG", subtype="VORBIS", compression_level=quality_level) as f:
        if title:
            f.title = title
        f.comment = "Original procedural synthesis (WILDRUSH tools/audio). No samples."
        f.write(data.astype(np.float32))
    normalize_ogg_serial(path)
