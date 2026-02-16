import hashlib
import logging
from pathlib import Path
import tarfile
import shutil
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from manifest import HASH_CHUNK_SIZE
from manifest import PREFERRED_CHUNK_SIZE

def split_file(path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(path, "rb") as f:
        i = 0
        while True:
            chunk = f.read(PREFERRED_CHUNK_SIZE)
            if not chunk:
                break

            part = out_dir / f"{path.name}.part{i}"
            with open(part, "wb") as out:
                out.write(chunk)

            i += 1

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def make_medium_chunk(args):
    path, meta, chunk_index = args
    chunk_path = Path("chunks") / f"chunk_{chunk_index}.tar.xz"
    with tarfile.open(chunk_path, "w:xz") as tar:
        tar.add(path, arcname=path.name)
    return {
        "name": chunk_path.name,
        "chunk_index": chunk_index,
        "files": [meta["name"]],
        "hash": sha256_file(chunk_path),
        "category": "medium"
    }


def make_large_chunk(args):
    part_path, chunk_index = args
    chunk_path = Path("chunks") / f"chunk_{chunk_index}.tar.xz"
    with tarfile.open(chunk_path, "w:xz") as tar:
        tar.add(part_path, arcname=part_path.name)
    return {
        "name": chunk_path.name,
        "chunk_index": chunk_index,
        "files": [part_path.name],
        "hash": sha256_file(chunk_path),
        "category": "large"
    }

if __name__ == "__main__":
    logger = logging.getLogger("file_logger")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler("app.log")
    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    # ---------- Load manifest ----------
    with open("manifest.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs("chunks", exist_ok=True)

    print("Creating small chunks...")

    # ---------- Small Files ----------
    small_files = [f for f in data["files"] if f["category"] == "small"]
    os.makedirs("smallFiles", exist_ok=True)

    moved_files = []
    for meta in small_files:
        src = Path("out") / meta["path"]
        dst = Path("smallFiles") / meta["name"]
        shutil.move(src, dst)
        moved_files.append((dst, meta))

    current_files = []
    current_size = 0
    chunk_index = 0

    for path, meta in tqdm(moved_files, total=len(moved_files), desc="Processing small files"):
        current_files.append((path, meta))
        current_size += meta["size"]

        if current_size >= PREFERRED_CHUNK_SIZE:
            with tarfile.open(f"chunks/chunk_{chunk_index}.tar.xz", "w:xz") as tar:
                for p, _ in current_files:
                    tar.add(p, arcname=p.name)

            data["chunks"].append({
                "name": f"chunk_{chunk_index}.tar.xz",
                "chunk_index": chunk_index,
                "files": [meta["name"] for _, meta in current_files],
                "hash": sha256_file(Path(f"chunks/chunk_{chunk_index}.tar.xz")),
                "category": "small"
            })

            chunk_index += 1
            current_files = []
            current_size = 0

            small_progress = round((chunk_index / len(moved_files)) * 10, 2)
            progress = 30 + small_progress
            logger.info(progress)

    if current_files:
        with tarfile.open(f"chunks/chunk_{chunk_index}.tar.xz", "w:xz") as tar:
            for p, _ in current_files:
                tar.add(p, arcname=p.name)

        data["chunks"].append({
            "name": f"chunk_{chunk_index}.tar.xz",
            "chunk_index": chunk_index,
            "files": [meta["name"] for _, meta in current_files],
            "hash": sha256_file(Path(f"chunks/chunk_{chunk_index}.tar.xz")),
            "category": "small"
        })

    chunk_index += 1

    print("Creating medium chunks...")
    shutil.rmtree("smallFiles", ignore_errors=True)

    # ---------- Medium Files ----------
    medium_files = [f for f in data["files"] if f["category"] == "medium"]
    os.makedirs("mediumFiles", exist_ok=True)

    moved_files = []
    for meta in medium_files:
        src = Path("out") / meta["path"]
        dst = Path("mediumFiles") / meta["name"]
        shutil.move(src, dst)
        moved_files.append((dst, meta))

    medium_done = 0
    if moved_files:
        medium_tasks = [
            (path, meta, chunk_index + i)
            for i, (path, meta) in enumerate(moved_files)
        ]
        workers = min(os.cpu_count() or 2, len(medium_tasks))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(make_medium_chunk, args) for args in medium_tasks]
            for fut in as_completed(futures):
                data["chunks"].append(fut.result())
                medium_done += 1
                medium_progress = round((medium_done / len(moved_files)) * 15, 2)
                progress = 40 + medium_progress
                logger.info(progress)
        chunk_index += len(moved_files)

    print("Processing large files...")
    shutil.rmtree("mediumFiles", ignore_errors=True)

    # ---------- Large Files ----------
    large_files = [f for f in data["files"] if f["category"] == "large"]

    os.makedirs("largeFiles", exist_ok=True)
    os.makedirs("largeFiles_split", exist_ok=True)

    moved_files = []
    for meta in large_files:
        src = Path("out") / meta["path"]
        dst = Path("largeFiles") / meta["name"]
        shutil.move(src, dst)
        moved_files.append((dst, meta))

    for path, meta in moved_files:
        split_file(path, Path("largeFiles_split"))

    shutil.rmtree("largeFiles", ignore_errors=True)

    path = Path("largeFiles_split")
    parts = [p for p in path.rglob("*") if p.is_file()]
    total = len(parts)
    large_done = 0

    if parts:
        large_tasks = [
            (part, chunk_index + i)
            for i, part in enumerate(parts)
        ]
        workers = min(os.cpu_count() or 2, len(large_tasks))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(make_large_chunk, args) for args in large_tasks]
            for fut in as_completed(futures):
                data["chunks"].append(fut.result())
                large_done += 1
                large_progress = round((large_done / total) * 40, 2)
                progress = 55 + large_progress
                logger.info(progress)
        chunk_index += len(parts)

    shutil.rmtree("largeFiles_split", ignore_errors=True)

    print("Chunking complete.")

    data["chunks"] = sorted(data["chunks"], key=lambda c: c["chunk_index"])

    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    exit(0)
