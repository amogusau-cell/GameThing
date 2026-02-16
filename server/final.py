import shutil
import yaml
from pathlib import Path
import requests
import os
import json
import re
from difflib import SequenceMatcher

SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
DETAILS_URL = "https://store.steampowered.com/api/appdetails"

GAME_PATH = Path(os.environ.get("GAME_BASE", ""))

def normalize(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()

def search_games(query):
    r = requests.get(SEARCH_URL, params={
        "term": query,
        "l": "english",
        "cc": "us"
    })
    r.raise_for_status()
    return r.json().get("items", [])

def pick_best_match(query, items):
    q_norm = normalize(query)

    candidates = [i for i in items if i.get("type") == "app"]

    # 1️⃣ exact normalized match
    for item in candidates:
        if normalize(item["name"]) == q_norm:
            return item

    # 2️⃣ strict token match (portal ≠ portal 2)
    strict = [
        i for i in candidates
        if normalize(i["name"]).split() == q_norm.split()
    ]
    if strict:
        return strict[0]

    # 3️⃣ similarity fallback
    scored = []
    for item in candidates:
        score = SequenceMatcher(
            None, q_norm, normalize(item["name"])
        ).ratio()
        scored.append((score, item))

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[0][1] if scored else None

def get_app_details(appid):
    r = requests.get(DETAILS_URL, params={"appids": appid})
    r.raise_for_status()
    return r.json()[str(appid)]["data"]

def save_json(data, folder):
    with open(os.path.join(folder, "appdetails.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def download(url, path):
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)

def download_images(data, base):
    img_dir = os.path.join(base, "images")
    os.makedirs(img_dir, exist_ok=True)

    core_images = {
        "header.jpg": data.get("header_image"),
        "background.jpg": data.get("background"),
    }

    for name, url in core_images.items():
        if url:
            download(url, os.path.join(img_dir, name))

    for i, s in enumerate(data.get("screenshots", [])):
        download(s["path_full"], os.path.join(img_dir, f"screenshot_{i}.jpg"))

def main(game_name: str, save_path: str):
    query = game_name.strip()

    results = search_games(query)
    if not results:
        print("No results.")
        return

    match = pick_best_match(query, results)
    if not match:
        print("No match.")
        return

    appid = match["id"]
    print(f"Selected: {match['name']} (AppID {appid})")

    data = get_app_details(appid)

    os.makedirs(save_path, exist_ok=True)

    save_json(data, save_path)
    download_images(data, save_path)

    print("Images and JSON saved ✅")

if __name__ == "__main__":
    print("Final process started...")

    with open("config.yaml", "r") as f:
        yaml_data = yaml.safe_load(f)
        isSteam = yaml_data.get("isSteamGame", False)
        getSteam = yaml_data.get("getSteamData", False)
        game_name = yaml_data.get("name", "")
        game_id = yaml_data.get("id", "")

    print(f"Game Name: {game_name}, isSteam: {isSteam}, getSteam: {getSteam}")
    
    if isSteam and getSteam:
        path = Path(f"{GAME_PATH}/games/{game_id}/steamdata")
        path.parent.mkdir(parents=True, exist_ok=True)
        main(game_id, str(path))

    src = Path("chunks")
    dst = Path(f"{GAME_PATH}/games/{game_id}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)

    shutil.move("manifest.json", dst / "manifest.json")
    shutil.move("config.yaml", dst / "config.yaml")
