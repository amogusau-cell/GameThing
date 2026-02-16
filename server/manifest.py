import json
import logging
from pathlib import Path
import hashlib
from tqdm import tqdm
import yaml

PREFERRED_CHUNK_SIZE = 8 * 1024 * 1024
LARGE_FILE_SIZE = 32 * 1024 * 1024
HASH_CHUNK_SIZE = 1024 * 1024


# ---------- HASHING ----------

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


# ---------- MANIFEST ----------

if __name__ == "__main__":
    print("Creating manifest.json...")

    logger = logging.getLogger("file_logger")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # VERY important

    file_handler = logging.FileHandler("app.log")
    formatter = logging.Formatter(
        "%(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    
    root = Path("out")
    
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    first_folder = folders[0] if folders else None
    
    root_hash = sha256_folder(first_folder)
    
    folders_output = []
    files_output = []
    chunks_output = []
    
    used_names = {}
    
    total_items = sum(1 for _ in root.rglob("*"))
    
    file_ids = 0
    
    for item in tqdm(root.rglob("*"), total=total_items, desc="Processing"):
        if item.is_dir():
            folders_output.append({
                "path": str(item.relative_to(root)).replace("\\", "/")
            })
    
        elif item.is_file():
            size = item.stat().st_size
            if size >= LARGE_FILE_SIZE:
                category = "large"
            elif size >= PREFERRED_CHUNK_SIZE:
                category = "medium"
            else:
                category = "small"
    
            files_output.append({
                "path": str(item.relative_to(root)).replace("\\", "/"),
                "name": str(file_ids),
                "size": size,
                "hash": sha256_file(item),
                "category": category
            })
            
            file_ids += 1

            progress = 10 + round((file_ids / total_items) * 20, 2) -1
            logger.info(progress)
    
    
    # ---------- FINAL OUTPUT ----------
    
    with open("config.yaml", "r") as f:
        yaml_data = yaml.safe_load(f)
        NAME = yaml_data.get("name")
        RUN = yaml_data.get("run")
        SAVE = yaml_data.get("saveInGameFolder")
        SAVE_PATH = yaml_data.get("savePath")

    
    output = {
        "name": NAME,
        "root": first_folder.name,
        "run": RUN,
        "saveInGameFolder": SAVE,
        "savePath": SAVE_PATH,
        "folders": folders_output,
        "files": files_output,
        "chunks": chunks_output,
        "hash": root_hash
    }
    
    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    logger.info("30")
    print("manifest.json created successfully ✅")
