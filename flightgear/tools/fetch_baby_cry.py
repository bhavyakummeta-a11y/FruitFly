"""Build the crying-baby sound for the cabin gag from a real, CC0 recording.

Source: "Crying newborn baby" by the_yura (via Freesound), CC0 1.0 (public domain
dedication), https://commons.wikimedia.org/wiki/File:Crying_newborn_baby.ogg
Credit is in flightgear/Aircraft/FlyCabin/Sounds/CREDITS.md.

Writes flightgear/Aircraft/FlyCabin/Sounds/baby-cry-1.wav .. baby-cry-5.wav: the
recording cut at its natural pauses into five short cries (2.5-5 s; the silent stretch
3.4-8.0 s is dropped), short fades, mono, 22.05 kHz, 16-bit, one shared gain (loudest
peak 0.85). cabin_show.nas plays a random clip after the last one ends while the baby
(a fly larva) cries and the viewer is in a cabin view. Short clips mean it falls quiet
within seconds of getting its pacifier (FlightGear can't stop a playing sample).
CRY_CLIPS in cabin_show.nas lists the clip lengths; tests check they match.

Run:  python flightgear/tools/fetch_baby_cry.py [--input local.ogg]
Needs `pip install soundfile` (decodes OGG); the WAV clips are committed, so nobody
else has to run this.
"""
import argparse
import os
import tempfile
import urllib.request
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "Aircraft", "FlyCabin", "Sounds")
URL = "https://upload.wikimedia.org/wikipedia/commons/2/2b/Crying_newborn_baby.ogg"
SIZE = 510174                     # bytes, as published on Commons
CLIPS = ((0.0, 3.4), (8.0, 12.3), (12.3, 17.5), (17.5, 20.0), (20.0, 23.0))  # seconds of the source
FADE = 0.06                       # fade in/out at each clip's ends (s)
RATE = 22050


def lowpass_halve(y):
    """44.1 -> 22.05 kHz: windowed-sinc low-pass at 10 kHz, then drop every other sample."""
    n = np.arange(-32, 33)
    h = np.sinc(2 * 10000 / 44100 * n) * np.hamming(len(n))
    return np.convolve(y, h / h.sum(), mode="same")[::2]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", help="local copy of the source .ogg (skips the download)")
    a = ap.parse_args()
    import soundfile as sf
    src = a.input
    if not src:
        src = os.path.join(tempfile.mkdtemp(prefix="babycry-"), "crying_newborn_baby.ogg")
        req = urllib.request.Request(URL, headers={"User-Agent": "FruitFly-sim-asset-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(src, "wb") as f:
            f.write(r.read())
    if os.path.getsize(src) != SIZE:
        raise SystemExit(f"{src}: {os.path.getsize(src)} bytes, expected {SIZE} (file changed upstream?)")
    y, sr = sf.read(src)
    if sr != 44100:
        raise SystemExit(f"expected 44.1 kHz, got {sr}")
    y = y.mean(axis=1) if y.ndim > 1 else y
    f = int(FADE * sr)
    ramp = np.linspace(0, 1, f)
    clips = []
    for start, end in CLIPS:
        seg = y[int(start * sr):int(end * sr)].copy()
        seg[:f] *= ramp
        seg[-f:] *= ramp[::-1]
        clips.append(lowpass_halve(seg))
    gain = 0.85 / max(np.abs(c).max() for c in clips)
    os.makedirs(OUT_DIR, exist_ok=True)
    for i, clip in enumerate(clips, 1):
        path = os.path.join(OUT_DIR, f"baby-cry-{i}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((clip * gain * 32767).astype("<i2").tobytes())
        print(f"{len(clip) / RATE:.2f} s -> {os.path.normpath(path)}")


if __name__ == "__main__":
    main()
