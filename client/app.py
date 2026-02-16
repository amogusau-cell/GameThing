import socket
import httpx
import webview
import json
from pathlib import Path
import os, sys
import shutil
import yaml
import requests

from downloader import DownloadManager

PORT = 6769
window_ready = False

BASE_DIR = Path(__file__).resolve().parent
download_manager = DownloadManager(BASE_DIR)

class ProgressFileWrapper:
    def __init__(self, file_path, progress_window: webview.Window):
        self.file_path = file_path
        self.file = open(file_path, "rb")
        self.total_size = os.path.getsize(file_path)
        self.bytes_read = 0
        self.last_printed = -1
        self.progress_window = progress_window

    def read(self, size=-1):
        chunk = self.file.read(size)
        if chunk:
            self.bytes_read += len(chunk)
            progress = int((self.bytes_read / self.total_size) * 100)

            if progress != self.last_printed:
                self.last_printed = progress

                if window_ready:
                    self.progress_window.evaluate_js(
                        f"onProgressUpdate({progress})"
                    )

                print(f"Upload progress: {progress}%")

        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.file.close()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no data sent, just vibes
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

def reformat_ip(ip: str) -> str:
    if not ip.startswith(("http://", "https://")):
        ip = "http://" + ip

    url = ip.rstrip("/")

    return url

def check_user(user: str, password: str, ip: str) -> str:
    url = reformat_ip(ip)

    headers = {"x-api-key": password}

    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()

        if user == r.json().get("user"):
            return "Correct"

        return "Invalid user"

    except requests.exceptions.RequestException as e:
        return f"Server Error: {e}"

def restart():
    os.execv(sys.executable, [sys.executable] + sys.argv)

def on_close():
    print("Closing...")
    try:
        requests.delete("http://127.0.0.1:6769", timeout=5)
    except Exception:
        pass
    os._exit(0)

def on_loaded():
    global window_ready
    window_ready = True
    print("Window is ready for JS calls")

def yaml_to_json(data: str):
    yaml_data = yaml.load(
        data,
        Loader=yaml.FullLoader
    )
    return json.dumps(yaml_data)

def folder_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total

def load_game_config(game_dir: Path) -> dict:
    config_path = game_dir / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text()) or {}
    except Exception:
        return {}

def preserve_saves(base_dir: Path, game_id: str) -> None:
    game_dir = base_dir / "games" / game_id
    config = load_game_config(game_dir)

    if not config.get("saveInGameFolder", False):
        return

    save_path = config.get("savePath")
    if not save_path:
        return

    src = Path(save_path)
    if not src.is_absolute():
        src = game_dir / save_path

    if not src.exists():
        return

    saves_dir = base_dir / "saves" / game_id / save_path
    saves_dir.parent.mkdir(parents=True, exist_ok=True)

    if saves_dir.exists():
        if saves_dir.is_dir():
            shutil.rmtree(saves_dir, ignore_errors=True)
        else:
            saves_dir.unlink(missing_ok=True)

    shutil.move(str(src), str(saves_dir))

if __name__ == "__main__":
    if Path("user.json").exists():
        with open("user.json") as usr:
            userData = json.load(usr)
        result = check_user(userData["username"], userData["password"], userData["ip"])
        if result == "Correct":
            class Api:
                def open_file(self):
                    file_result = webview.windows[0].create_file_dialog(
                        webview.FileDialog.OPEN,
                        allow_multiple=False
                    )
                    if file_result:
                        print("Python aldı:", file_result[0])
                        return file_result[0]
                    return None

                def get_user(self):
                    print("Get user")
                    return json.dumps(userData)

                def get_game_data(self, game_id: str):
                    game_data = """name: "Alchemy Factory"
id: "Alchemy_Factory"
run: "Alchemy.Factory.Build.21344204/Alchemy.Factory.Build.21344204/Play - Alchemy Factory.exe"
saveInGameFolder: True
savePath: "Alchemy.Factory.Build.21344204/Alchemy.Factory.Build.21344204/Game/Alchemy Factory/SaveGames"
isSteamGame: True
getSteamData: True
"""
                    return yaml_to_json(game_data)

                def send_file(self, path: str, config: str):
                    print(f"Sending file {path}")

                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    url = reformat_ip(user_data["ip"]) + "/upload"

                    # Use httpx with progress tracking
                    with httpx.Client(timeout=None) as client:
                        with ProgressFileWrapper(path, window) as progress_file:
                            files = {
                                "file": (os.path.basename(path), progress_file, "application/octet-stream")
                            }
                            data = {
                                "config": config
                            }
                            headers = {
                                "x-api-key": user_data["password"]
                            }

                            response = client.post(
                                url,
                                files=files,
                                data=data,
                                headers=headers
                            )

                    response.raise_for_status()
                    print("Upload complete!")
                    return response.text

                def download_file(self, config: str):
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    url = reformat_ip(user_data["ip"]) + "/download"

                    response = requests.post(
                        url,
                        data={
                            "config": config  # ✅ Form field
                        },
                        headers={
                            "x-api-key": user_data["password"]
                        },
                        timeout=None
                    )

                    response.raise_for_status()
                    return response.json()

                def get_processes(self):
                    print(f"Getting processes")

                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    headers = {
                        "x-api-key": user_data["password"]
                    }

                    url = reformat_ip(user_data["ip"]) + "/processes/data"
                    processes = requests.get(url, headers=headers)

                    return processes.json()

                def get_server_ip(self):
                    print(f"Getting server ip")
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    return user_data["ip"]

                def get_auth_token(self):
                    print(f"Getting password")
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    return user_data["password"]

                def get_library(self):
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    try:
                        return download_manager.fetch_library(server_url, api_key)
                    except Exception as e:
                        print(f"Library fetch failed: {e}")
                        return []

                def start_game_download(self, game_id: str):
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    download_manager.start(game_id, server_url, api_key)
                    return {"status": "started", "id": game_id}

                def stop_game_download(self, game_id: str):
                    download_manager.stop(game_id)
                    return {"status": "stopping", "id": game_id}

                def get_downloads(self):
                    return {"downloads": download_manager.list_status()}

                def open_game_folder(self, game_id: str):
                    game_path = BASE_DIR / "games" / game_id
                    if not game_path.exists():
                        return {"status": "missing", "id": game_id}

                    if sys.platform.startswith("win"):
                        os.startfile(str(game_path))
                    elif sys.platform == "darwin":
                        import subprocess
                        subprocess.run(["open", str(game_path)])
                    else:
                        import subprocess
                        subprocess.run(["xdg-open", str(game_path)])

                    return {"status": "opened", "id": game_id}

                def delete_game_folder(self, game_id: str):
                    download_manager.remove(game_id)

                    game_path = BASE_DIR / "games" / game_id
                    if not game_path.exists():
                        return {"status": "missing", "id": game_id}

                    preserve_saves(BASE_DIR, game_id)
                    shutil.rmtree(game_path)
                    return {"status": "deleted", "id": game_id}

                def get_uploaded_games(self):
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    headers = {"x-api-key": api_key}
                    r = requests.get(f"{server_url}/account/games", headers=headers, timeout=10)
                    r.raise_for_status()
                    return r.json()

                def get_local_usage(self):
                    games_size = folder_size(BASE_DIR / "games")
                    downloads_size = folder_size(BASE_DIR / "downloads")
                    total = games_size + downloads_size
                    return {
                        "total": total,
                        "games": games_size,
                        "downloads": downloads_size
                    }

                def change_password(self, current_password: str, new_password: str):
                    if not current_password or not new_password:
                        return {"status": "error", "message": "Password required"}

                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    headers = {"x-api-key": api_key}
                    r = requests.post(
                        f"{server_url}/account/password",
                        headers=headers,
                        json={
                            "current_password": current_password,
                            "new_password": new_password
                        },
                        timeout=10
                    )

                    if r.status_code != 200:
                        return {"status": "error", "message": r.json().get("detail", "Failed")}

                    user_data["password"] = new_password
                    with open("user.json", "w", encoding="utf-8") as f:
                        json.dump(user_data, f, indent=2)

                    return {"status": "ok"}

                def delete_account(self, current_password: str):
                    if not current_password:
                        return {"status": "error", "message": "Password required"}

                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    headers = {"x-api-key": api_key}
                    r = requests.post(
                        f"{server_url}/account/delete",
                        headers=headers,
                        json={"current_password": current_password},
                        timeout=10
                    )

                    if r.status_code != 200:
                        return {"status": "error", "message": r.json().get("detail", "Failed")}

                    Path("user.json").unlink(missing_ok=True)
                    restart()

                def logout(self):
                    Path("user.json").unlink(missing_ok=True)
                    restart()

                def get_server_config(self, game_id: str):
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    headers = {"x-api-key": api_key}
                    r = requests.get(
                        f"{server_url}/games/{game_id}/download/config.yaml",
                        headers=headers,
                        timeout=10
                    )
                    r.raise_for_status()
                    return r.text

                def update_server_config(self, game_id: str, config: str):
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    headers = {"x-api-key": api_key}
                    r = requests.post(
                        f"{server_url}/games/{game_id}/config",
                        headers=headers,
                        data={"config": config},
                        timeout=10
                    )

                    if r.status_code != 200:
                        return {"status": "error", "message": r.json().get("detail", "Failed")}

                    # Also update local config if installed
                    local_config = BASE_DIR / "games" / game_id / "config.yaml"
                    if local_config.exists():
                        local_config.write_text(config, encoding="utf-8")

                    return {"status": "ok"}

                def delete_server_game(self, game_id: str):
                    with open("user.json", "r", encoding="utf-8") as f:
                        user_data = json.load(f)

                    server_url = reformat_ip(user_data["ip"])
                    api_key = user_data["password"]

                    headers = {"x-api-key": api_key}
                    r = requests.delete(
                        f"{server_url}/games/{game_id}",
                        headers=headers,
                        timeout=10
                    )

                    if r.status_code != 200:
                        return {"status": "error", "message": r.json().get("detail", "Failed")}

                    return {"status": "ok"}

            api = Api()

            window = webview.create_window(
                "My App",
                "library.html",
                js_api=api,
                maximized=True
            )

            window.events.loaded += on_loaded

            window.events.closing += on_close

            webview.start(debug=False)
            exit(0)


    class LoginApi:
        def login(self, username, password, ip) -> str:
            print(username, password, ip)

            if username and password and ip:
                user_data = {
                    "username": username,
                    "password": password,
                    "ip": ip
                }

                result = check_user(username, password, ip)

                print(result)

                if result == "Correct":
                    with open("user.json", "w", encoding="utf-8") as f:
                        json.dump(user_data, f, indent=2)
                    restart()
                else:
                    return result

            return "Username, password or url is not entered."

        def register(self, username, password, ip) -> str:
            print(username, password, ip)

            if not (username and password and ip):
                return "Username, password or url is not entered."

            url = reformat_ip(ip) + "/register"

            try:
                r = requests.post(
                    url,
                    json={"username": username, "password": password},
                    timeout=10
                )
            except requests.exceptions.RequestException as e:
                return f"Server Error: {e}"

            if r.status_code == 409:
                return "Username already exists."
            if r.status_code != 200:
                return r.json().get("detail", "Registration failed.")

            user_data = {
                "username": username,
                "password": password,
                "ip": ip
            }

            with open("user.json", "w", encoding="utf-8") as f:
                json.dump(user_data, f, indent=2)

            restart()


    loginApi = LoginApi()

    window = webview.create_window(
        "My App",
        "login.html",
        js_api=loginApi,
        maximized=True
    )

    webview.start()

#https://getsamplefiles.com/download/zip/sample-3.zip
