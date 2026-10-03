from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend import state
from backend.websocket import publish

api = Blueprint("api", __name__, url_prefix="/api")


def _json_int(name: str, default: int = 0, minimum: int | None = None, maximum: int | None = None) -> int:
    data = request.get_json(silent=True) or {}
    try:
        value = int(data.get(name, default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _broadcast_state(current: dict) -> dict:
    publish({"type": "state", "state": current})
    return current


@api.get("/state")
def get_state():
    return jsonify(state.get_state())


@api.post("/coins/add")
def coins_add():
    amount = _json_int("amount", 0, -1_000_000, 1_000_000)
    return jsonify(_broadcast_state(state.add_coins(amount)))


@api.post("/coins/set")
def coins_set():
    amount = _json_int("amount", 0, 0, 999_999_999)
    return jsonify(_broadcast_state(state.set_coins(amount)))


@api.post("/health/change")
def health_change():
    amount = _json_int("amount", 0, -100, 100)
    return jsonify(_broadcast_state(state.change_health(amount)))


@api.post("/health/set")
def health_set():
    amount = _json_int("amount", 100, 0, 100)
    return jsonify(_broadcast_state(state.set_health(amount)))


@api.post("/level/set")
def level_set():
    level = _json_int("level", 1, 1, 9999)
    return jsonify(_broadcast_state(state.set_level(level)))


@api.post("/name/set")
def name_set():
    data = request.get_json(silent=True) or {}
    return jsonify(_broadcast_state(state.set_name(str(data.get("name", "Player")))))


@api.post("/inject")
def inject():
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind", "")).lower()
    code = str(data.get("code", ""))

    if kind not in {"html", "css", "js"}:
        return jsonify({"ok": False, "error": "kind must be html, css or js"}), 400
    if len(code) > 50_000:
        return jsonify({"ok": False, "error": "code is too large"}), 400

    publish({"type": "inject", "kind": kind, "code": code})
    return jsonify({"ok": True})


@api.post("/reset")
def reset():
    current = state.reset_state()
    publish({"type": "reset-injections"})
    return jsonify(_broadcast_state(current))
