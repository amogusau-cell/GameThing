import json
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
import os, signal

app = FastAPI()
server = True

with open("server.json", "r") as f:
    PATH_TO_FILE = Path(json.load(f)["file_path"])
    print(PATH_TO_FILE)

@app.get("/")
def download_file():
    return FileResponse(PATH_TO_FILE, filename=PATH_TO_FILE.name)

@app.get("/config")
def download_file():
    return FileResponse("config.yaml", filename="config.yaml")

def shutdown():
    os.remove("server.json")
    os.kill(os.getpid(), signal.SIGTERM)

@app.delete("/")
def close_server(background_tasks: BackgroundTasks):
    background_tasks.add_task(shutdown)
    return {"status": "shutting down"}

@app.get("/health")
def health():
    return {"ok": True}


# ---------- RUN ----------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=6769)
