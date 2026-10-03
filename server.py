from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, request, send_from_directory

from backend.routes import api
from backend.websocket import realtime

ROOT = Path(__file__).resolve().parent
GAME_DIR = ROOT / "src" / "game"
PANEL_DIR = ROOT / "src" / "panel"
ASSETS_DIR = ROOT / "assets"
TARGETS_FILE = ROOT / "injector_targets.json"
REMOTE_ALLOWLIST_FILE = ROOT / "injector_remote_allowlist.json"

app = Flask(__name__)
app.register_blueprint(api)
app.register_blueprint(realtime)

_event_lock = threading.Lock()
_event_revision = 0
_events: deque[dict] = deque(maxlen=150)

_DEFAULT_TARGETS = {
    "selected": "test-game",
    "targets": [
        {
            "id": "test-game",
            "name": "Test Game",
            "kind": "builtin",
            "url": "builtin://test-game",
            "protected": True,
        }
    ],
}


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return value[:48] or "target"


def _load_targets() -> dict:
    if not TARGETS_FILE.exists():
        _save_targets(_DEFAULT_TARGETS)
        return json.loads(json.dumps(_DEFAULT_TARGETS))

    try:
        data = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _save_targets(_DEFAULT_TARGETS)
        return json.loads(json.dumps(_DEFAULT_TARGETS))

    targets = data.get("targets")
    selected = data.get("selected")

    if not isinstance(targets, list) or not targets:
        _save_targets(_DEFAULT_TARGETS)
        return json.loads(json.dumps(_DEFAULT_TARGETS))

    ids = {str(item.get("id", "")) for item in targets if isinstance(item, dict)}
    if selected not in ids:
        data["selected"] = "test-game" if "test-game" in ids else next(iter(ids))

    return data


def _save_targets(data: dict) -> None:
    TARGETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _selected_target() -> dict:
    data = _load_targets()
    selected = data.get("selected")

    for item in data["targets"]:
        if item.get("id") == selected:
            return item

    return data["targets"][0]



def _load_remote_allowlist() -> set[str]:
    """
    Remote/public targets must be explicitly listed here by the site owner.
    The JSON file can contain:
        {"hosts": ["astraiii.com", "www.astraiii.com"]}
    """
    if not REMOTE_ALLOWLIST_FILE.exists():
        REMOTE_ALLOWLIST_FILE.write_text(
            json.dumps({"hosts": []}, indent=2),
            encoding="utf-8",
        )
        return set()

    try:
        data = json.loads(REMOTE_ALLOWLIST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    hosts = data.get("hosts", [])
    if not isinstance(hosts, list):
        return set()

    return {
        str(host).strip().lower().rstrip(".")
        for host in hosts
        if str(host).strip()
    }


def _save_remote_allowlist(hosts: set[str]) -> None:
    REMOTE_ALLOWLIST_FILE.write_text(
        json.dumps({"hosts": sorted(hosts)}, indent=2),
        encoding="utf-8",
    )


def _trust_remote_host(host: str) -> None:
    host = host.strip().lower().rstrip(".")
    if not host:
        raise ValueError("Invalid hostname.")

    hosts = _load_remote_allowlist()
    hosts.add(host)
    _save_remote_allowlist(hosts)


def _host_is_approved_remote(host: str) -> bool:
    host = host.lower().rstrip(".")

    for allowed in _load_remote_allowlist():
        if host == allowed or host.endswith("." + allowed):
            return True

    return False


def _validate_target_url(url: str) -> tuple[str, str, bool]:
    """
    Returns (normalized_url, hostname, requires_public_trust).

    Local/private targets work automatically. Public domains work after the
    user explicitly confirms in the panel that they own/control that site.
    """
    url = url.strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Use an http:// or https:// URL.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing usernames/passwords are not supported.")

    host = (parsed.hostname or "").lower().strip().rstrip(".")
    if not host:
        raise ValueError("The target URL needs a hostname.")

    if _host_is_approved_remote(host):
        return url, host, False

    try:
        ip = ipaddress.ip_address(host)

        if ip.is_loopback or ip.is_private:
            return url, host, False

        return url, host, True
    except ValueError:
        pass

    try:
        results = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return url, host, True

    resolved_ips = {
        result[4][0]
        for result in results
        if result[4]
    }

    for address in resolved_ips:
        try:
            ip = ipaddress.ip_address(address)
            if ip.is_loopback or ip.is_private:
                return url, host, False
        except ValueError:
            continue

    return url, host, True


def _inject_bridge_into_html(data: bytes) -> bytes:
    text = data.decode("utf-8", errors="replace")
    tag = '<script src="/injector-bridge.js"></script>'

    if tag in text:
        return data

    lower = text.lower()
    index = lower.rfind("</body>")

    if index >= 0:
        text = text[:index] + tag + "\n" + text[index:]
    else:
        text += "\n" + tag

    return text.encode("utf-8")


def _builtin_response(path: str) -> Response:
    relative = path.strip("/") or "index.html"
    candidate = (GAME_DIR / relative).resolve()

    try:
        candidate.relative_to(GAME_DIR.resolve())
    except ValueError:
        return Response("Invalid path.", status=400)

    if not candidate.is_file():
        return Response("File not found.", status=404)

    if candidate.suffix.lower() in {".html", ".htm"}:
        body = _inject_bridge_into_html(candidate.read_bytes())
        return Response(body, content_type="text/html; charset=utf-8")

    return send_from_directory(GAME_DIR, relative)


def _target_url(base_url: str, path: str) -> str:
    path = path.lstrip("/")
    url = f"{base_url.rstrip('/')}/{path}"

    if request.query_string:
        url += "?" + request.query_string.decode("utf-8", errors="ignore")

    return url


def _forward_headers() -> dict[str, str]:
    headers: dict[str, str] = {}

    for name in (
        "Accept",
        "Accept-Language",
        "Content-Type",
        "Cookie",
        "User-Agent",
        "X-Requested-With",
    ):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _proxy_custom(target: dict, path: str) -> Response:
    target_url = str(target.get("url", "")).rstrip("/")

    upstream_request = urllib.request.Request(
        _target_url(target_url, path),
        data=request.get_data() if request.method not in {"GET", "HEAD"} else None,
        headers=_forward_headers(),
        method=request.method,
    )

    try:
        upstream = urllib.request.urlopen(upstream_request, timeout=8)
        status = upstream.status
        body = upstream.read()
        upstream_headers = upstream.headers
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()
        upstream_headers = exc.headers
    except urllib.error.URLError as exc:
        return Response(
            f"Target is unavailable: {exc.reason}",
            status=502,
            content_type="text/plain; charset=utf-8",
        )

    content_type = upstream_headers.get("Content-Type", "application/octet-stream")

    if "text/html" in content_type.lower():
        body = _inject_bridge_into_html(body)

    response = Response(body, status=status, content_type=content_type)

    for header in ("Cache-Control", "ETag", "Last-Modified"):
        value = upstream_headers.get(header)
        if value:
            response.headers[header] = value

    for cookie in upstream_headers.get_all("Set-Cookie") or []:
        response.headers.add("Set-Cookie", cookie)
    location = upstream_headers.get("Location")
    if location:
        try:
            absolute = urllib.parse.urljoin(target_url + "/", location)
            parsed_target = urllib.parse.urlparse(target_url)
            parsed_location = urllib.parse.urlparse(absolute)

            if (
                parsed_target.scheme == parsed_location.scheme
                and parsed_target.netloc == parsed_location.netloc
            ):
                proxied_path = parsed_location.path.lstrip("/")
                rewritten = "/target/" + proxied_path
                if parsed_location.query:
                    rewritten += "?" + parsed_location.query
                response.headers["Location"] = rewritten
            else:
                response.headers["Location"] = location
        except Exception:
            response.headers["Location"] = location

    return response


def _push_event(kind: str, code: str = "") -> dict:
    global _event_revision

    with _event_lock:
        _event_revision += 1
        event = {
            "revision": _event_revision,
            "type": kind,
            "code": code,
        }
        _events.append(event)
        return event


@app.get("/")
def root():
    return redirect("/panel")


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "app": "web-injector",
            "panel": True,
            "target_proxy": True,
            "injection_api": True,
        }
    )

@app.get("/game")
def game_index():
    return redirect("/target/")


@app.get("/legacy-game")
def legacy_game_index():
    return send_from_directory(GAME_DIR, "index.html")


@app.get("/legacy-game/<path:filename>")
def legacy_game_file(filename: str):
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


@app.route(
    "/target/",
    defaults={"filename": ""},
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
@app.route(
    "/target/<path:filename>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
def target_proxy(filename: str):
    target = _selected_target()

    if target.get("kind") == "builtin":
        return _builtin_response(filename)

    return _proxy_custom(target, filename)


@app.get("/api/targets")
def targets_list():
    data = _load_targets()
    return jsonify({"ok": True, **data})


@app.post("/api/targets/select")
def targets_select():
    payload = request.get_json(silent=True) or {}
    target_id = str(payload.get("id", "")).strip()

    data = _load_targets()
    ids = {str(item.get("id", "")) for item in data["targets"]}

    if target_id not in ids:
        return jsonify({"ok": False, "error": "Unknown target."}), 404

    data["selected"] = target_id
    _save_targets(data)
    _push_event("reload", "")

    return jsonify({"ok": True, "selected": target_id})


@app.post("/api/targets/add")
def targets_add():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    raw_url = str(payload.get("url", "")).strip()
    trust_public = bool(payload.get("trust_public", False))

    if not name:
        return jsonify({"ok": False, "error": "Give the target a name."}), 400

    try:
        url, host, requires_trust = _validate_target_url(raw_url)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    if requires_trust and not trust_public:
        return jsonify(
            {
                "ok": False,
                "requires_trust": True,
                "host": host,
                "error": (
                    f"{host} is a public domain. Confirm that you own or control "
                    "this site before adding it."
                ),
            }
        ), 409

    if requires_trust and trust_public:
        try:
            _trust_remote_host(host)
        except (OSError, ValueError) as exc:
            return jsonify(
                {
                    "ok": False,
                    "error": f"Could not save trusted domain: {exc}",
                }
            ), 500

    data = _load_targets()
    base_id = _slug(name)
    target_id = base_id
    used = {str(item.get("id", "")) for item in data["targets"]}

    counter = 2
    while target_id in used:
        target_id = f"{base_id}-{counter}"
        counter += 1

    item = {
        "id": target_id,
        "name": name[:64],
        "kind": "proxy",
        "url": url,
        "protected": False,
        "remote": requires_trust or _host_is_approved_remote(host),
    }

    data["targets"].append(item)
    data["selected"] = target_id
    _save_targets(data)
    _push_event("reload", "")

    return jsonify({"ok": True, "target": item, "selected": target_id})


@app.delete("/api/targets/<target_id>")
def targets_delete(target_id: str):
    data = _load_targets()
    target = next(
        (item for item in data["targets"] if item.get("id") == target_id),
        None,
    )

    if not target:
        return jsonify({"ok": False, "error": "Unknown target."}), 404

    if target.get("protected"):
        return jsonify({"ok": False, "error": "The built-in Test Game cannot be deleted."}), 400

    data["targets"] = [
        item for item in data["targets"] if item.get("id") != target_id
    ]

    if data.get("selected") == target_id:
        data["selected"] = "test-game"

    _save_targets(data)
    _push_event("reload", "")

    return jsonify({"ok": True, "selected": data["selected"]})


@app.get("/api/target/status")
def target_status():
    target = _selected_target()

    if target.get("kind") == "builtin":
        return jsonify(
            {
                "ok": True,
                "reachable": True,
                "target": target,
                "proxy": "/target/",
            }
        )

    target_url = str(target.get("url", "")).rstrip("/")

    try:
        req = urllib.request.Request(
            target_url + "/",
            headers={"User-Agent": "WebInjector/1.5"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2.5) as upstream:
            reachable = 200 <= upstream.status < 500
    except Exception:
        reachable = False

    payload = {
        "ok": reachable,
        "reachable": reachable,
        "target": target,
        "proxy": "/target/",
    }

    return jsonify(payload), (200 if reachable else 503)


@app.get("/api/target/revision")
def target_revision():
    with _event_lock:
        revision = _event_revision

    return jsonify({"ok": True, "revision": revision})


@app.get("/api/target/pending")
def target_pending():
    try:
        since = max(0, int(request.args.get("since", "0")))
    except ValueError:
        since = 0

    with _event_lock:
        pending = [event for event in _events if event["revision"] > since]
        latest = _event_revision

    return jsonify(
        {
            "ok": True,
            "revision": latest,
            "events": pending,
        }
    )


@app.post("/api/target/inject")
def target_inject():
    payload = request.get_json(silent=True) or {}
    kind = str(payload.get("type", "")).lower().strip()
    code = str(payload.get("code", ""))

    if kind not in {"html", "css", "js"}:
        return jsonify({"ok": False, "error": "type must be html, css or js"}), 400

    if not code.strip():
        return jsonify({"ok": False, "error": "Nothing to inject."}), 400

    if len(code) > 250_000:
        return jsonify({"ok": False, "error": "Injection is too large."}), 413

    event = _push_event(kind, code)

    return jsonify(
        {
            "ok": True,
            "revision": event["revision"],
            "type": kind,
        }
    )


@app.post("/api/target/reset")
def target_reset():
    event = _push_event("reload", "")
    return jsonify({"ok": True, "revision": event["revision"]})


@app.get("/injector-bridge.js")
def injector_bridge():
    javascript = r"""
(() => {
    if (window.__WEB_INJECTOR_BRIDGE__) return;
    window.__WEB_INJECTOR_BRIDGE__ = true;

    let revision = 0;

    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

    function addBadge() {
        if (document.getElementById("__wi_badge")) return;

        const badge = document.createElement("div");
        badge.id = "__wi_badge";
        badge.textContent = "WEB INJECTOR • CONNECTED";

        Object.assign(badge.style, {
            position: "fixed",
            left: "14px",
            bottom: "14px",
            zIndex: "2147483647",
            padding: "7px 10px",
            borderRadius: "999px",
            background: "rgba(10,12,20,.86)",
            border: "1px solid rgba(255,105,185,.55)",
            boxShadow: "0 0 24px rgba(255,105,185,.18)",
            color: "#ff91cf",
            font: "700 10px Inter, system-ui, sans-serif",
            letterSpacing: ".08em",
            backdropFilter: "blur(12px)",
            pointerEvents: "none"
        });

        document.body.appendChild(badge);
    }

    function injectHtml(code) {
        const template = document.createElement("template");
        template.innerHTML = code;

        template.content.querySelectorAll("script").forEach(oldScript => {
            const script = document.createElement("script");

            for (const attr of oldScript.attributes) {
                script.setAttribute(attr.name, attr.value);
            }

            script.textContent = oldScript.textContent;
            oldScript.replaceWith(script);
        });

        document.body.appendChild(template.content);
    }

    function injectCss(code, rev) {
        const style = document.createElement("style");
        style.dataset.webInjectorRevision = String(rev);
        style.textContent = code;
        document.head.appendChild(style);
    }

    function injectJs(code) {
        const fn = new Function(code);
        fn.call(window);
    }

    function apply(event) {
        try {
            if (event.type === "html") injectHtml(event.code);
            if (event.type === "css") injectCss(event.code, event.revision);
            if (event.type === "js") injectJs(event.code);
            if (event.type === "reload") location.reload();

            window.dispatchEvent(new CustomEvent("web-injector-applied", {
                detail: event
            }));
        } catch (error) {
            console.error("[Web Injector] Injection failed:", error);
        }
    }

    async function start() {
        addBadge();

        try {
            const initial = await fetch("/api/target/revision", { cache: "no-store" });
            const data = await initial.json();
            revision = Number(data.revision || 0);
        } catch (error) {
            console.warn("[Web Injector] Could not initialize:", error);
        }

        while (true) {
            try {
                const response = await fetch(
                    `/api/target/pending?since=${encodeURIComponent(revision)}`,
                    { cache: "no-store" }
                );

                const data = await response.json();

                for (const event of data.events || []) {
                    apply(event);
                    revision = Math.max(revision, Number(event.revision || 0));
                }

                revision = Math.max(revision, Number(data.revision || revision));
            } catch (error) {
                console.warn("[Web Injector] Poll failed:", error);
            }

            await sleep(300);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
        start();
    }
})();
"""

    return Response(
        javascript,
        content_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web Injector local development server")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind to")
    parser.add_argument("--port", type=int, default=5000, help="TCP port to listen on")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not 1 <= args.port <= 65535:
        raise SystemExit("Port must be between 1 and 65535")

    app.run(
        host=args.host,
        port=args.port,
        debug=False,
        threaded=True,
        use_reloader=False,
    )
