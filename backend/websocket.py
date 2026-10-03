from __future__ import annotations

import json
import queue
from threading import Lock
from typing import Any

from flask import Blueprint, Response, stream_with_context

realtime = Blueprint("realtime", __name__)
_subscribers: list[queue.Queue] = []
_lock = Lock()


def publish(event: dict[str, Any]) -> None:
    with _lock:
        dead: list[queue.Queue] = []
        for subscriber in _subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                dead.append(subscriber)
        for subscriber in dead:
            if subscriber in _subscribers:
                _subscribers.remove(subscriber)


@realtime.get("/events")
def events() -> Response:
    subscriber: queue.Queue = queue.Queue(maxsize=32)

    with _lock:
        _subscribers.append(subscriber)

    def generate():
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                try:
                    payload = subscriber.get(timeout=15)
                    yield f"data: {json.dumps(payload)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            with _lock:
                if subscriber in _subscribers:
                    _subscribers.remove(subscriber)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
