import logging
import shutil
import subprocess
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON_BIN = "python3"
STATE_PATH = Path("state.json")

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            return {}
    return {}

def save_state(step: int) -> None:
    STATE_PATH.write_text(json.dumps({"step": step}))

def run_step(script_name: str):
    script_path = BASE_DIR / script_name
    subprocess.run([PYTHON_BIN, str(script_path)], check=True)

if __name__ == "__main__":
    logger = logging.getLogger("file_logger")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler("app.log")
    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    state = load_state()
    step = int(state.get("step", 0))

    # Ensure we have a clean out folder before chunking
    if step < 3:
        shutil.rmtree("out", ignore_errors=True)
        run_step("unzip.py")  # Unzip process 10
        save_state(1)

        run_step("manifest.py")  # Manifest process 20
        save_state(2)

        shutil.rmtree("chunks", ignore_errors=True)
        run_step("chunk.py")  # Chunk process 65 10 15 40
        save_state(3)

    if step < 4:
        shutil.rmtree("out", ignore_errors=True)
        run_step("final.py")  # Final process 5
        save_state(4)

    logger.info("100")
