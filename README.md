# GameThing
Save Games to your server and access them through the app. No need to worry about downloading and unzipping.
The server can be deployed in docker. Run the client app by running the python script app.py.

To run the server in docker use these scripts:

Build:
docker build -t gamething-server /Path/To/folder/server

You should replace "/Path/To/folder" part with the actual path to the folder.

Run:
docker run --rm -p 8000:8000 -v /path/presistent:/app/games gamething-server

You should replace "/path/presistent" part with the actual path to the games folder.
