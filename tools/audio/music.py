"""WILDRUSH music loops (stereo, seamless, original).

Restrained dark-esports mood: minor keys, detuned-saw pads, FM plucks/bells, synthesized drums,
sidechain-ducked bass and pads. Each track is sequenced on an integer samples-per-beat grid
(tempos chosen so 44100*60/bpm is an integer), rendered into buses that extend past the loop
end, then wrapped - so reverb/delay/release tails continue seamlessly into bar 1. The match
track has a presence dip (2-4 kHz) to leave room for gameplay SFX.

  music_menu     D minor, 90 BPM, 32 bars (85.3 s)  Dm9 | Bbmaj7 | Gm9 | A7sus4 A7
  music_select   E minor, 105 BPM, 20 bars (45.7 s) pedal-E ostinato; Em | Fmaj7#11/E | Em | B/E
  music_match    C minor, 126 BPM, 56 bars (106.7 s) Cm(add9) | Abmaj7 | Fm9 | G7sus4 G7
  music_results  84 BPM, 8 bars (22.9 s)             Fmaj9 | Em9 | Dm9 | Am9 | ... | Esus4 E7
"""
from __future__ import annotations

import numpy as np

from dsp import (SR, TWO_PI, biquad, conv_circular, db2a, env_pts, hp, hz, lfilter_circular, lp, mix_at, ns,
                 osc_saw, osc_sine, osc_tri, pan, rng_for, sos, sos_circular, synth_ir, tvec, wrap_to)
from instruments import (bell, brass, clap, crash, epiano, fm_pluck, glass, hat, kick, nrm, pluck_bass,
                         reverse_swell, riser, saw_pad, shaker, snare, sub_bass, sub_boom, tom)

REGISTRY: dict = {}


def cue(name):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


class Song:
    def __init__(self, name, bpm, bars, bpb=4, tail_s=10.0):
        spb = SR * 60.0 / bpm
        if abs(spb - round(spb)) > 1e-9:
            raise ValueError(f"{name}: {bpm} BPM does not give an integer samples-per-beat")
        self.spb = int(round(spb))
        self.bpb = bpb
        self.bars = bars
        self.N = bars * bpb * self.spb
        self.tail = ns(tail_s)
        self.buses: dict = {}
        self.rng = rng_for("music", name)
        self.kicks: list = []

    def beats(self, b):
        """Duration of b beats in seconds."""
        return b * self.spb / SR

    def pos(self, bar, beat=0.0):
        return int(round((bar * self.bpb + beat) * self.spb))

    def add(self, bus, x, bar, beat=0.0, gain_db=0.0, p=0.0, jitter_ms=0.0):
        if bus not in self.buses:
            self.buses[bus] = np.zeros((2, self.N + self.tail), dtype=np.float32)
        st = pan(x, p) if x.ndim == 1 else x
        pos = self.pos(bar, beat)
        if jitter_ms:
            pos += int(self.rng.normal(0.0, jitter_ms * 1e-3 * SR))
        mix_at(self.buses[bus], st, pos % self.N, float(db2a(gain_db)))
        return pos % self.N

    def kick(self, bar, beat, gain_db, **kw):
        k = kick(self.rng, **kw)
        self.kicks.append(self.add("drums", k, bar, beat, gain_db))

    def get(self, bus):
        if bus not in self.buses:
            return np.zeros((2, self.N))
        return wrap_to(self.buses[bus].astype(np.float64), self.N)

    def duck(self, depth, tau=0.12, att=0.005):
        """Sidechain gain curve (periodic) driven by the kick positions."""
        r = np.zeros(self.N + ns(1.0))
        m = ns(6 * tau)
        t = tvec(m)
        kern = np.minimum(t / att, 1.0) * np.exp(-np.maximum(t - att, 0) / tau)
        for p_ in self.kicks:
            mix_at(r, kern, p_)
        r = np.minimum(wrap_to(r, self.N), 1.0)
        return 1.0 - depth * r


def pingpong(x, delay, fb=0.38, repeats=4, lp_hz=4500.0):
    """Circular tempo-synced ping-pong echo (returns the echoes only)."""
    mono = x.mean(axis=0)
    out = np.zeros_like(x)
    g = 1.0
    for k in range(1, repeats + 1):
        g *= fb
        out[k % 2] += g * np.roll(mono, k * delay)
    return sos_circular(sos("lowpass", lp_hz, 2), out)


def hall(x, key, t60=2.4, wet=0.25, predelay=0.02):
    ir = synth_ir(rng_for("music_ir", key), t60=t60, stereo=True, predelay=predelay, er_gain=0.25)
    return (1 - 0.3 * wet) * x + wet * conv_circular(x, ir)


def room(x, key, t60=0.5, wet=0.12):
    ir = synth_ir(rng_for("music_room", key), t60=t60, stereo=True, predelay=0.005, er_gain=0.5)
    return (1 - 0.3 * wet) * x + wet * conv_circular(x, ir)


def hpf(x, f=35.0):
    return sos_circular(sos("highpass", f, 2), x)


def eq(x, kind, f0, q, gain_db):
    b, a = biquad(kind, f0, q, gain_db)
    return lfilter_circular(b, a, x)


def soft_lead(f, dur, release=0.12, vib=0.004):
    """Mellow lead: triangle + sine (+ a little low-passed saw), delayed vibrato."""
    n = ns(dur + release)
    t = tvec(n)
    fv = f * (1 + vib * np.sin(TWO_PI * 5.0 * t) * np.clip((t - 0.15) / 0.2, 0, 1))
    y = 0.8 * osc_tri(fv, n) + 0.6 * osc_sine(fv, n) + 0.25 * lp(osc_saw(fv, n, 0.3), 2200.0, 2)
    amp = env_pts(n, [(0, 0), (0.012, 1), (min(0.2, dur), 0.85), (dur, 0.8), (dur + release, 0)])
    return y * amp


def H(names):
    return [hz(n) for n in names]


def layer(*parts):
    """Sum (gain, signal) pairs of different lengths (zero-padded to the longest)."""
    n = max(x.shape[-1] for _, x in parts)
    out = np.zeros(n)
    for g, x in parts:
        out[: x.shape[-1]] += g * x
    return out


def arp16(tones):
    """16-step arpeggio pattern over (up to 5) chord tones."""
    c = list(tones) + [tones[-1]] * (5 - len(tones))
    return [c[0], c[1], c[2], c[3], c[2], c[1], c[0], c[1], c[0], c[1], c[2], c[4], c[2], c[1], c[0], c[1]]


# ============================================================================ MENU
@cue("music_menu")
def music_menu(v, rng):
    S = Song("menu", 90, 32)
    r = S.rng
    blocks = [
        ("D2", ["F3", "A3", "C4", "E4"], ["D4", "F4", "A4", "C5", "E5", "C5", "A4", "F4"]),
        ("Bb1", ["F3", "A3", "D4", "F4"], ["Bb3", "D4", "F4", "A4", "D5", "A4", "F4", "D4"]),
        ("G1", ["F3", "Bb3", "D4", "A4"], ["G3", "Bb3", "D4", "F4", "A4", "F4", "D4", "Bb3"]),
        ("A1", ["G3", "D4", "E4", "A4"], ["A3", "D4", "E4", "G4", "A4", "G4", "E4", "D4"]),
    ]
    a7 = (["G3", "C#4", "E4", "A4"], ["A3", "C#4", "E4", "G4", "A4", "G4", "E4", "C#4"])
    cut = [1800.0, 2400.0, 3200.0, 2000.0]
    bar_s = S.beats(4)
    for cyc in range(4):
        for b, (root, pad_v, arp_v) in enumerate(blocks):
            bar0 = cyc * 8 + b * 2
            bars = [(bar0, pad_v, arp_v)] if b < 3 else [(bar0, pad_v, arp_v), (bar0 + 1, *a7)]
            for i, (bar, pv, av) in enumerate(bars):
                length = 2 * bar_s if b < 3 else bar_s
                S.add("pad", saw_pad(H(pv), length, r, cutoff=cut[cyc], attack=0.6, release=1.2, detune=10.0),
                      bar, 0, -2)
                # arpeggio (8ths) in cycles 1-3
                if cyc >= 1:
                    for rep in range(2 if b < 3 else 1):
                        for k, nt in enumerate(av):
                            vel = -5 if k % 2 == 0 else -8
                            vel += -3 if cyc == 3 else 0
                            S.add("keys", fm_pluck(hz(nt), 0.5, index=2.2 if cyc < 3 else 1.4, decay=0.22),
                                  bar + rep, 0.5 * k, vel, p=0.3 if k % 2 else -0.3, jitter_ms=2)
            # bass
            f = hz(root)
            if cyc in (0, 3):
                S.add("bass", sub_bass(f, 2 * bar_s - 0.05, attack=0.02, release=0.2), bar0, 0, -6)
            else:
                for bar in (bar0, bar0 + 1):
                    for beat, dur, mult in ((0, 1.4, 1), (1.5, 0.45, 1), (2.5, 0.45, 2), (3.0, 0.9, 1)):
                        S.add("bass", pluck_bass(f * mult, S.beats(dur), cutoff0=900.0, cutoff1=220.0), bar, beat, -3)
    # drums
    for bar in range(32):
        cyc = bar // 8
        if cyc == 0:
            if bar % 2 == 0:
                S.kick(bar, 0, -6, f0=95.0, f1=42.0, amp_tau=0.2, click=0.1)
            if bar >= 4:
                for k in range(8):
                    S.add("drums", shaker(r), bar, 0.5 * k + (0.04 if k % 2 else 0), -20 if k % 2 else -16, p=-0.3)
        elif cyc in (1, 2):
            S.kick(bar, 0, -2)
            if bar % 2 == 1:
                S.kick(bar, 2.5, -6)
            S.add("drums", layer((0.7, nrm(snare(r, 0.35, 190.0, 0.4))), (0.6, clap(r))), bar, 2, -3)
            for k in range(8):
                vel = [-4, -12, -7, -12, -4, -12, -7, -10][k]
                S.add("drums", hat(r, 0.07), bar, 0.5 * k + (0.04 if k % 2 else 0), vel, p=0.25, jitter_ms=1.5)
            if bar % 4 == 3:
                S.add("drums", hat(r, 0.35, open_=True), bar, 3.5, -12, p=0.25)
        else:
            if bar % 2 == 0:
                S.kick(bar, 0, -3)
            for k in range(4):
                S.add("drums", hat(r, 0.06), bar, k, -13, p=0.25)
    # bell motif (cycle 0) and lead (cycle 2)
    for bar, nt in ((0, "A5"), (2, "F5"), (4, "D5"), (6, "E5"), (7, "C#5")):
        S.add("keys", bell(hz(nt), 3.0, tau=1.1, bright=0.5), bar, 0, -9)
    lead = [(16, 0, 1.5, "D5"), (16, 1.5, 0.5, "E5"), (16, 2, 2, "F5"), (17, 0, 2, "E5"), (17, 2, 2, "C5"),
            (18, 0, 1.5, "D5"), (18, 1.5, 0.5, "C5"), (18, 2, 2, "A4"), (19, 0, 2, "F4"), (19, 2, 2, "A4"),
            (20, 0, 1.5, "Bb4"), (20, 1.5, 0.5, "C5"), (20, 2, 2, "D5"), (21, 0, 2, "F5"), (21, 2, 1, "E5"),
            (21, 3, 1, "D5"), (22, 0, 3, "E5"), (22, 3, 1, "D5"), (23, 0, 2, "C#5"), (23, 2, 1, "E5"),
            (23, 3, 1, "A4")]
    for bar, beat, dur, nt in lead:
        S.add("lead", soft_lead(hz(nt), S.beats(dur) * 0.95), bar, beat, -6)
        S.add("lead", glass(hz(nt) * 2, 1.2, tau=0.4), bar, beat, -20)
    # transitions
    for target in (8, 16):
        sw = reverse_swell(r, S.beats(4))
        S.add("fx", sw, target, -4, -16)
    S.add("fx", sub_boom(1.6, 55.0, 38.0), 16, 0, -13)

    duck_pad = S.duck(0.3, 0.18)
    duck_bass = S.duck(0.45, 0.12)
    keys = S.get("keys")
    keys = hall(keys + pingpong(keys, S.pos(0, 0.75)), "menu_keys", 2.6, 0.3)
    lead_b = S.get("lead")
    lead_b = hall(lead_b + 0.8 * pingpong(lead_b, S.pos(0, 0.75)), "menu_lead", 2.6, 0.3)
    pad = hall(S.get("pad") * duck_pad, "menu_pad", 3.0, 0.3)
    drums = room(S.get("drums"), "menu_drums", 0.6, 0.12)
    bass = S.get("bass") * duck_bass
    fx = hall(S.get("fx"), "menu_fx", 2.5, 0.3)
    mix = (db2a(0) * drums + db2a(-1) * bass + db2a(-5) * pad + db2a(-4) * keys + db2a(-3) * lead_b
           + db2a(-6) * fx)
    return eq(hpf(mix, 35.0), "peak", 3000.0, 0.8, -1.5)


# ============================================================================ SELECT
@cue("music_select")
def music_select(v, rng):
    S = Song("select", 105, 20)
    r = S.rng
    chords = [["E3", "G3", "B3", "F#4"], ["F3", "A3", "B3", "E4"], ["E3", "G3", "B3", "E4"], ["D#3", "F#3", "B3", "D#4"]]
    bar_s = S.beats(4)
    for bar in range(20):
        cyc, pos_ = divmod(bar, 4)
        # pedal-E 16th ostinato with a filter that opens across each 4-bar cycle
        if not (16 <= bar <= 17):
            for k in range(16):
                c0 = 700.0 + 2600.0 * (pos_ * 16 + k) / 64.0
                note = hz("E2") if k % 4 != 2 else hz("E3")
                vel = -4 if k % 4 == 0 else -10
                S.add("ost", pluck_bass(note, S.beats(0.22), cutoff0=c0, cutoff1=180.0, tau=0.05), bar, 0.25 * k,
                      vel, p=0.0, jitter_ms=1)
        cutoff = [2100.0, 2500.0, 3200.0, 3600.0, 1900.0][cyc]
        S.add("pad", saw_pad(H(chords[pos_]), bar_s, r, cutoff=cutoff, attack=0.25, release=0.9, detune=12.0),
              bar, 0, -2)
        if pos_ == 0:
            S.add("bass", sub_bass(hz("E2"), 4 * bar_s - 0.05, attack=0.03, release=0.3), bar, 0, -7)
            S.add("fx", sub_boom(1.5, 60.0, 40.0), bar, 0, -15)
        # heartbeat kick
        if cyc >= 1 or bar % 2 == 0:
            S.kick(bar, 0, -4, f0=100.0, f1=46.0, amp_tau=0.13)
            S.kick(bar, 0.5, -9, f0=95.0, f1=46.0, amp_tau=0.11)
        if cyc >= 1 and bar < 18:
            for k in range(16):
                vel = [-8, -17, -13, -17][k % 4]
                S.add("drums", hat(r, 0.05), bar, 0.25 * k, vel, p=0.3, jitter_ms=1)
        if cyc == 3:
            for k in range(4):
                S.add("drums", hat(r, 0.3, open_=True), bar, k + 0.5, -17, p=-0.3)
        if cyc in (2, 3) and pos_ == 3:
            S.add("drums", tom(r, 98.0), bar, 3.0, -7, p=-0.3)
            S.add("drums", tom(r, 82.0), bar, 3.5, -6, p=0.3)
        if cyc == 3:
            S.add("pad", brass(H(["E2", "B2", "E3"]), S.beats(0.5), r, attack=0.02, release=0.25,
                               bright=(700.0, 1800.0, 900.0), vib_depth=0.0, scoop=0.0), bar, 0, -9)
    # counter-melody (cycles 2-3)
    for cyc in (2, 3):
        for pos_, nt in enumerate(("B5", "C6", "G5", "F#5")):
            S.add("keys", glass(hz(nt), 2.0, tau=0.6), cyc * 4 + pos_, 0, -12)
            S.add("keys", glass(hz(nt) / 2, 1.5, tau=0.5), cyc * 4 + pos_, 2, -18)
    # riser into the loop point
    S.add("fx", riser(r, 2 * bar_s, 250.0, 7000.0), 18, 0, -13)
    S.add("fx", reverse_swell(r, S.beats(3)), 0, -3, -14)
    S.add("drums", snare(r, 0.3, 200.0, 0.3), 19, 3.5, -12)

    duck_pad = S.duck(0.25, 0.15)
    ost = S.get("ost") * S.duck(0.4, 0.1)
    ost = ost + 0.5 * pingpong(ost, S.pos(0, 0.75), fb=0.3, repeats=3)
    keys = S.get("keys")
    keys = hall(keys + pingpong(keys, S.pos(0, 1.5)), "sel_keys", 2.8, 0.35)
    pad = hall(S.get("pad") * duck_pad, "sel_pad", 2.8, 0.3)
    drums = room(S.get("drums"), "sel_drums", 0.7, 0.15)
    fx = hall(S.get("fx"), "sel_fx", 2.0, 0.25)
    mix = (drums + db2a(-6) * ost + db2a(-3) * S.get("bass") + db2a(-5) * pad + db2a(-3) * keys + db2a(-5) * fx)
    return eq(hpf(mix, 38.0), "peak", 2800.0, 0.8, -2.0)


# ============================================================================ MATCH
@cue("music_match")
def music_match(v, rng):
    S = Song("match", 126, 56)
    r = S.rng
    blocks = [
        ("C2", ["G3", "C4", "D4", "Eb4"], ["C4", "Eb4", "G4", "D5", "Eb5"]),
        ("Ab1", ["G3", "C4", "Eb4", "Ab4"], ["Ab3", "C4", "Eb4", "G4", "C5"]),
        ("F2", ["Ab3", "C4", "Eb4", "G4"], ["F3", "Ab3", "C4", "Eb4", "G4"]),
        ("G1", ["G3", "C4", "D4", "F4"], ["G3", "C4", "D4", "F4", "G4"]),
    ]
    g7 = (["G3", "B3", "D4", "F4"], ["G3", "B3", "D4", "F4", "G4"])
    bar_s = S.beats(4)

    def section(bar):
        if bar < 8:
            return "intro"
        if bar < 24:
            return "A"
        if bar < 32:
            return "break"
        if bar < 48:
            return "A2"
        return "outro"

    pad_cut = {"intro": 1600.0, "A": 2400.0, "break": 3600.0, "A2": 3000.0, "outro": 1800.0}
    for bar in range(56):
        sec = section(bar)
        b = (bar % 8) // 2
        root, pv, av = blocks[b]
        if b == 3 and bar % 2 == 1:
            pv, av = g7
        # pads: one chord per bar (re-voiced every bar keeps the sweep smooth)
        S.add("pad", saw_pad(H(pv), bar_s, r, cutoff=pad_cut[sec], attack=0.12, release=0.5, detune=11.0),
              bar, 0, -2)
        f = hz(root)
        if sec == "break":
            if bar % 2 == 0:
                S.add("bass", sub_bass(f, 2 * bar_s - 0.05, attack=0.03, release=0.25), bar, 0, -3)
        else:
            for k, mult in enumerate((1, 1, 2, 1, 1, 1, 1.5, 2)):
                S.add("bass", pluck_bass(f * mult, S.beats(0.42), cutoff0=1400.0, cutoff1=200.0, tau=0.06),
                      bar, 0.5 * k, -3 if k % 2 == 0 else -6)
        # drums
        if sec != "break":
            S.kick(bar, 0, -2)
            S.kick(bar, 2, -3)
            if bar % 2 == 1:
                S.kick(bar, 2.75, -8)
            if bar % 4 == 3:
                S.kick(bar, 3.5, -7)
        if sec in ("A", "A2", "outro"):
            for beat in (1, 3):
                S.add("drums", layer((0.6, nrm(snare(r, 0.3, 200.0, 0.35))), (0.7, clap(r))), bar, beat, -3)
        steps = 16 if sec != "break" else 8
        for k in range(steps):
            beat = 4.0 * k / steps
            vel = [-6, -16, -11, -16][k % 4] if steps == 16 else [-10, -15][k % 2]
            S.add("drums", hat(r, 0.05), bar, beat, vel, p=0.25, jitter_ms=1)
        if sec == "A2":
            for beat in (1.5, 3.5):
                S.add("drums", hat(r, 0.3, open_=True), bar, beat, -14, p=0.25)
        # 16th arpeggio (A, A2, outro)
        if sec in ("A", "A2", "outro"):
            pat = arp16(H(av))
            vel0 = -7 if sec != "outro" else -11
            idx = 2.0 if sec != "outro" else 1.1
            for k, fnote in enumerate(pat):
                S.add("keys", fm_pluck(fnote * 2 if k in (3, 11) else fnote, 0.3, index=idx, decay=0.12),
                      bar, 0.25 * k, vel0 - (0 if k % 4 == 0 else 3), p=0.35 if k % 2 else -0.35, jitter_ms=1.5)
    # break: bell motif + riser + swells
    for i, nt in enumerate(("Eb5", "D5", "C5", "G4", "Ab4", "C5", "D5", "B4")):
        S.add("keys", bell(hz(nt), 2.6, tau=0.9, bright=0.6), 24 + i, 0, -6)
    S.add("fx", riser(r, 2 * bar_s, 300.0, 7000.0), 30, 0, -15)
    for target in (24, 32):
        S.add("fx", reverse_swell(r, S.beats(4)), target, -4, -15)
    S.add("fx", crash(r, 2.5, tau=0.8), 32, 0, -15)
    for target in (8, 32):
        S.add("fx", sub_boom(1.5, 58.0, 38.0), target, 0, -12)
    S.add("drums", tom(r, 110.0), 55, 3.0, -8, p=-0.3)
    S.add("drums", tom(r, 92.0), 55, 3.25, -8, p=0.0)
    S.add("drums", tom(r, 78.0), 55, 3.5, -7, p=0.3)
    # lead motif (A2): two passes of an 8-bar phrase
    phrase = [(0, 0, 1, "G4"), (0, 1, 1, "C5"), (0, 2, 1, "D5"), (0, 3, 1, "Eb5"), (1, 0, 2, "D5"),
              (1, 2, 1, "C5"), (1, 3, 1, "G4"), (2, 0, 1, "Ab4"), (2, 1, 1, "C5"), (2, 2, 1.5, "Eb5"),
              (2, 3.5, 0.5, "D5"), (3, 0, 3, "C5"), (3, 3, 1, "Bb4"), (4, 0, 1, "Ab4"), (4, 1, 1, "C5"),
              (4, 2, 1.5, "F5"), (4, 3.5, 0.5, "Eb5"), (5, 0, 2, "D5"), (5, 2, 1, "C5"), (5, 3, 1, "Ab4"),
              (6, 0, 2, "G4"), (6, 2, 2, "C5"), (7, 0, 2, "B4"), (7, 2, 1, "D5"), (7, 3, 1, "G4")]
    for start in (32, 40):
        for bar, beat, dur, nt in phrase:
            if start == 40 and bar == 7:
                continue
            S.add("lead", soft_lead(hz(nt), S.beats(dur) * 0.92), start + bar, beat, -5)
        if start == 40:
            S.add("lead", soft_lead(hz("B4"), S.beats(2) * 0.92), 47, 0, -5)
            S.add("lead", soft_lead(hz("D5"), S.beats(2) * 0.92), 47, 2, -5)

    duck_pad = S.duck(0.35, 0.15)
    duck_bass = S.duck(0.55, 0.1)
    keys = S.get("keys")
    keys = hp(keys, 250.0, 2)
    keys = hall(keys + pingpong(keys, S.pos(0, 0.75), fb=0.33, repeats=3), "match_keys", 2.2, 0.25)
    lead_b = S.get("lead")
    lead_b = hall(lead_b + 0.7 * pingpong(lead_b, S.pos(0, 0.75)), "match_lead", 2.2, 0.28)
    pad = hall(S.get("pad") * duck_pad, "match_pad", 2.4, 0.25)
    drums = room(S.get("drums"), "match_drums", 0.5, 0.1)
    bass = S.get("bass") * duck_bass
    fx = hall(S.get("fx"), "match_fx", 2.2, 0.3)
    mix = (drums + db2a(-1.5) * bass + db2a(-7) * pad + db2a(-6) * keys + db2a(-4) * lead_b + db2a(-5) * fx)
    # leave room for gameplay SFX: presence dip + slightly softened top
    return eq(hpf(mix, 35.0), "peak", 2800.0, 0.7, -3.0)


# ============================================================================ RESULTS
@cue("music_results")
def music_results(v, rng):
    S = Song("results", 84, 8)
    r = S.rng
    prog = [("F2", ["A3", "C4", "E4", "G4"]), ("E2", ["G3", "B3", "D4", "F#4"]), ("D2", ["F3", "A3", "C4", "E4"]),
            ("A1", ["G3", "B3", "C4", "E4"]), ("F2", ["A3", "C4", "E4", "G4"]), ("E2", ["G3", "B3", "D4", "F#4"]),
            ("D2", ["F3", "A3", "C4", "E4"]), ("E2", ["E3", "A3", "B3", "D4"])]
    bar_s = S.beats(4)
    for bar, (root, keys) in enumerate(prog):
        halves = [(0.0, keys, 4.0)] if bar < 7 else [(0.0, keys, 2.0), (2.0, ["E3", "G#3", "B3", "D4"], 2.0)]
        for beat0, kv, length in halves:
            for k, nt in enumerate(kv):
                S.add("keys", epiano(hz(nt), S.beats(length) * 0.95, vel=0.75, decay=1.6), bar, beat0 + 0.02 * k, -3,
                      p=-0.2 + 0.13 * k)
            if length == 4.0:
                for k, nt in enumerate(kv[1:]):
                    S.add("keys", epiano(hz(nt), S.beats(1.4), vel=0.45, decay=0.9), bar, 2.5 + 0.02 * k, -9,
                          p=0.2 - 0.1 * k)
        S.add("pad", saw_pad(H(keys[:3]), bar_s, r, cutoff=2200.0, attack=0.5, release=1.0, detune=8.0), bar, 0, -6)
        S.add("bass", sub_bass(hz(root), bar_s - 0.05, attack=0.02, release=0.3), bar, 0, -5)
        S.kick(bar, 0, -7, f0=90.0, f1=42.0, amp_tau=0.18, click=0.05)
        S.kick(bar, 2.5, -12, f0=90.0, f1=42.0, amp_tau=0.15, click=0.05)
        for beat in (1, 3):
            S.add("drums", lp(snare(r, 0.12, 330.0, 0.8, noise_tau=0.02), 7000.0, 2), bar, beat, -11, p=0.15)
        for k in range(8):
            S.add("drums", shaker(r), bar, 0.5 * k + (0.05 if k % 2 else 0), -10 if k % 2 == 0 else -14, p=-0.3,
                  jitter_ms=2)
    melody = [(0, 0, 1.5, "A5"), (0, 1.5, 0.5, "G5"), (0, 2, 2, "E5"), (1, 0, 2, "D5"), (1, 2, 2, "B4"),
              (2, 0, 1.5, "C5"), (2, 1.5, 0.5, "D5"), (2, 2, 2, "F5"), (3, 0, 4, "E5"), (4, 0, 1.5, "A5"),
              (4, 1.5, 0.5, "B5"), (4, 2, 2, "C6"), (5, 0, 2, "B5"), (5, 2, 2, "G5"), (6, 0, 1.5, "A5"),
              (6, 1.5, 0.5, "F5"), (6, 2, 2, "D5"), (7, 0, 2, "E5"), (7, 2, 2, "G#5")]
    for bar, beat, dur, nt in melody:
        S.add("lead", bell(hz(nt), S.beats(dur) + 1.2, tau=0.7, bright=0.9), bar, beat, -3)

    keys = hall(S.get("keys"), "res_keys", 2.2, 0.25)
    lead_b = S.get("lead")
    lead_b = hall(lead_b + 0.6 * pingpong(lead_b, S.pos(0, 1.5), fb=0.3, repeats=3), "res_lead", 2.6, 0.3)
    pad = hall(S.get("pad") * S.duck(0.15, 0.2), "res_pad", 2.6, 0.3)
    drums = room(S.get("drums"), "res_drums", 0.6, 0.15)
    mix = (db2a(-2) * drums + db2a(-3) * S.get("bass") + db2a(-7) * pad + keys + db2a(-3) * lead_b)
    mix = eq(hpf(mix, 40.0), "peak", 260.0, 0.8, -2.5)
    return eq(mix, "highshelf", 4000.0, 0.7, 4.0)
