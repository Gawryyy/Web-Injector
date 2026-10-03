from __future__ import annotations

from copy import deepcopy
from threading import Lock

_lock = Lock()

_DEFAULT_STATE = {
    "player": {
        "name": "gawr",
        "coins": 100,
        "level": 1,
        "health": 100,
        "max_health": 100,
    },
    "world": {
        "message": "Welcome to the local Web Injector test game.",
    },
}

_state = deepcopy(_DEFAULT_STATE)


def get_state() -> dict:
    with _lock:
        return deepcopy(_state)


def reset_state() -> dict:
    global _state
    with _lock:
        _state = deepcopy(_DEFAULT_STATE)
        return deepcopy(_state)


def add_coins(amount: int) -> dict:
    with _lock:
        _state["player"]["coins"] = max(0, _state["player"]["coins"] + amount)
        return deepcopy(_state)


def set_coins(amount: int) -> dict:
    with _lock:
        _state["player"]["coins"] = max(0, amount)
        return deepcopy(_state)


def change_health(amount: int) -> dict:
    with _lock:
        player = _state["player"]
        player["health"] = max(0, min(player["max_health"], player["health"] + amount))
        return deepcopy(_state)


def set_health(amount: int) -> dict:
    with _lock:
        player = _state["player"]
        player["health"] = max(0, min(player["max_health"], amount))
        return deepcopy(_state)


def set_level(level: int) -> dict:
    with _lock:
        _state["player"]["level"] = max(1, level)
        return deepcopy(_state)


def set_name(name: str) -> dict:
    clean = name.strip()[:24] or "Player"
    with _lock:
        _state["player"]["name"] = clean
        return deepcopy(_state)
