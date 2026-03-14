from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from multiprocessing import get_context
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import requests
import yaml

HASH_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_folder(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
                    h.update(chunk)
    return h.hexdigest()


def join_file(parts_dir: Path, output: Path) -> None:
    parts = sorted(
        parts_dir.iterdir(),
        key=lambda p: int(p.name.split(".part")[-1])
    )
    with open(output, "wb") as out:
        for part in parts:
            with open(part, "rb") as f:
                out.write(f.read())


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _download_stream(
    url: str,
    headers: Dict[str, str],
    output_path: Path,
    cancel_event: threading.Event,
    on_bytes: Callable[[int], None],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with requests.get(url, stream=True, headers=headers, timeout=30) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if cancel_event.is_set():
                    return
                if chunk:
                    f.write(chunk)
                    on_bytes(len(chunk))


def process_chunk(
    chunk_path: str,
    chunk_meta: Dict,
    file_map: Dict[str, Dict],
    items_dir: str,
    tmp_small_dir: str,
    tmp_large_dir: str,
) -> None:
    chunk_path_p = Path(chunk_path)
    items_dir_p = Path(items_dir)
    tmp_small_dir_p = Path(tmp_small_dir)
    tmp_large_dir_p = Path(tmp_large_dir)

    expected_hash = chunk_meta.get("hash")
    actual_hash = sha256_file(chunk_path_p)
    if expected_hash and actual_hash != expected_hash:
        raise RuntimeError(
            f"Chunk hash mismatch for {chunk_meta.get('name')}"
        )

    category = chunk_meta.get("category")
    chunk_tmp = (tmp_small_dir_p if category in ("small", "medium") else tmp_large_dir_p) / chunk_meta.get("name", "chunk")
    _safe_rmtree(chunk_tmp)
    _ensure_dir(chunk_tmp)

    with tarfile.open(chunk_path_p, "r:xz") as tar:
        tar.extractall(chunk_tmp)

    if category in ("small", "medium"):
        for file in chunk_tmp.iterdir():
            if not file.is_file():
                continue
            meta = file_map.get(file.name)
            if not meta:
                raise RuntimeError(f"Unknown file {file.name}")
            if sha256_file(file) != meta["hash"]:
                raise RuntimeError(f"Hash mismatch for {meta['path']}")
            shutil.move(file, items_dir_p / meta["name"])
    else:
        for part in chunk_tmp.iterdir():
            if not part.is_file():
                continue
            base_name = part.name.split(".part")[0]
            parts_dir = tmp_large_dir_p / base_name
            parts_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(part, parts_dir / part.name)

    _safe_rmtree(chunk_tmp)
    chunk_path_p.unlink(missing_ok=True)


def merge_large_file(
    meta: Dict,
    tmp_large_dir: str,
    items_dir: str,
) -> None:
    tmp_large_dir_p = Path(tmp_large_dir)
    items_dir_p = Path(items_dir)
    parts_dir = tmp_large_dir_p / meta["name"]
    if not parts_dir.exists():
        raise RuntimeError(f"Missing parts for {meta['name']}")

    output = items_dir_p / meta["name"]
    join_file(parts_dir, output)

    if sha256_file(output) != meta["hash"]:
        raise RuntimeError(f"Hash mismatch for {meta['path']}")

    shutil.rmtree(parts_dir, ignore_errors=True)


@dataclass
class DownloadStatus:
    id: str
    download: float = 0.0
    process: float = 0.0
    status: str = "idle"
    error: str = ""
    installed: bool = False
    bytes_total: int = 0
    bytes_done: int = 0


class DownloadManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.downloads_dir = base_dir / "downloads"
        self.games_dir = base_dir / "games"
        self.saves_dir = base_dir / "saves"
        self.cache_dir = base_dir / "cache"
        self.cache_games_dir = self.cache_dir / "games"
        self.cache_images_dir = self.cache_dir / "images"
        _ensure_dir(self.downloads_dir)
        _ensure_dir(self.games_dir)
        _ensure_dir(self.saves_dir)
        _ensure_dir(self.cache_games_dir)
        _ensure_dir(self.cache_images_dir)

        self._lock = threading.Lock()
        self._statuses: Dict[str, DownloadStatus] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._cache_lock = threading.Lock()

    def _set_status(self, game_id: str, **kwargs) -> None:
        with self._lock:
            status = self._statuses.get(game_id)
            if not status:
                status = DownloadStatus(id=game_id)
                self._statuses[game_id] = status
            for key, value in kwargs.items():
                setattr(status, key, value)

    def _get_status(self, game_id: str) -> DownloadStatus:
        with self._lock:
            return self._statuses.get(game_id, DownloadStatus(id=game_id))

    def start(
        self,
        game_id: str,
        server_url: str,
        api_key: str,
        max_workers: Optional[int] = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(game_id)
            if current and current.status in ("downloading", "processing"):
                return
            cancel_event = threading.Event()
            self._cancel_events[game_id] = cancel_event
            self._statuses[game_id] = DownloadStatus(
                id=game_id,
                status="downloading",
            )

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(game_id, server_url, api_key, cancel_event, max_workers),
            daemon=True,
        )
        thread.start()

    def stop(self, game_id: str) -> None:
        with self._lock:
            cancel_event = self._cancel_events.get(game_id)
            if cancel_event:
                cancel_event.set()

    def list_status(self) -> List[Dict]:
        with self._lock:
            items = []
            for status in self._statuses.values():
                status.installed = (self.games_dir / status.id).exists()
                items.append(status.__dict__.copy())
            return items

    def remove(self, game_id: str) -> None:
        with self._lock:
            cancel_event = self._cancel_events.pop(game_id, None)
            if cancel_event:
                cancel_event.set()
            self._statuses.pop(game_id, None)

    def _cache_game_dir(self, game_id: str) -> Path:
        return self.cache_games_dir / game_id

    def _cache_image_dir(self, game_id: str) -> Path:
        return self.cache_images_dir / game_id

    def _read_text(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _read_yaml(self, path: Path) -> Optional[Dict]:
        text = self._read_text(path)
        if text is None:
            return None
        try:
            return yaml.safe_load(text) or {}
        except Exception:
            return None

    def _read_json(self, path: Path) -> Optional[Dict]:
        text = self._read_text(path)
        if text is None:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _cache_config_path(self, game_id: str) -> Path:
        return self._cache_game_dir(game_id) / "config.yaml"

    def _cache_manifest_path(self, game_id: str) -> Path:
        return self._cache_game_dir(game_id) / "manifest.json"

    def cache_config_text(self, game_id: str, text: str) -> None:
        with self._cache_lock:
            self._write_text(self._cache_config_path(game_id), text)

    def cache_manifest(self, game_id: str, manifest: Dict) -> None:
        with self._cache_lock:
            self._write_text(
                self._cache_manifest_path(game_id),
                json.dumps(manifest, indent=2),
            )

    def _load_config_text(self, game_id: str) -> Optional[str]:
        local_path = self.games_dir / game_id / "config.yaml"
        cache_path = self._cache_config_path(game_id)
        if local_path.exists():
            return self._read_text(local_path)
        if cache_path.exists():
            return self._read_text(cache_path)
        return None

    def _load_manifest(self, game_id: str) -> Optional[Dict]:
        local_path = self.games_dir / game_id / "manifest.json"
        cache_path = self._cache_manifest_path(game_id)
        if local_path.exists():
            return self._read_json(local_path)
        if cache_path.exists():
            return self._read_json(cache_path)
        return None

    def _fetch_config_text(
        self,
        server_url: str,
        headers: Dict[str, str],
        game_id: str,
    ) -> Optional[str]:
        r = requests.get(
            f"{server_url}/games/{game_id}/download/config.yaml",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.text

    def _fetch_manifest(
        self,
        server_url: str,
        headers: Dict[str, str],
        game_id: str,
    ) -> Optional[Dict]:
        r = requests.get(
            f"{server_url}/games/{game_id}/download/manifest.json",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return None

    def get_cached_image(
        self,
        game_id: str,
        image_name: str,
        server_url: str,
        api_key: str,
    ) -> Optional[Path]:
        if "/" in image_name or "\\" in image_name:
            return None

        cache_path = self._cache_image_dir(game_id) / image_name
        missing_marker = cache_path.with_suffix(cache_path.suffix + ".missing")
        if cache_path.exists():
            return cache_path
        if missing_marker.exists():
            return None

        url = f"{server_url}/games/{game_id}/images/{image_name}"
        headers = {"X-API-Key": api_key}

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")

        try:
            with requests.get(url, stream=True, headers=headers, timeout=10) as r:
                if r.status_code == 404:
                    missing_marker.write_text("missing", encoding="utf-8")
                    return None
                r.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
            tmp_path.replace(cache_path)
            missing_marker.unlink(missing_ok=True)
            return cache_path
        except Exception:
            tmp_path.unlink(missing_ok=True)
            return None

    def cache_info(self, game_id: str) -> Dict:
        config_path = self._cache_config_path(game_id)
        manifest_path = self._cache_manifest_path(game_id)
        images_dir = self._cache_image_dir(game_id)

        config_bytes = config_path.stat().st_size if config_path.exists() else 0
        manifest_bytes = manifest_path.stat().st_size if manifest_path.exists() else 0

        images_bytes = 0
        images_count = 0
        if images_dir.exists():
            for item in images_dir.iterdir():
                if item.is_file() and not item.name.endswith(".missing") and not item.name.endswith(".tmp"):
                    images_count += 1
                    images_bytes += item.stat().st_size

        total_bytes = config_bytes + manifest_bytes + images_bytes

        return {
            "config": {"exists": config_path.exists(), "bytes": config_bytes},
            "manifest": {"exists": manifest_path.exists(), "bytes": manifest_bytes},
            "images": {"count": images_count, "bytes": images_bytes},
            "total_bytes": total_bytes,
        }

    def clear_cache(self, game_id: str) -> None:
        _safe_rmtree(self._cache_game_dir(game_id))
        _safe_rmtree(self._cache_image_dir(game_id))

    def _restore_saves(self, game_id: str, config: Dict, game_dir: Path) -> None:
        if not config.get("saveInGameFolder", False):
            return

        save_path = config.get("savePath")
        if not save_path:
            return

        src = self.saves_dir / game_id / save_path
        if not src.exists():
            return

        dest = Path(save_path)
        if not dest.is_absolute():
            dest = game_dir / save_path

        if src.is_dir():
            if dest.exists():
                if dest.is_dir():
                    for item in src.iterdir():
                        shutil.move(str(item), dest / item.name)
                    shutil.rmtree(src, ignore_errors=True)
                else:
                    return
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                if dest.is_file():
                    dest.unlink()
                else:
                    return
            shutil.move(str(src), str(dest))

    def fetch_library(
        self,
        server_url: str,
        api_key: str,
    ) -> List[Dict]:
        headers = {"X-API-Key": api_key}
        r = requests.get(f"{server_url}/games", headers=headers, timeout=10)
        r.raise_for_status()
        game_ids = r.json().get("games", [])

        library = []
        for game_id in game_ids:
            config_text = self._load_config_text(game_id)
            manifest = self._load_manifest(game_id)

            if config_text is None or manifest is None:
                try:
                    if config_text is None:
                        config_text = self._fetch_config_text(server_url, headers, game_id)
                        if config_text is not None:
                            self.cache_config_text(game_id, config_text)
                    if manifest is None:
                        manifest = self._fetch_manifest(server_url, headers, game_id)
                        if manifest is not None:
                            self.cache_manifest(game_id, manifest)
                except Exception:
                    pass

            config = {}
            if config_text:
                try:
                    config = yaml.safe_load(config_text) or {}
                except Exception:
                    config = {}

            size_bytes = 0
            if isinstance(manifest, dict):
                size_bytes = sum(f.get("size", 0) for f in manifest.get("files", []))

            library.append({
                "id": game_id,
                "name": config.get("name", game_id),
                "size_bytes": size_bytes,
                "installed": (self.games_dir / game_id).exists(),
            })

        return library

    def _run_pipeline(
        self,
        game_id: str,
        server_url: str,
        api_key: str,
        cancel_event: threading.Event,
        max_workers: Optional[int],
    ) -> None:
        headers = {"X-API-Key": api_key}

        work_dir = self.downloads_dir / game_id
        _safe_rmtree(work_dir)
        _ensure_dir(work_dir)

        chunks_dir = work_dir / "chunks"
        tmp_small = work_dir / "tmp_small"
        tmp_large = work_dir / "tmp_large"
        items_dir = work_dir / "items"
        for d in (chunks_dir, tmp_small, tmp_large, items_dir):
            _ensure_dir(d)

        try:
            config_r = requests.get(
                f"{server_url}/games/{game_id}/download/config.yaml",
                headers=headers,
                timeout=20,
            )
            config_r.raise_for_status()
            (work_dir / "config.yaml").write_text(config_r.text, encoding="utf-8")
            config_data = yaml.safe_load(config_r.text) or {}
            self.cache_config_text(game_id, config_r.text)

            manifest_r = requests.get(
                f"{server_url}/games/{game_id}/download/manifest.json",
                headers=headers,
                timeout=20,
            )
            manifest_r.raise_for_status()
            manifest = manifest_r.json()
            (work_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2),
                encoding="utf-8",
            )
            if isinstance(manifest, dict):
                self.cache_manifest(game_id, manifest)

            file_map = {f["name"]: f for f in manifest.get("files", [])}
            total_bytes = sum(f.get("size", 0) for f in manifest.get("files", [])) or 1
            total_chunks = len(manifest.get("chunks", [])) or 1

            self._set_status(
                game_id,
                bytes_total=total_bytes,
                bytes_done=0,
                download=0.0,
                process=0.0,
                status="downloading",
                error="",
            )

            downloaded_bytes = 0
            processed_chunks = 0

            mp_ctx = get_context("spawn")
            workers = max_workers or max(2, (os.cpu_count() or 2))

            futures = []
            with ProcessPoolExecutor(max_workers=workers, mp_context=mp_ctx) as pool:
                for chunk in manifest.get("chunks", []):
                    if cancel_event.is_set():
                        break

                    chunk_url = f"{server_url}/games/{game_id}/downloadchunk/{chunk['chunk_index']}"
                    chunk_path = chunks_dir / chunk["name"]

                    def on_bytes(delta: int) -> None:
                        nonlocal downloaded_bytes
                        downloaded_bytes += delta
                        self._set_status(
                            game_id,
                            bytes_done=downloaded_bytes,
                            download=min(1.0, downloaded_bytes / total_bytes),
                        )

                    _download_stream(
                        chunk_url,
                        headers,
                        chunk_path,
                        cancel_event,
                        on_bytes,
                    )

                    if cancel_event.is_set():
                        break

                    futures.append(
                        pool.submit(
                            process_chunk,
                            str(chunk_path),
                            chunk,
                            file_map,
                            str(items_dir),
                            str(tmp_small),
                            str(tmp_large),
                        )
                    )

                    done, pending = wait(futures, timeout=0)
                    for fut in done:
                        fut.result()
                        processed_chunks += 1
                        self._set_status(
                            game_id,
                            process=min(1.0, processed_chunks / total_chunks),
                            status="processing",
                        )
                    futures = list(pending)

                for fut in as_completed(futures):
                    fut.result()
                    processed_chunks += 1
                    self._set_status(
                        game_id,
                        process=min(1.0, processed_chunks / total_chunks),
                        status="processing",
                    )

            if cancel_event.is_set():
                self._set_status(game_id, status="cancelled")
                _safe_rmtree(work_dir)
                return

            large_files = [
                f for f in manifest.get("files", []) if f.get("category") == "large"
            ]
            total_merge = len(large_files)
            if total_merge:
                self._set_status(game_id, status="processing")
                with ProcessPoolExecutor(max_workers=workers, mp_context=mp_ctx) as pool:
                    merge_futures = [
                        pool.submit(merge_large_file, meta, str(tmp_large), str(items_dir))
                        for meta in large_files
                    ]
                    merged = 0
                    for fut in as_completed(merge_futures):
                        fut.result()
                        merged += 1
                        progress = (processed_chunks + merged) / (total_chunks + total_merge)
                        self._set_status(game_id, process=min(1.0, progress))

            game_dir = self.games_dir / game_id
            _safe_rmtree(game_dir)
            _ensure_dir(game_dir)

            for folder in manifest.get("folders", []):
                Path(game_dir / folder["path"]).mkdir(parents=True, exist_ok=True)

            for meta in manifest.get("files", []):
                src = items_dir / meta["name"]
                dst = game_dir / meta["path"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(src, dst)

            root = manifest.get("root")
            if root:
                final_hash = sha256_folder(game_dir / root)
                if final_hash != manifest.get("hash"):
                    raise RuntimeError("Final root folder hash mismatch")

            shutil.move(str(work_dir / "config.yaml"), str(game_dir / "config.yaml"))
            shutil.move(str(work_dir / "manifest.json"), str(game_dir / "manifest.json"))

            self._restore_saves(game_id, config_data, game_dir)

            _safe_rmtree(work_dir)
            self._set_status(
                game_id,
                download=1.0,
                process=1.0,
                status="completed",
            )
        except Exception as e:
            self._set_status(
                game_id,
                status="error",
                error=str(e),
            )
            _safe_rmtree(work_dir)
