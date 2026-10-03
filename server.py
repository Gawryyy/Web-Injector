from __future__ import annotations

import argparse
from pathlib import Path

from flask import Flask, jsonify, redirect, send_from_directory

from backend.routes import api
from backend.websocket import realtime

ROOT = Path(__file__).resolve().parent
GAME_DIR = ROOT / "src" / "game"
PANEL_DIR = ROOT / "src" / "panel"
ASSETS_DIR = ROOT / "assets"

app = Flask(__name__)
app.register_blueprint(api)
app.register_blueprint(realtime)


@app.get("/")
def root():
    return redirect("/game")


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "app": "web-injector",
            "game": True,
            "panel": True,
            "injection_api": True,
        }
    )


@app.get("/game")
def game_index():
    return send_from_directory(GAME_DIR, "index.html")


@app.get("/game/<path:filename>")
def game_file(filename: str):
    return send_from_directory(GAME_DIR, filename)


@app.get("/panel")
def panel_index():
    return send_from_directory(PANEL_DIR, "index.html")


@app.get("/panel/<path:filename>")
def panel_file(filename: str):
    return send_from_directory(PANEL_DIR, filename)


@app.get("/assets/<path:filename>")
def asset_file(filename: str):
    return send_from_directory(ASSETS_DIR, filename)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web Injector local test server")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind to")
    parser.add_argument("--port", type=int, default=5000, help="TCP port to listen on")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("Port must be between 1 and 65535")
    app.run(host=args.host, port=args.port, debug=False, threaded=True, use_reloader=False)
