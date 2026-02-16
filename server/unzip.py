import zipfile
from pathlib import Path

from tqdm import tqdm
import logging

if __name__ == "__main__":
    print("Starting extraction process...")

    logger = logging.getLogger("file_logger")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # VERY important

    file_handler = logging.FileHandler("app.log")
    formatter = logging.Formatter(
        "%(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    with zipfile.ZipFile("data.zip") as zf:
        members = zf.infolist()
        total = len(members)

        for i, member in enumerate(tqdm(members, desc="Extracting"), start=1):
            try:
                zf.extract(member, "out")
            except zipfile.error:
                pass

            progress = round((i / total) * 10, 2)
            # example usage:
            logger.info(progress)

    # Keep data.zip for resume capability; clean up after full processing.
