"""Download the twelve source files and verify the reviewed snapshot.

Default: original portfolio's immutable GitHub commit, to reproduce this run.
--source tlc tries the official URLs; changed contents fail checksum validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

COMMIT = "b3bdf9d213cda1efcd5477cb505cb47f422532b8"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", choices=["snapshot", "tlc"], default="snapshot")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "data/processed/source_manifest.json").read_text())
target_dir = root / "data/raw/taxi"
target_dir.mkdir(parents=True, exist_ok=True)
for item in manifest:
    name = item["file"]
    if not name.endswith(".parquet"):
        continue
    target = target_dir / name
    def file_hash(path):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    if target.exists():
        if file_hash(target) != item["sha256"]:
            raise ValueError(f"Existing {target.name} differs from reviewed data; preserve it and investigate.")
        print(f"Verified existing {name}", flush=True)
        continue
    url = (f"https://d37ci6vzurychx.cloudfront.net/trip-data/{name}" if args.source == "tlc"
           else f"https://raw.githubusercontent.com/Legari92/nyc-taxi-operational-analysis/{COMMIT}/data/raw/taxi/{name}")
    temporary = target.with_suffix(".download")
    print(f"Downloading {name}", flush=True)
    try:
        with urlopen(url, timeout=120) as response, temporary.open("wb") as handle:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(block)
        if file_hash(temporary) != item["sha256"]:
            raise ValueError(f"Checksum mismatch for {name}: source may have changed; do not combine versions.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
print("All twelve files match the reviewed snapshot.")
