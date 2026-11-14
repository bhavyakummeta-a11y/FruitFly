"""Download the stock FGAddon Boeing 737-800 and install our fly-passenger overlay.

    python flightgear/setup_aircraft.py

Result (flightgear/Aircraft/ is what you pass to --fg-aircraft):
    flightgear/Aircraft/737-800/                stock aircraft (committed, ~46 MB; re-downloaded only if missing)
    flightgear/Aircraft/737-800/738-flies-set.xml   copied from overlay/
    flightgear/Aircraft/FlyCabin/               our cabin + fly models (committed)

Safe to re-run: the download is skipped if the right version is already there,
and the overlay set file is always re-copied so edits in overlay/ take effect.
"""
import hashlib
import os
import shutil
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
AIRCRAFT = os.path.join(HERE, "Aircraft")
CACHE = os.path.join(HERE, "downloads")

# FGAddon "Aircraft-2024" catalog entry for package id 738 (dir 737-800), checked 2026-11-14
URLS = ["https://fgaddon.b-cdn.net/Aircraft-2024/737-800.zip",
        "http://mirrors.ibiblio.org/flightgear/ftp/Aircraft-2024/737-800.zip"]
MD5 = "31048f5a6efee5bfc1e7bbf3010485ae"
STAMP = os.path.join(AIRCRAFT, "737-800", ".fruitfly-md5")


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(dest):
    for url in URLS:
        try:
            print(f"Downloading {url} ...")
            urllib.request.urlretrieve(url, dest)
            if md5(dest) == MD5:
                return
            print("  MD5 mismatch, trying next mirror")
        except OSError as e:
            print(f"  failed: {e}")
    sys.exit("Could not download a verified 737-800.zip. The FGAddon catalog may have "
             "a newer revision: update URLS/MD5 from "
             "https://mirrors.ibiblio.org/flightgear/ftp/Aircraft-2024/catalog.xml")


def main():
    os.makedirs(CACHE, exist_ok=True)
    target = os.path.join(AIRCRAFT, "737-800")
    have = os.path.exists(STAMP) and open(STAMP).read().strip() == MD5
    if not have:
        zpath = os.path.join(CACHE, "737-800.zip")
        if not (os.path.exists(zpath) and md5(zpath) == MD5):
            download(zpath)
        if os.path.isdir(target):
            shutil.rmtree(target)
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():   # refuse paths that escape Aircraft/
                if not os.path.abspath(os.path.join(AIRCRAFT, name)).startswith(
                        os.path.abspath(target)):
                    sys.exit(f"unexpected path in zip: {name}")
            z.extractall(AIRCRAFT)
        with open(STAMP, "w") as f:
            f.write(MD5)
        print(f"Installed stock 737-800 -> {target}")
    else:
        print("Stock 737-800 already installed")

    shutil.copy2(os.path.join(HERE, "overlay", "738-flies-set.xml"), target)
    print("Installed overlay -> 737-800/738-flies-set.xml (aircraft id: 738-flies)")


if __name__ == "__main__":
    main()
