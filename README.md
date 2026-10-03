# Web Injector

A local learning project with two browser tabs:

- **Test Game** — a small local web game with coins, level and health.
- **Control Panel** — changes the game state and can inject HTML/CSS/JavaScript into the local test-game page.

The injector is intentionally scoped to the project's own `127.0.0.1` test page.

## Folder structure

```text
Web-Injector/
├── assets/
│   ├── fonts/
│   ├── icons/
│   └── images/
├── backend/
│   ├── routes.py
│   ├── state.py
│   └── websocket.py
├── src/
│   ├── game/
│   │   ├── index.html
│   │   ├── game.css
│   │   └── game.js
│   └── panel/
│       ├── index.html
│       ├── panel.css
│       └── panel.js
├── launcher.py
├── server.py
├── requirements.txt
└── README.md
```

## Run on Kubuntu / Linux

Open a terminal in the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 launcher.py
```

The launcher starts the server and opens:

- `http://127.0.0.1:5000/game`
- `http://127.0.0.1:5000/panel`

Press **Ctrl+C** in the launcher terminal to stop the server.

## First things to try

1. Press **+100** in the control panel and watch the coin counter update in the game tab.
2. Change the player's level or health.
3. Open the **Injector** tab and inject the included CSS example.
4. Switch the injector type to HTML or JavaScript and test the examples.

## How the live updates work

This first version uses **Server-Sent Events (SSE)** for server-to-browser updates. The file is still named `backend/websocket.py` to match the planned project layout, but SSE keeps the first version lightweight and requires no browser library.
