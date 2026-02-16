#!/usr/bin/env python3
"""
make_random_tree.py

Creates a folder with randomly nested subfolders and files whose total UNZIPPED
size is approximately the user-provided target, then zips the folder.

Usage:
    python make_random_tree.py
"""

import os
import random
import shutil
import string
import time
from pathlib import Path

# ------------- helpers -------------
def parse_size(s: str) -> int:
    """Parse sizes like '10MB', '2.5 GB', '1024', '7k' -> bytes (int)."""
    s = s.strip().lower().replace(" ", "")
    units = {"b": 1, "kb": 1024, "k": 1024, "mb": 1024**2, "m": 1024**2, "gb": 1024**3, "g": 1024**3, "tb": 1024**4}
    # try suffix match
    for u in sorted(units.keys(), key=len, reverse=True):
        if s.endswith(u):
            try:
                num = float(s[:-len(u)]) if s[:-len(u)] != "" else 1.0
                return int(num * units[u])
            except ValueError:
                break
    # fallback: plain number (bytes)
    if s.isdigit() or (s.replace(".", "", 1).isdigit() and "." in s):
        return int(float(s))
    raise ValueError(f"Can't parse size: {s}")


def random_name(length=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def make_parents_and_filepath(base: Path, depth_min=0, depth_max=6):
    depth = random.randint(depth_min, depth_max)
    parts = [random_name(random.randint(3, 50)) for _ in range(depth)]
    dirpath = base.joinpath(*parts)
    dirpath.mkdir(parents=True, exist_ok=True)
    fname = random_name(12) + random.choice([".bin", ".dat", ".txt", ".bin"])
    return dirpath / fname


def write_file_with_size(path: Path, size_bytes: int, chunk=1024 * 1024):
    """Write a file of exactly size_bytes. Mix zeros and random data to vary compressibility."""
    remaining = size_bytes
    use_random_chunk = False
    # Decide randomly whether to write mostly random or zeros (gives variety)
    random_pref = random.random()
    with open(path, "wb") as f:
        while remaining > 0:
            w = min(chunk, remaining)
            # occasionally write truly random bytes (slower) to create incompressible files
            if random_pref < 0.2 or (random_pref < 0.7 and random.random() < 0.05):
                f.write(os.urandom(w))
            else:
                f.write(b"\0" * w)
            remaining -= w


# ------------- main flow -------------
def main():
    print("How big should the folder be? (examples: '150MB', '2.5GB', '4096')\n> ", end="")
    target_s = input().strip()
    try:
        target_bytes = parse_size(target_s)
    except Exception as e:
        print("Couldn't parse size. Try examples like '100MB' or '2GB'.")
        raise

    # Make unique base folder
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base_name = f"random_tree_{stamp}"
    base = Path.cwd() / base_name
    base.mkdir(exist_ok=False)
    print(f"Creating folder: {base}  (target unzipped size ≈ {target_bytes} bytes)")

    remaining = target_bytes
    file_count = 0
    total_written = 0

    # Safety limits so it doesn't produce absurd number of tiny files by accident
    max_files = max(1, int(target_bytes // 1024)) + 10000  # very large target could allow many files

    while remaining > 0 and file_count < max_files:
        # Pick a random file size. Strategy:
        # - usually pick small-to-medium chunk
        # - occasionally pick a very large chunk
        if remaining == 1:
            piece = 1
        else:
            # allow very large single files sometimes
            if random.random() < 0.07:
                piece = random.randint(max(1, remaining // 2), remaining)
            else:
                # typical piece: 1 byte . min(remaining, target/4, 128MB)
                cap = max(1, min(remaining, max(1, target_bytes // 4), 128 * 1024 * 1024))
                piece = random.randint(1, cap)

        # Create random nested path
        filepath = make_parents_and_filepath(base)
        # Avoid collisions (extremely unlikely)
        if filepath.exists():
            continue

        # Write the file (this can be slow for huge sizes)
        try:
            print(f"Writing file #{file_count+1}: {filepath}  size={piece} bytes")
            write_file_with_size(filepath, piece)
        except Exception as e:
            print(f"ERROR writing {filepath}: {e}")
            # if writing fails, stop to avoid partial mess
            break

        file_count += 1
        total_written += piece
        remaining = max(0, target_bytes - total_written)

        # small optimization: if remaining tiny (<1KB), create a tiny file to finish
        if 0 < remaining < 1024 and random.random() < 0.5:
            # next loop will probably create the final tiny file
            pass

    # Recalculate actual size on disk (sum of file sizes)
    actual = 0
    for p in base.rglob("*"):
        if p.is_file():
            actual += p.stat().st_size

    print("\nDone creating files.")
    print(f"Files created: {file_count}")
    print(f"Total size (sum of files) = {actual} bytes  (~{actual / (1024**2):.2f} MB)")

    # Zip the folder
    zip_name = str(base)
    print(f"Zipping folder to: {zip_name}.zip")
    archive_path = shutil.make_archive(zip_name, "zip", root_dir=base)
    archive_size = os.path.getsize(archive_path)
    print(f"Archive created: {archive_path}  ({archive_size} bytes, ~{archive_size/(1024**2):.2f} MB)")

    print("\nSummary:")
    print(f"  Folder (unzipped) path: {base}")
    print(f"  Folder (unzipped) total size: {actual} bytes")
    print(f"  ZIP archive: {archive_path}")
    print("If you want sparser (faster) creation or different randomness patterns, edit the script.\nHave fun! 🚀")


if __name__ == "__main__":
    main()
