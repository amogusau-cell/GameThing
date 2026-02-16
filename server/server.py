import json
import os
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
import yaml
from pydantic import BaseModel
import subprocess
app = FastAPI()


GAME_PATH = Path("games")
PROCESSING_PATH = Path("processes")
USERS_PATH = Path("users.yaml")


class CreateGameData(BaseModel):
    config: str = ""


class ProcessData(BaseModel):
    id: str
    download: float
    process: float
    download_url: str


class RegisterData(BaseModel):
    username: str
    password: str


class ChangePasswordData(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountData(BaseModel):
    current_password: str

def serialize_process_list(processes: list[ProcessData]) -> list[dict]:
    return [p.model_dump() for p in processes]


# ---------- LOAD USERS ----------

def load_users():
    if USERS_PATH.exists():
        with open(USERS_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
            return data.get("users", {})
    return {}


def save_users():
    with open(USERS_PATH, "w") as f:
        yaml.safe_dump({"users": USERS}, f)


USERS = load_users()

# ---------- LOAD PROCESSES IF EXISTS -----------

if not os.path.exists(PROCESSING_PATH / "processes.json"):
    os.makedirs(PROCESSING_PATH, exist_ok=True)
    with open(PROCESSING_PATH / "processes.json", "w") as f:
        f.write("[]")

with open(PROCESSING_PATH / "processes.json", "r") as f:
    process_data = json.load(open(PROCESSING_PATH / "processes.json"))


# ---------- AUTH ----------

def auth_user(request: Request):
    api_key = (
        request.headers.get("x-api-key")
        or request.query_params.get("api-key")
    )

    for username, data in USERS.items():
        if data["api_key"] == api_key:
            return username
    raise HTTPException(status_code=401, detail="Invalid API key")


# ---------- ACCOUNT ----------

@app.post("/register")
def register(data: RegisterData):
    if not data.username or not data.password:
        raise HTTPException(status_code=400, detail="Missing username or password")

    if data.username in USERS:
        raise HTTPException(status_code=409, detail="User already exists")

    USERS[data.username] = {"api_key": data.password}
    save_users()
    return {"status": "ok"}


@app.get("/account/games")
def account_games(user: str = Depends(auth_user)):
    uploaded = []
    for game in GAME_PATH.iterdir():
        if not game.is_dir():
            continue

        config_path = game / "config.yaml"
        owner = None
        name = game.name

        if config_path.exists():
            try:
                config = yaml.safe_load(config_path.read_text()) or {}
                owner = config.get("user")
                name = config.get("name", name)
            except Exception:
                owner = None

        if owner == user:
            uploaded.append({"id": game.name, "name": name})

    return {"games": uploaded}


@app.post("/account/password")
def change_password(
        data: ChangePasswordData,
        user: str = Depends(auth_user)
):
    if USERS.get(user, {}).get("api_key") != data.current_password:
        raise HTTPException(status_code=403, detail="Invalid password")

    if not data.new_password:
        raise HTTPException(status_code=400, detail="New password required")

    USERS[user]["api_key"] = data.new_password
    save_users()
    return {"status": "ok"}


@app.post("/account/delete")
def delete_account(
        data: DeleteAccountData,
        user: str = Depends(auth_user)
):
    if USERS.get(user, {}).get("api_key") != data.current_password:
        raise HTTPException(status_code=403, detail="Invalid password")

    USERS.pop(user, None)
    save_users()
    return {"status": "ok"}


# ---------- CONFIG UPDATE ----------

@app.post("/games/{game_id}/config")
def update_config(
        game_id: str,
        config: str = Form(...),
        user: str = Depends(auth_user)
):
    require_game_access(game_id)

    try:
        data = yaml.safe_load(config) or {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid YAML")

    if data.get("id") and data["id"] != game_id:
        raise HTTPException(status_code=400, detail="Game id mismatch")

    with open(GAME_PATH / game_id / "config.yaml", "w") as f:
        yaml.safe_dump(data, f)

    return {"status": "ok"}


# ---------- GAME LOOKUP ----------

def get_game(game_id: str) -> Path | None:
    for game in GAME_PATH.iterdir():
        if game.name == game_id:
            return game
    return None


def require_game_access(game_id: str) -> Path:
    game = get_game(game_id)

    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return game


# ---------- ROUTES ----------

process = None

@app.on_event("startup")
def start():
    global process
    process = subprocess.Popen(["python3", "process.py"])

@app.on_event("shutdown")
def stop():
    if process:
        process.terminate()

@app.get("/")
def check_user(user: str = Depends(auth_user)):
    return {"user": user}

@app.get("/games/{game_id}/downloadchunk/{chunk_id}")
def download_chunk(
        game_id: str,
        chunk_id: str,
        user: str = Depends(auth_user)
):
    require_game_access(game_id)

    file_path = GAME_PATH / game_id / "chunks" / f"chunk_{chunk_id}.tar.xz"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Chunk not found")

    return FileResponse(file_path, filename=file_path.name)


@app.get("/games/{game_id}/download/manifest.json")
def download_manifest(
        game_id: str,
        user: str = Depends(auth_user)
):
    require_game_access(game_id)

    file_path = GAME_PATH / game_id / "manifest.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")

    return FileResponse(file_path, filename="manifest.json")


@app.get("/games/{game_id}/download/config.yaml")
def download_config(
        game_id: str,
        user: str = Depends(auth_user)
):
    require_game_access(game_id)

    file_path = GAME_PATH / game_id / "config.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Config not found")

    return FileResponse(file_path, filename="processes/sample_zip_test/config.yaml")


@app.get("/status")
def status(user: str = Depends(auth_user)):
    return {"status": f"{user} is authenticated"}


@app.get("/games")
def get_games(user: str = Depends(auth_user)):
    games = []
    for game in GAME_PATH.iterdir():
        if game.is_dir():
            games.append(game.name)
    return {"games": games}


@app.get("/processes")
def get_loading_games(user: str = Depends(auth_user)):
    out_processes = []
    with open(PROCESSING_PATH / "processes.json", "r") as process_json:
        processes = json.load(process_json)
    for game in processes:
        out_processes.append(game["id"])
    return {"processes": out_processes}

@app.get("/processes/data")
def get_loading_games(user: str = Depends(auth_user)):
    with open(PROCESSING_PATH / "processes.json", "r") as process_json:
        processes = json.load(process_json)
    return {"processes": processes}


@app.post("/upload")
async def create_game(
        config: str = Form(...),
        file: UploadFile = File(...),
        user: str = Depends(auth_user)
):
    print("Starting download")
    game_data = yaml.safe_load(config)

    process_path = PROCESSING_PATH / game_data["id"]
    os.makedirs(process_path, exist_ok=True)

    with open(process_path / "config.yaml", "w") as config_file:
        yaml.dump(game_data, config_file)

    # Stream the file to disk in chunks
    with open(process_path / "data.zip", "wb") as out_file:
        while True:
            chunk = await file.read(8192)  # Read 8KB at a time
            if not chunk:
                break
            out_file.write(chunk)

    print("Finished download")

    # Add to processes.json
    new_process = ProcessData(
        id=game_data["id"],
        download=1.0,
        process=0.0,
        download_url=""
    )

    process_data.append(new_process.model_dump())

    with open(PROCESSING_PATH / "processes.json", "w") as f:
        json.dump(process_data, f, indent=2)

    return {"status": "ok"}

@app.post("/download")
async def create_game(
        config: str = Form(...),
        user: str = Depends(auth_user)
):
    print("Starting download")
    game_data = yaml.safe_load(config)

    process_path = PROCESSING_PATH / game_data["id"]
    os.makedirs(process_path, exist_ok=True)

    with open(process_path / "config.yaml", "w") as config_file:
        yaml.dump(game_data, config_file)

    # Add to processes.json
    new_process = ProcessData(
        id=game_data["id"],
        download=0.0,
        process=0.0,
        download_url=game_data["url"]
    )

    process_data.append(new_process.model_dump())

    with open(PROCESSING_PATH / "processes.json", "w") as f:
        json.dump(process_data, f, indent=2)

    return {"status": "ok"}


@app.delete("/games/{game_id}")
def delete_game(game_id: str, user: str = Depends(auth_user)):
    game = get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    shutil.rmtree(game)
    return {"game_id": game_id, "removed": True}

@app.get("/games/{game_id}/images/{image_id}")
def get_image(game_id: str, image_id: str, user: str = Depends(auth_user)):
    image_path = GAME_PATH / game_id / "steamdata/images" / image_id

    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path)


# ---------- RUN ----------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

#uvicorn server:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 300
#docker run --rm -p 8000:8000 -v /path/presistent:/app/games gamething-server
#docker build -t gamething-server /Users/ozersimsek/Desktop/GameThingClientUi/server
