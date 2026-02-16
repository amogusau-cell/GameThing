import json
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
import os
from tqdm import tqdm

import requests

# ------------------ paths ------------------

BASE_DIR = Path(__file__).resolve().parent
PYTHON_BIN = "python3"
MAIN_SCRIPT = BASE_DIR / "main.py"

PROCESSES_PATH = Path("processes")
PROCESSES_PATH.mkdir(parents=True, exist_ok=True)

JSON_PATH = PROCESSES_PATH / "processes.json"

# ------------------ globals ------------------

data_lock = threading.Lock()
threads = []
threads_lock = threading.Lock()


# ------------------ helpers ------------------

def read_json():
    if not JSON_PATH.exists():
        return []
    with open(JSON_PATH, "r") as f:
        return json.load(f)


def write_json(data):
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)


def update_process_value(game_id: str, key: str, value: float) -> None:
    with data_lock:
        data = read_json()
        for item in data:
            if item.get("id") == game_id:
                item[key] = round(value, 3)
                write_json(data)
                return


def remove_process(game_id: str) -> None:
    with data_lock:
        data = read_json()
        new_data = [item for item in data if item.get("id") != game_id]
        write_json(new_data)


# ------------------ progress writers ------------------

def download_progress_writer(game_id, stop_event, progress_q):
    last = 0.0
    while not stop_event.is_set() or not progress_q.empty():
        try:
            progress = progress_q.get(timeout=0.2)
        except queue.Empty:
            continue

        if abs(progress - last) >= 0.01:
            update_process_value(game_id, "download", progress)
            last = progress


def process_progress_writer(game_id, stop_event, log_path: Path):
    last = 0.0
    while not stop_event.is_set():
        try:
            with open(log_path, "r") as log:
                lines = log.readlines()
                if not lines:
                    time.sleep(0.2)
                    continue
                progress = float(lines[-1].strip())
        except Exception:
            time.sleep(0.2)
            continue

        if progress > 1.0:
            progress = progress / 100.0
        if progress < 0:
            progress = 0.0
        if progress > 1.0:
            progress = 1.0

        if abs(progress - last) >= 0.01:
            update_process_value(game_id, "process", progress)
            last = progress

        time.sleep(0.2)


# ------------------ workers ------------------

def download(url, output_path: Path, stop_event, progress_q):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing file if it exists to avoid corruption
    if output_path.exists():
        output_path.unlink()

    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()  # <-- IMPORTANT

        total = int(r.headers.get("content-length", 0))
        done = 0

        chunk_size = 1024 * 1024
        with open(output_path, "wb") as f:
            # Fix: Add decode_unicode=False to prevent automatic decoding
            with tqdm(total=total, unit='B', unit_scale=True, unit_divisor=1024, desc="Downloading") as pbar:
                for chunk in r.iter_content(chunk_size=chunk_size, decode_unicode=False):
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        pbar.update(len(chunk))
                        if total:
                            progress_q.put(done / total)

            f.flush()
            os.fsync(f.fileno())

    # Verify against actual file size on disk
    actual_size = output_path.stat().st_size
    if total and actual_size != total:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download corrupted: expected {total} bytes, got {actual_size}"
        )

    stop_event.set()


def process_item_download(item):
    print(f"Downloading {item['id']}")
    stop_event = threading.Event()
    progress_q = queue.Queue()

    t = threading.Thread(
        target=download_progress_writer,
        args=(item["id"], stop_event, progress_q)
    )
    t.start()

    with threads_lock:
        threads.append(t)

    try:
        work_dir = PROCESSES_PATH / item["id"] / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        download(
            item["download_url"],
            work_dir / "data.zip",
            stop_event,
            progress_q
        )
    finally:
        t.join()
        with threads_lock:
            threads.remove(t)

        update_process_value(item["id"], "download", 1.0)


def process_item(item):
    print(f"Processing {item['id']}")
    stop_event = threading.Event()

    process_path = PROCESSES_PATH / item["id"]
    work_dir = process_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    zip_path = work_dir / "data.zip"
    if not zip_path.exists():
        fallback_zip = process_path / "data.zip"
        if fallback_zip.exists():
            shutil.move(fallback_zip, zip_path)

    config_path = process_path / "config.yaml"
    if config_path.exists():
        shutil.copy(config_path, work_dir / "config.yaml")

    log_path = work_dir / "app.log"
    if log_path.exists():
        log_path.unlink(missing_ok=True)

    t = threading.Thread(
        target=process_progress_writer,
        args=(item["id"], stop_event, log_path)
    )
    t.start()

    with threads_lock:
        threads.append(t)

    try:
        env = os.environ.copy()
        env["GAME_BASE"] = str(BASE_DIR)
        subprocess.run([PYTHON_BIN, str(MAIN_SCRIPT)], cwd=work_dir, env=env, check=True)
    finally:
        stop_event.set()
        t.join()
        with threads_lock:
            threads.remove(t)

        update_process_value(item["id"], "process", 1.0)

    print("Processing finished")

    # cleanup work dir (keep saves, chunks already moved to games)
    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(process_path, ignore_errors=True)


# ------------------ main loop ------------------

if __name__ == "__main__":
    print("Started")

    try:
        while True:
            with data_lock:
                data = read_json()
                if data:
                    incomplete = [
                        item for item in data
                        if not (item.get("download", 0) >= 1.0 and item.get("process", 0) >= 1.0)
                    ]
                    if len(incomplete) != len(data):
                        write_json(incomplete)
                        data = incomplete
            for item in data:
                game_id = item.get("id")
                if not game_id:
                    continue

                if item.get("download", 0) < 1.0 and item.get("process", 0) < 1.0:
                    process_item_download(item)

                # Reload after download
                data = read_json()
                item = next((i for i in data if i.get("id") == game_id), None)
                if not item:
                    continue

                if item.get("download", 0) >= 1.0 and item.get("process", 0) < 1.0:
                    process_item(item)

                data = read_json()
                item = next((i for i in data if i.get("id") == game_id), None)
                if item and item.get("download", 0) >= 1.0 and item.get("process", 0) >= 1.0:
                    remove_process(game_id)

            time.sleep(2)
    except KeyboardInterrupt:
        print("Shutting down...")
        with threads_lock:
            active_threads = threads.copy()
        for t in active_threads:
            t.join()
        print("All threads cleaned up")
