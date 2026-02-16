from pathlib import Path
import shutil

if __name__ == "__main__":
    Path("process").unlink()
    Path("manifest.json").unlink()
    shutil.rmtree("chunks", ignore_errors=True)