"""Synthesize the crying-baby sample for the cabin gag (no recordings, no licences).

Writes flightgear/Aircraft/FlyCabin/Sounds/baby-cry.wav: about 4 s, 22.05 kHz mono
16-bit. Three "waaah" wails, each with a rising-then-falling pitch, a wobble, and
vowel-like formants, plus short gasping in-breaths between them. cabin_show.nas plays
it in a loop while the baby (a fly larva) cries and the viewer is in a cabin view.

Run:  python flightgear/tools/make_baby_cry.py   (output is committed)
"""
import os
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "Aircraft", "FlyCabin", "Sounds", "baby-cry.wav")
RATE = 22050
SEED = 7


def wail(dur, f_start, f_peak, f_end, rng):
    n = int(dur * RATE)
    t = np.arange(n) / RATE
    u = t / dur
    # pitch contour: up to the peak at 30%, then down; 5-7 Hz wobble and a little jitter
    f0 = np.where(u < 0.3, f_start + (f_peak - f_start) * (u / 0.3),
                  f_peak + (f_end - f_peak) * ((u - 0.3) / 0.7))
    f0 = f0 * (1 + 0.025 * np.sin(2 * np.pi * rng.uniform(5, 7) * t)) \
            * (1 + 0.006 * rng.standard_normal(n).cumsum() / np.sqrt(np.arange(1, n + 1)))
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    # "waa" vowel: formants near 1.0, 1.6 and 3.0 kHz (a baby's small vocal tract)
    formants = ((1000, 260, 1.0), (1650, 300, 0.7), (3000, 450, 0.35))
    y = np.zeros(n)
    for h in range(1, 16):
        fh = h * f0
        gain = sum(a * np.exp(-0.5 * ((fh - fc) / bw) ** 2) for fc, bw, a in formants) + 0.15 / h
        y += gain * np.sin(h * phase) * (fh < RATE / 2 - 500)
    # attack, slow sag, then a choked cut-off
    env = np.minimum(1, u / 0.06) * (1 - 0.35 * u) * np.minimum(1, (1 - u) / 0.12)
    rough = 1 + 0.25 * np.convolve(rng.standard_normal(n), np.ones(40) / 40, mode="same")
    return y * env * rough


def gasp(dur, rng):
    n = int(dur * RATE)
    noise = rng.standard_normal(n)
    noise = np.convolve(noise, np.ones(6) / 6, mode="same") - np.convolve(noise, np.ones(60) / 60, mode="same")
    u = np.arange(n) / n
    return 0.25 * noise * np.sin(np.pi * u) ** 2


def main():
    rng = np.random.default_rng(SEED)
    parts = []
    for dur, a, b, c in ((1.15, 420, 560, 380), (0.9, 450, 600, 420), (1.35, 400, 540, 340)):
        parts += [wail(dur, a, b, c, rng), gasp(0.28, rng), np.zeros(int(0.08 * RATE))]
    y = np.concatenate(parts)
    y = 0.8 * y / np.abs(y).max()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with wave.open(OUT, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    print(f"{len(y) / RATE:.1f} s -> {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
