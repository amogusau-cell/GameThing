# GameThing
Save Games to your server and access them through the app. No need to worry about downloading and unzipping.
The server can be deployed in docker. Run the client app by running the python script app.py.

## How to run the server

### Docker
You can run the server in docker with this example docker compose file.

Use `docker compose up` in the same path as docker-compose.yaml to start the server.

Example docker compose file: (docker-compose.yaml)

```
services:
  gamething-server:
    image: ghcr.io/amogusau-cell/gamething-server:latest
    ports:
      - "8000:8000"
    volumes:
      - /path/to/storage/games:/app/games
      - /path/to/storage/processes:/app/processes
      - ./users.yaml:/app/users.yaml
    restart: unless-stopped
```

You should replace /path/to/storage with your actual large storage (can be hdd).
It is recommended to mount the users.yaml in order to keep the user data after server restart.

You can also run the server by running `python server.py` command.

## How to add a game

### Zip file

Use the add file option to select your zip file.

### Url

Paste an url that will directly download the zip file for the game.

### Config.yaml

This is an example config file:

```
name: Game Name
id: game_name
saveInGameFolder: true
savePath: path/to/savefolder
isSteamGame: true
getSteamData: true
```

`Name` is the games display name.

`id` is the game's id. The game is saved with that value so any other game should not have the same id.

`saveInGameFolder` states that if the game saves its save files in the game files or not. If set to `true` any file in `savePath` will be kept on the client even after the game is deleted.

`savePath` the path the game uses to save its saved data. Can be empty if `saveInGameFolder` is set to false.

`isSteamGame` states if the game is from steam.

If `getSteamData` and `isSteamGame` is set to true then the server will download additional data such as screenshots to be used in ui.