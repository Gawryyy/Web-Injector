from __future__ import annotations

import json
import math
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import messagebox
except ImportError as exc:
    raise SystemExit(
        "CustomTkinter is required. Activate your venv and run:\n"
        "  pip install -r requirements.txt\n"
        "Then start launcher.py again."
    ) from exc

try:
    from PIL import Image, ImageDraw, ImageOps
except ImportError as exc:
    raise SystemExit(
        "Pillow is required for the profile image. Activate your venv and run:\n"
        "  pip install Pillow\n"
        "Then start launcher.py again."
    ) from exc


ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / "launcher_settings.json"
SERVER_FILE = ROOT / "server.py"
PFP_FILE = ROOT / "assets" / "images" / "PFP.jpg"

WEBSITE_URL = "https://astraiii.com"
DISCORD_URL = "https://discord.gg/yjPgv6vEvW"

APP_VERSION = "v1.5"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C = {
    "bg": "#07090F",
    "sidebar": "#0A0D15",
    "surface": "#10141F",
    "surface2": "#151A27",
    "surface3": "#1B2130",
    "surface4": "#20283A",
    "line": "#252D3E",
    "line2": "#313A4D",
    "text": "#F8F5FC",
    "text2": "#D8D7E0",
    "muted": "#8F97AA",
    "pink": "#FF69B9",
    "pink2": "#FF9AD1",
    "purple": "#AE7BFF",
    "blue": "#67C4FF",
    "green": "#59E8A3",
    "red": "#FF667D",
    "orange": "#FFBF70",
    "gray": "#6D7588",
}

DEFAULT_SETTINGS = {
    "host": "127.0.0.1",
    "port": 5000,
    "auto_start": True,
    "open_game_on_start": True,
    "open_panel_on_start": True,
}

LOG_GRADIENT = [
    "#FF9AD1",
    "#FF82C6",
    "#E98CFF",
    "#C18BFF",
    "#9C9DFF",
    "#78B7FF",
    "#67C4FF",
]


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = rgb(a)
    br, bg, bb = rgb(b)
    return "#%02x%02x%02x" % (
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


def rounded_avatar(path: Path, size: int = 132) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image = ImageOps.fit(image, (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(image, (0, 0), mask)
    return out


class GradientText(ctk.CTkFrame):
    def __init__(
        self,
        master,
        text: str,
        *,
        font: tuple[str, int, str] = ("Inter", 24, "bold"),
        bg_color: str | tuple[str, str] = "transparent",
    ) -> None:
        super().__init__(master, fg_color=bg_color, corner_radius=0)
        colors = [C["pink2"], C["pink"], C["purple"], C["blue"]]
        count = max(1, len(text) - 1)
        for index, char in enumerate(text):
            p = index / count
            segment = min(2, int(p * 3))
            local = (p * 3) - segment
            color = mix(colors[segment], colors[segment + 1], local)
            ctk.CTkLabel(
                self,
                text=char,
                text_color=color,
                font=font,
                width=1,
            ).pack(side="left")


class StatusDot(tk.Canvas):
    def __init__(self, master, bg: str, size: int = 32) -> None:
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self.size = size
        self.state_name = "gray"
        self.phase = 0.0
        self.after(70, self._animate)

    def set_state(self, state: str) -> None:
        self.state_name = state
        self._draw()

    def _draw(self) -> None:
        color = {
            "green": C["green"],
            "red": C["red"],
            "gray": C["gray"],
        }.get(self.state_name, C["gray"])
        pulse = (math.sin(self.phase) + 1.0) / 2.0 if self.state_name != "gray" else 0.0
        self.delete("all")
        center = self.size / 2
        glow_r = 12 + pulse * 2.5
        self.create_oval(
            center - glow_r,
            center - glow_r,
            center + glow_r,
            center + glow_r,
            fill=mix(C["surface"], color, 0.10 + 0.10 * pulse),
            outline="",
        )
        self.create_oval(
            center - 8,
            center - 8,
            center + 8,
            center + 8,
            fill=mix(C["surface"], color, 0.35),
            outline="",
        )
        self.create_oval(
            center - 5,
            center - 5,
            center + 5,
            center + 5,
            fill=color,
            outline="",
        )

    def _animate(self) -> None:
        if self.winfo_exists():
            self.phase += 0.23
            self._draw()
            self.after(70, self._animate)


class StatusCard(ctk.CTkFrame):
    def __init__(self, master, icon: str, title: str) -> None:
        super().__init__(
            master,
            fg_color=C["surface"],
            border_color=C["line"],
            border_width=1,
            corner_radius=22,
        )
        self.grid_columnconfigure(0, weight=1)
        self.icon = ctk.CTkLabel(
            self,
            text=icon,
            width=34,
            height=34,
            corner_radius=11,
            fg_color=C["surface2"],
            text_color=C["pink2"],
            font=("Inter", 15, "bold"),
        )
        self.icon.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 9))
        self.dot = StatusDot(self, C["surface"], 34)
        self.dot.grid(row=0, column=1, sticky="e", padx=12, pady=(14, 8))
        self.title = ctk.CTkLabel(
            self,
            text=title,
            text_color=C["text"],
            font=("Inter", 11, "bold"),
            anchor="w",
        )
        self.title.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16)
        self.status = ctk.CTkLabel(
            self,
            text="Disconnected",
            text_color=C["muted"],
            font=("Inter", 9),
            anchor="w",
        )
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 16))

    def set_state(self, state: str, text: str) -> None:
        color = {
            "green": C["green"],
            "red": C["red"],
            "gray": C["muted"],
        }.get(state, C["muted"])
        self.dot.set_state(state)
        self.status.configure(text=text, text_color=color)


class WebInjectorLauncher:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("Web Injector")
        self.root.geometry("1220x790")
        self.root.minsize(1030, 690)
        self.root.configure(fg_color=C["bg"])

        try:
            self.root.attributes("-alpha", 0.995)
        except tk.TclError:
            pass

        self.settings = self.load_settings()
        self.server_process: subprocess.Popen[str] | None = None
        self.attached_external_server = False
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._probe_running = False
        self._probe_loop_started = False
        self._last_probe_results: dict[str, bool] | None = None
        self._closing = False
        self.started_at = time.time()
        self.current_page = "dashboard"
        self.log_color_index = 0

        self.host_var = tk.StringVar(value=str(self.settings["host"]))
        self.port_var = tk.StringVar(value=str(self.settings["port"]))
        self.auto_start_var = tk.BooleanVar(value=bool(self.settings["auto_start"]))
        self.open_game_var = tk.BooleanVar(value=bool(self.settings["open_game_on_start"]))
        self.open_panel_var = tk.BooleanVar(value=bool(self.settings["open_panel_on_start"]))

        self._build_ui()
        self._set_all_statuses("gray")
        self._update_endpoint_labels()
        self._update_runtime_labels()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._drain_log_queue)
        self.root.after(500, self._start_probe_loop)
        self.root.after(1000, self._tick_runtime)
        self._fade_in()

        self.log("Launcher initialized.", "INFO")
        self.log(f"Python {sys.version.split()[0]} • {sys.platform}", "INFO")

        if self.settings["auto_start"]:
            self.root.after(550, self.start_server)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self.root,
            width=224,
            corner_radius=0,
            fg_color=C["sidebar"],
            border_width=0,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(8, weight=1)

        self.content = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        self._build_sidebar()
        self._build_topbar()

        self.page_host = ctk.CTkFrame(self.content, fg_color="transparent", corner_radius=0)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.pages: dict[str, ctk.CTkFrame] = {
            "dashboard": self._build_dashboard_page(),
            "settings": self._build_settings_page(),
            "info": self._build_info_page(),
            "credits": self._build_credits_page(),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.show_page("dashboard")

    def _build_sidebar(self) -> None:
        brand_card = ctk.CTkFrame(
            self.sidebar,
            fg_color=C["surface"],
            corner_radius=22,
            border_color=C["line"],
            border_width=1,
        )
        brand_card.grid(row=0, column=0, sticky="ew", padx=14, pady=(18, 22))
        brand_card.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkLabel(
            brand_card,
            text="✦",
            width=42,
            height=42,
            corner_radius=15,
            fg_color="#26172F",
            text_color=C["pink2"],
            font=("Inter", 20, "bold"),
        )
        logo.grid(row=0, column=0, padx=(12, 9), pady=12)

        brand_text = ctk.CTkFrame(brand_card, fg_color="transparent", corner_radius=0)
        brand_text.grid(row=0, column=1, sticky="w")
        GradientText(brand_text, "WEB INJECTOR", font=("Inter", 11, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            brand_text,
            text=f"Gawr  •  {APP_VERSION}",
            text_color=C["muted"],
            font=("Inter", 8, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        ctk.CTkLabel(
            self.sidebar,
            text="WORKSPACE",
            text_color=C["gray"],
            font=("Inter", 8, "bold"),
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        nav_items = [
            ("dashboard", "◉", "Dashboard"),
            ("settings", "⚙", "Settings"),
            ("info", "ⓘ", "Info"),
            ("credits", "✦", "Credits"),
        ]
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for row, (key, icon, label) in enumerate(nav_items, start=2):
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"{icon}     {label}",
                command=lambda k=key: self.show_page(k),
                height=44,
                corner_radius=14,
                anchor="w",
                fg_color="transparent",
                hover_color=C["surface2"],
                text_color=C["muted"],
                font=("Inter", 10, "bold"),
            )
            btn.grid(row=row, column=0, sticky="ew", padx=13, pady=3)
            self.nav_buttons[key] = btn

        bottom = ctk.CTkFrame(
            self.sidebar,
            fg_color=C["surface"],
            corner_radius=18,
            border_color=C["line"],
            border_width=1,
        )
        bottom.grid(row=9, column=0, sticky="sew", padx=14, pady=16)
        bottom.grid_columnconfigure(1, weight=1)
        self.sidebar_dot = StatusDot(bottom, C["surface"], 30)
        self.sidebar_dot.grid(row=0, column=0, padx=(10, 2), pady=9)
        self.sidebar_state_label = ctk.CTkLabel(
            bottom,
            text="Disconnected",
            text_color=C["muted"],
            font=("Inter", 9, "bold"),
            anchor="w",
        )
        self.sidebar_state_label.grid(row=0, column=1, sticky="w", padx=(0, 10))

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self.content, fg_color="transparent", corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 12))
        bar.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(bar, fg_color="transparent", corner_radius=0)
        left.grid(row=0, column=0, sticky="w")
        self.page_title = ctk.CTkLabel(
            left,
            text="Dashboard",
            text_color=C["text"],
            font=("Inter", 25, "bold"),
            anchor="w",
        )
        self.page_title.pack(anchor="w")
        self.page_subtitle = ctk.CTkLabel(
            left,
            text="web environment",
            text_color=C["muted"],
            font=("Inter", 9),
            anchor="w",
        )
        self.page_subtitle.pack(anchor="w", pady=(1, 0))

        right = ctk.CTkFrame(bar, fg_color="transparent", corner_radius=0)
        right.grid(row=0, column=1, sticky="e")
        self.endpoint_pill = ctk.CTkLabel(
            right,
            text="127.0.0.1:5000",
            height=36,
            corner_radius=13,
            fg_color=C["surface"],
            text_color=C["text2"],
            font=("JetBrains Mono", 9, "bold"),
            width=150,
        )
        self.endpoint_pill.pack(side="left", padx=(0, 8))
        self.live_pill = ctk.CTkLabel(
            right,
            text="●  OFFLINE",
            height=36,
            corner_radius=13,
            fg_color=C["surface"],
            text_color=C["gray"],
            font=("Inter", 9, "bold"),
            width=120,
        )
        self.live_pill.pack(side="left")

    def show_page(self, key: str) -> None:
        self.current_page = key
        titles = {
            "dashboard": ("Dashboard", "Start, monitor and control your web environment"),
            "settings": ("Settings", "Server and launch behavior"),
            "info": ("Info", "What this web injector is for"),
            "credits": ("Credits", "Project creator and links"),
        }
        title, subtitle = titles[key]
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        self.pages[key].tkraise()
        for name, btn in self.nav_buttons.items():
            if name == key:
                btn.configure(fg_color=C["surface2"], text_color=C["text"])
            else:
                btn.configure(fg_color="transparent", text_color=C["muted"])

    # ---------- common UI helpers ----------
    def _card(self, parent, *, corner: int = 22, fg: str | None = None) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=fg or C["surface"],
            corner_radius=corner,
            border_color=C["line"],
            border_width=1,
        )

    def _section(self, parent, title: str, subtitle: str = "") -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        ctk.CTkLabel(
            box,
            text=title,
            text_color=C["text"],
            font=("Inter", 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        if subtitle:
            ctk.CTkLabel(
                box,
                text=subtitle,
                text_color=C["muted"],
                font=("Inter", 8),
                anchor="w",
            ).pack(fill="x", pady=(2, 0))
        return box

    def _button(self, parent, text: str, command, *, accent=False, danger=False, width=0) -> ctk.CTkButton:
        if accent:
            fg = C["pink"]
            hover = C["purple"]
            text_color = "#090A0E"
        elif danger:
            fg = "#2A1720"
            hover = "#3A1C27"
            text_color = C["red"]
        else:
            fg = C["surface2"]
            hover = C["surface3"]
            text_color = C["text2"]
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=42,
            width=width if width > 0 else 140,
            corner_radius=14,
            fg_color=fg,
            hover_color=hover,
            text_color=text_color,
            font=("Inter", 10, "bold"),
            border_width=1 if not accent else 0,
            border_color=C["line2"],
        )

    def _build_dashboard_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_host, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        hero = self._card(page, corner=26)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        hero.grid_columnconfigure(0, weight=1)

        hero_left = ctk.CTkFrame(hero, fg_color="transparent", corner_radius=0)
        hero_left.grid(row=0, column=0, sticky="w", padx=22, pady=20)
        GradientText(hero_left, "WEB INJECTION", font=("Inter", 21, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            hero_left,
            text="A polished sandbox for state changes, DOM injection and live browser tooling.",
            text_color=C["muted"],
            font=("Inter", 9),
        ).pack(anchor="w", pady=(4, 0))

        actions = ctk.CTkFrame(hero, fg_color="transparent", corner_radius=0)
        actions.grid(row=0, column=1, sticky="e", padx=20, pady=20)
        self.start_button = self._button(actions, "▶  Start server", self.start_server, accent=True)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = self._button(actions, "■  Stop", self.stop_server, danger=True)
        self.stop_button.pack(side="left")

        status_wrap = ctk.CTkFrame(page, fg_color="transparent", corner_radius=0)
        status_wrap.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for i in range(4):
            status_wrap.grid_columnconfigure(i, weight=1, uniform="status")
        self.status_server = StatusCard(status_wrap, "◈", "Server")
        self.status_game = StatusCard(status_wrap, "▶", "Selected target")
        self.status_panel = StatusCard(status_wrap, "⌘", "Control panel")
        self.status_injection = StatusCard(status_wrap, "⚡", "Injection API")
        cards = (self.status_server, self.status_game, self.status_panel, self.status_injection)
        for i, card in enumerate(cards):
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == 3 else 5))

        lower = ctk.CTkFrame(page, fg_color="transparent", corner_radius=0)
        lower.grid(row=2, column=0, sticky="nsew")
        lower.grid_columnconfigure(0, weight=0, minsize=305)
        lower.grid_columnconfigure(1, weight=1)
        lower.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(lower, fg_color="transparent", corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        quick = self._card(left)
        quick.pack(fill="x", pady=(0, 12))
        self._section(quick, "Quick launch", "Open either side of the web environment").pack(fill="x", padx=18, pady=(17, 12))
        self._button(quick, "◎  Open selected target", self.open_game).pack(fill="x", padx=18, pady=(0, 7))
        self._button(quick, "⌘  Open control panel", self.open_panel).pack(fill="x", padx=18, pady=(0, 18))

        runtime = self._card(left)
        runtime.pack(fill="x")
        self._section(runtime, "Runtime", "Current launcher session").pack(fill="x", padx=18, pady=(17, 11))
        self.runtime_endpoint = self._info_row(runtime, "Endpoint", "-")
        self.runtime_uptime = self._info_row(runtime, "Uptime", "00:00:00")
        self.runtime_pid = self._info_row(runtime, "Process", "Not running", last=True)

        log_card = self._card(lower, corner=22)
        log_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)

        log_head = ctk.CTkFrame(log_card, fg_color="transparent", corner_radius=0)
        log_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(15, 8))
        log_head.grid_columnconfigure(0, weight=1)
        GradientText(log_head, "LIVE ACTIVITY", font=("Inter", 11, "bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            log_head,
            text="Clear",
            command=self.clear_logs,
            width=68,
            height=30,
            corner_radius=11,
            fg_color=C["surface2"],
            hover_color=C["surface3"],
            text_color=C["muted"],
            font=("Inter", 8, "bold"),
        ).grid(row=0, column=1, sticky="e")

        log_inner = ctk.CTkFrame(log_card, fg_color="#0A0D14", corner_radius=16)
        log_inner.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        log_inner.grid_rowconfigure(0, weight=1)
        log_inner.grid_columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_inner,
            bg="#0A0D14",
            fg=C["text2"],
            insertbackground=C["text"],
            selectbackground=C["purple"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=12,
            wrap="word",
            font=("JetBrains Mono", 9),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.log_text.configure(state="disabled")
        self.log_text.tag_configure("timestamp", foreground=C["gray"])
        self.log_text.tag_configure("INFO", foreground=C["blue"])
        self.log_text.tag_configure("OK", foreground=C["green"])
        self.log_text.tag_configure("WARN", foreground=C["orange"])
        self.log_text.tag_configure("ERROR", foreground=C["red"])
        self.log_text.tag_configure("SERVER", foreground=C["purple"])
        for i, color in enumerate(LOG_GRADIENT):
            self.log_text.tag_configure(f"g{i}", foreground=color)
        return page

    def _build_settings_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_host, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure((0, 1), weight=1, uniform="settings")

        server = self._card(page, corner=24)
        server.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._section(server, "Server", "Choose where the Flask server listens").pack(fill="x", padx=22, pady=(20, 18))
        self._setting_entry(server, "Host", "127.0.0.1 keeps this project local to your computer.", self.host_var)
        self._setting_entry(server, "Port", "Choose a TCP port between 1024 and 65535.", self.port_var)
        self._button(server, "Save server settings", self.save_settings_from_controls, accent=True).pack(anchor="w", padx=22, pady=(7, 22))

        behavior = self._card(page, corner=24)
        behavior.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._section(behavior, "Launch behavior", "Choose what happens when the launcher starts").pack(fill="x", padx=22, pady=(20, 12))
        self._toggle_row(behavior, "Auto-start server", "Start the local server when this launcher opens.", self.auto_start_var)
        self._toggle_row(behavior, "Open selected target", "Open the currently selected web target through the injector proxy.", self.open_game_var)
        self._toggle_row(behavior, "Open control panel", "Open the panel after a successful connection.", self.open_panel_var)
        self._button(behavior, "Save launch behavior", self.save_settings_from_controls).pack(anchor="w", padx=22, pady=(10, 22))

        note = ctk.CTkFrame(
            page,
            fg_color="#111426",
            corner_radius=20,
            border_color="#29224A",
            border_width=1,
        )
        note.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(note, text="✦", width=36, height=36, corner_radius=12, fg_color="#281C3A", text_color=C["pink2"], font=("Inter", 17, "bold")).pack(side="left", padx=(16, 10), pady=14)
        text = ctk.CTkFrame(note, fg_color="transparent", corner_radius=0)
        text.pack(side="left", fill="x", expand=True, pady=13)
        ctk.CTkLabel(text, text="Local by design", text_color=C["pink2"], font=("Inter", 10, "bold")).pack(anchor="w")
        ctk.CTkLabel(text, text="The default 127.0.0.1 host keeps the game and injector panel on this computer.", text_color=C["muted"], font=("Inter", 9)).pack(anchor="w", pady=(2, 0))
        return page

    def _build_info_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_host, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure(0, weight=1)

        hero = self._card(page, corner=26)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(
            hero,
            text="LOCAL TEST PROJECT",
            height=28,
            corner_radius=10,
            fg_color="#26182F",
            text_color=C["pink2"],
            font=("Inter", 8, "bold"),
            width=145,
        ).pack(anchor="w", padx=24, pady=(22, 10))
        GradientText(hero, "BUILT TO LEARN THE WEB", font=("Inter", 20, "bold")).pack(anchor="w", padx=24)
        ctk.CTkLabel(
            hero,
            text=(
                "Web Injector runs a test game and a control panel on your own computer. "
                "The panel can change the test game's state and send HTML, CSS or JavaScript "
                "into that web page so you can see how DOM changes, APIs, Python backends "
                "and live updates work together."
            ),
            text_color=C["text2"],
            font=("Inter", 10),
            justify="left",
            wraplength=820,
            anchor="w",
        ).pack(fill="x", padx=24, pady=(10, 24))

        cols = ctk.CTkFrame(page, fg_color="transparent", corner_radius=0)
        cols.grid(row=1, column=0, sticky="ew")
        cols.grid_columnconfigure((0, 1), weight=1, uniform="info")

        learn = self._card(cols)
        learn.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._section(learn, "What you can learn", "Useful pieces behind the demo").pack(fill="x", padx=20, pady=(19, 12))
        for item in ("Python + Flask server", "HTTP APIs and JSON", "Live browser updates", "DOM / HTML / CSS / JavaScript", "Client ↔ server architecture"):
            row = ctk.CTkFrame(learn, fg_color=C["surface2"], corner_radius=13)
            row.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(row, text="✦", text_color=C["pink2"], width=28, font=("Inter", 10, "bold")).pack(side="left", padx=(8, 0), pady=8)
            ctk.CTkLabel(row, text=item, text_color=C["text2"], font=("Inter", 9), anchor="w").pack(side="left", fill="x", expand=True, pady=8)
        ctk.CTkFrame(learn, fg_color="transparent", height=12).pack()

        scope = self._card(cols)
        scope.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._section(scope, "Project scope", "A web sandbox, not a random-site tool").pack(fill="x", padx=20, pady=(19, 12))
        ctk.CTkLabel(
            scope,
            text=(
                "This starter project is intentionally aimed at the included local test game. "
                "It gives you a controlled place to experiment with browser behavior, state changes "
                "and injection concepts without relying on unrelated websites."
            ),
            text_color=C["text2"],
            font=("Inter", 9),
            justify="left",
            wraplength=390,
            anchor="nw",
        ).pack(fill="both", expand=True, padx=20, pady=(0, 20))
        return page

    def _build_credits_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_host, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure(0, weight=1)

        card = self._card(page, corner=28)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        avatar_wrap = ctk.CTkFrame(
            card,
            fg_color="#1A1326",
            corner_radius=74,
            width=148,
            height=148,
            border_width=2,
            border_color=C["purple"],
        )
        avatar_wrap.grid(row=0, column=0, rowspan=4, padx=(28, 24), pady=28, sticky="n")
        avatar_wrap.grid_propagate(False)

        if PFP_FILE.exists():
            try:
                avatar = rounded_avatar(PFP_FILE, 128)
                self.pfp_image = ctk.CTkImage(light_image=avatar, dark_image=avatar, size=(128, 128))
                ctk.CTkLabel(avatar_wrap, text="", image=self.pfp_image).place(relx=0.5, rely=0.5, anchor="center")
            except Exception:
                self._avatar_fallback(avatar_wrap)
        else:
            self._avatar_fallback(avatar_wrap)

        name_area = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
        name_area.grid(row=0, column=1, sticky="sw", padx=(0, 28), pady=(32, 0))
        GradientText(name_area, "GAWR", font=("Inter", 29, "bold")).pack(anchor="w")
        ctk.CTkLabel(name_area, text="Creator / developer", text_color=C["pink2"], font=("Inter", 10, "bold")).pack(anchor="w", pady=(3, 0))

        ctk.CTkLabel(
            card,
            text="Web Injector",
            text_color=C["muted"],
            font=("Inter", 9),
            anchor="w",
        ).grid(row=1, column=1, sticky="nw", padx=(0, 28), pady=(8, 0))

        divider = ctk.CTkFrame(card, height=1, fg_color=C["line"], corner_radius=1)
        divider.grid(row=2, column=1, sticky="ew", padx=(0, 28), pady=(16, 14))

        buttons = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
        buttons.grid(row=3, column=1, sticky="nw", padx=(0, 28), pady=(0, 32))
        self._button(buttons, "🌐  Website", self.open_website, accent=True).pack(side="left", padx=(0, 9))
        self._button(buttons, "◈  Discord", self.open_discord).pack(side="left")

        foot = ctk.CTkLabel(
            page,
            text=f"Web Injector {APP_VERSION}  •  web test environment",
            text_color=C["gray"],
            font=("JetBrains Mono", 8),
        )
        foot.grid(row=1, column=0, sticky="w", pady=(12, 0))
        return page

    def _avatar_fallback(self, parent) -> None:
        ctk.CTkLabel(
            parent,
            text="PFP.jpg\nnot found",
            text_color=C["muted"],
            font=("Inter", 9, "bold"),
            justify="center",
        ).place(relx=0.5, rely=0.5, anchor="center")

    def _setting_entry(self, parent, title: str, subtitle: str, variable: tk.StringVar) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        box.pack(fill="x", padx=22, pady=(0, 15))
        ctk.CTkLabel(box, text=title, text_color=C["text"], font=("Inter", 9, "bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(box, text=subtitle, text_color=C["muted"], font=("Inter", 8), anchor="w").pack(fill="x", pady=(2, 7))
        ctk.CTkEntry(
            box,
            textvariable=variable,
            height=42,
            corner_radius=14,
            fg_color="#0B0F18",
            border_color=C["line2"],
            border_width=1,
            text_color=C["text2"],
            placeholder_text_color=C["gray"],
            font=("JetBrains Mono", 10),
        ).pack(fill="x")

    def _toggle_row(self, parent, title: str, subtitle: str, variable: tk.BooleanVar) -> None:
        row = ctk.CTkFrame(parent, fg_color=C["surface2"], corner_radius=15)
        row.pack(fill="x", padx=20, pady=5)
        row.grid_columnconfigure(0, weight=1)
        text = ctk.CTkFrame(row, fg_color="transparent", corner_radius=0)
        text.grid(row=0, column=0, sticky="ew", padx=14, pady=11)
        ctk.CTkLabel(text, text=title, text_color=C["text"], font=("Inter", 9, "bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(text, text=subtitle, text_color=C["muted"], font=("Inter", 8), anchor="w").pack(fill="x", pady=(1, 0))
        ctk.CTkSwitch(
            row,
            text="",
            variable=variable,
            width=48,
            height=25,
            corner_radius=13,
            fg_color=C["surface4"],
            progress_color=C["purple"],
            button_color=C["text"],
            button_hover_color=C["pink2"],
        ).grid(row=0, column=1, padx=(8, 14))

    def _info_row(self, parent, key: str, value: str, *, last=False) -> ctk.CTkLabel:
        row = ctk.CTkFrame(parent, fg_color=C["surface2"], corner_radius=13)
        row.pack(fill="x", padx=16, pady=(0, 10 if not last else 16))
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text=key, text_color=C["muted"], font=("Inter", 8, "bold")).grid(row=0, column=0, sticky="w", padx=11, pady=9)
        label = ctk.CTkLabel(row, text=value, text_color=C["text2"], font=("JetBrains Mono", 8, "bold"), anchor="e")
        label.grid(row=0, column=1, sticky="e", padx=11, pady=9)
        return label

    # ---------- settings ----------
    def load_settings(self) -> dict:
        settings = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for key in DEFAULT_SETTINGS:
                        if key in loaded:
                            settings[key] = loaded[key]
            except (OSError, json.JSONDecodeError):
                pass
        return settings

    def save_settings_from_controls(self) -> None:
        host = self.host_var.get().strip() or "127.0.0.1"
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be a number between 1024 and 65535.")
            return
        if not 1024 <= port <= 65535:
            messagebox.showerror("Invalid port", "Port must be between 1024 and 65535.")
            return
        old_endpoint = (self.settings["host"], self.settings["port"])
        self.settings.update(
            {
                "host": host,
                "port": port,
                "auto_start": bool(self.auto_start_var.get()),
                "open_game_on_start": bool(self.open_game_var.get()),
                "open_panel_on_start": bool(self.open_panel_var.get()),
            }
        )
        SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        self._update_endpoint_labels()
        self.log("Settings saved.", "OK")
        if self.is_running() and old_endpoint != (host, port):
            self.log("Endpoint changed. Restart the server to apply it.", "WARN")

    # ---------- URLs ----------
    @property
    def base_url(self) -> str:
        host = str(self.settings["host"])
        browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        return f"http://{browser_host}:{int(self.settings['port'])}"

    def _update_endpoint_labels(self) -> None:
        endpoint = f"{self.settings['host']}:{self.settings['port']}"
        if hasattr(self, "endpoint_pill"):
            self.endpoint_pill.configure(text=endpoint)
        if hasattr(self, "runtime_endpoint"):
            self.runtime_endpoint.configure(text=endpoint)

    def open_game(self) -> None:
        webbrowser.open(f"{self.base_url}/target/")
        self.log("Opening selected target.", "INFO")

    def open_panel(self) -> None:
        webbrowser.open(f"{self.base_url}/panel")
        self.log("Opening control panel.", "INFO")

    def open_website(self) -> None:
        webbrowser.open(WEBSITE_URL)
        self.log("Opening website.", "INFO")

    def open_discord(self) -> None:
        if DISCORD_URL:
            webbrowser.open(DISCORD_URL)
            self.log("Opening Discord.", "INFO")
        else:
            messagebox.showinfo(
                "Discord link not set",
                "Set DISCORD_URL near the top of launcher.py to your Discord invite/profile URL.",
            )
            self.log("Discord link is not configured yet.", "WARN")

    # ---------- server lifecycle ----------
    def is_running(self) -> bool:
        return self.server_process is not None and self.server_process.poll() is None

    def _port_is_free(self, host: str, port: int) -> bool:
        bind_host = host if host != "::" else "::1"
        family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.4)
            sock.bind((bind_host, port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    def start_server(self) -> None:
        if self.is_running():
            self.log("Server is already running.", "WARN")
            return
        try:
            port = int(self.port_var.get().strip())
            if 1024 <= port <= 65535:
                self.settings["host"] = self.host_var.get().strip() or "127.0.0.1"
                self.settings["port"] = port
                self._update_endpoint_labels()
        except ValueError:
            pass

        host = str(self.settings["host"])
        port = int(self.settings["port"])
        self.attached_external_server = False
        self._set_all_statuses("gray")
        self.status_server.set_state("gray", "Starting…")
        self._set_global_state("gray", "STARTING")
        self.log(f"Starting local server on {host}:{port}…", "INFO")

        if not self._port_is_free(host, port):
            if self._probe_url(f"{self.base_url}/health"):
                self.attached_external_server = True
                self.log("Existing Web Injector server found. Attached to it.", "OK")
                self._schedule_probe(force=True)
                return
            self.status_server.set_state("red", "Port unavailable")
            self._set_global_state("red", "OFFLINE")
            self.log(f"Port {port} is already in use. Choose another port in Settings.", "ERROR")
            return

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        cmd = [sys.executable, "-u", str(SERVER_FILE), "--host", host, "--port", str(port)]
        try:
            self.server_process = subprocess.Popen(
                cmd,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except OSError as exc:
            self.status_server.set_state("red", "Failed to start")
            self._set_global_state("red", "OFFLINE")
            self.log(f"Could not start server: {exc}", "ERROR")
            return
        threading.Thread(target=self._read_server_output, daemon=True).start()
        threading.Thread(target=self._wait_for_server_start, daemon=True).start()
        self._update_runtime_labels()

    def _wait_for_server_start(self) -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline and not self._closing:
            if self.server_process and self.server_process.poll() is not None:
                code = self.server_process.returncode
                self.root.after(0, lambda: self._server_start_failed(f"Server exited with code {code}."))
                return
            if self._probe_url(f"{self.base_url}/health"):
                self.root.after(0, self._server_connected)
                return
            time.sleep(0.15)
        self.root.after(0, lambda: self._server_start_failed("Server did not become ready in time."))

    def _server_connected(self) -> None:
        self.log("Connected to server.", "OK")
        self.status_server.set_state("green", "Online")
        self._set_global_state("green", "ONLINE")
        self._schedule_probe(force=True)
        self._update_runtime_labels()
        if self.settings.get("open_game_on_start"):
            self.open_game()
        if self.settings.get("open_panel_on_start"):
            self.root.after(250, self.open_panel)

    def _server_start_failed(self, reason: str) -> None:
        self.status_server.set_state("red", "Offline")
        self._set_global_state("red", "OFFLINE")
        self.log(reason, "ERROR")
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        self.server_process = None
        self._update_runtime_labels()

    def stop_server(self) -> None:
        if self.attached_external_server and not self.is_running():
            self.log("External server detached; launcher did not terminate it.", "WARN")
            self.attached_external_server = False
            self._set_all_statuses("gray")
            self._set_global_state("gray", "DISCONNECTED")
            return
        if not self.is_running():
            self.log("Server is not running.", "WARN")
            self._set_all_statuses("gray")
            self._set_global_state("gray", "DISCONNECTED")
            return
        self.log("Stopping server…", "INFO")
        assert self.server_process is not None
        self.server_process.terminate()
        try:
            self.server_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.server_process.kill()
            self.server_process.wait(timeout=2)
        self.server_process = None
        self._set_all_statuses("gray")
        self._set_global_state("gray", "DISCONNECTED")
        self._update_runtime_labels()
        self.log("Server stopped.", "INFO")

    def _read_server_output(self) -> None:
        process = self.server_process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            clean = line.rstrip()
            if clean:
                self.log_queue.put((clean, "SERVER"))
        if not self._closing and process.returncode not in (None, 0, -15):
            self.log_queue.put((f"Server process ended with code {process.returncode}.", "ERROR"))

    # ---------- probes ----------
    def _probe_url(self, url: str) -> bool:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "WebInjectorLauncher/1.3"})
            with urllib.request.urlopen(request, timeout=0.55) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _start_probe_loop(self) -> None:
        if self._probe_loop_started or self._closing:
            return
        self._probe_loop_started = True
        self._schedule_probe()

    def _schedule_probe(self, force: bool = False) -> None:
        if self._closing:
            return
        if force or not self._probe_running:
            self._probe_running = True
            threading.Thread(target=self._probe_services, daemon=True).start()
        if self._probe_loop_started:
            self.root.after(1800, self._schedule_probe)

    def _probe_services(self) -> None:
        base = self.base_url
        results = {
            "server": self._probe_url(f"{base}/health"),
            "game": self._probe_url(f"{base}/api/target/status"),
            "panel": self._probe_url(f"{base}/panel"),
            "injection": self._probe_url(f"{base}/api/state"),
        }
        self._probe_running = False
        if not self._closing:
            self.root.after(0, lambda: self._apply_probe_results(results))

    def _apply_probe_results(self, results: dict[str, bool]) -> None:
        expected = self.is_running() or self.attached_external_server
        previous = self._last_probe_results
        if results["server"]:
            self.status_server.set_state("green", "Online")
        else:
            self.status_server.set_state("red" if expected else "gray", "Offline" if expected else "Disconnected")

        mapping = [
            (self.status_game, "game", "Reachable"),
            (self.status_panel, "panel", "Reachable"),
            (self.status_injection, "injection", "Working"),
        ]
        for widget, key, ok_text in mapping:
            if results[key]:
                widget.set_state("green", ok_text)
            elif expected:
                widget.set_state("red", "Not responding")
            else:
                widget.set_state("gray", "Disconnected")

        if all(results.values()):
            self._set_global_state("green", "ONLINE")
        elif any(results.values()) or expected:
            self._set_global_state("red", "DEGRADED")
        else:
            self._set_global_state("gray", "DISCONNECTED")

        if previous is not None:
            if results["server"] and not previous["server"]:
                self.log("Server connection restored.", "OK")
            elif previous["server"] and not results["server"] and expected:
                self.log("Lost connection to server.", "ERROR")
            if results["game"] and not previous["game"]:
                self.log("Test game is reachable.", "OK")
            if results["panel"] and not previous["panel"]:
                self.log("Control panel is reachable.", "OK")
            if results["injection"] and not previous["injection"]:
                self.log("Injection API is working.", "OK")
            elif previous["injection"] and not results["injection"] and expected:
                self.log("Injection API stopped responding.", "ERROR")
        elif results["injection"]:
            self.log("Injection API is working.", "OK")

        self._last_probe_results = dict(results)
        self._update_runtime_labels()

    # ---------- status / logs ----------
    def _set_all_statuses(self, state: str) -> None:
        text = "Disconnected" if state == "gray" else "Offline"
        for item in (self.status_server, self.status_game, self.status_panel, self.status_injection):
            item.set_state(state, text)

    def _set_global_state(self, state: str, text: str) -> None:
        color = {"green": C["green"], "red": C["red"], "gray": C["gray"]}.get(state, C["gray"])
        if hasattr(self, "live_pill"):
            self.live_pill.configure(text=f"●  {text}", text_color=color)
        if hasattr(self, "sidebar_dot"):
            self.sidebar_dot.set_state(state)
        if hasattr(self, "sidebar_state_label"):
            display = text.capitalize() if text != "ONLINE" else "Online"
            self.sidebar_state_label.configure(text=display, text_color=color if state != "gray" else C["muted"])

    def log(self, message: str, level: str = "INFO") -> None:
        self.log_queue.put((message, level))

    def _drain_log_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                message, level = self.log_queue.get_nowait()
                self._append_log(message, level)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log_queue)

    def _append_log(self, message: str, level: str) -> None:
        if not hasattr(self, "log_text"):
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        level = level.upper()
        gradient_tag = f"g{self.log_color_index % len(LOG_GRADIENT)}"
        self.log_color_index += 1
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{stamp}  ", "timestamp")
        self.log_text.insert("end", f"{level:<7}", level if level in {"INFO", "OK", "WARN", "ERROR", "SERVER"} else gradient_tag)
        self.log_text.insert("end", "  ")
        self.log_text.insert("end", message + "\n", gradient_tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_logs(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log_color_index = 0

    # ---------- runtime ----------
    def _update_runtime_labels(self) -> None:
        if not hasattr(self, "runtime_pid"):
            return
        if self.is_running() and self.server_process:
            self.runtime_pid.configure(text=f"PID {self.server_process.pid}")
        elif self.attached_external_server:
            self.runtime_pid.configure(text="External")
        else:
            self.runtime_pid.configure(text="Not running")
        self._update_endpoint_labels()

    def _tick_runtime(self) -> None:
        if self._closing:
            return
        elapsed = int(time.time() - self.started_at)
        hours, rem = divmod(elapsed, 3600)
        minutes, seconds = divmod(rem, 60)
        if hasattr(self, "runtime_uptime"):
            self.runtime_uptime.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        self.root.after(1000, self._tick_runtime)

    def _fade_in(self) -> None:
        try:
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            return

        def step(alpha: float = 0.0) -> None:
            if self._closing:
                return
            alpha = min(0.995, alpha + 0.065)
            try:
                self.root.attributes("-alpha", alpha)
            except tk.TclError:
                return
            if alpha < 0.995:
                self.root.after(16, lambda: step(alpha))

        self.root.after(10, step)

    def on_close(self) -> None:
        self._closing = True
        if self.is_running() and self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=1.5)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
        self.root.destroy()


def main() -> None:
    root = ctk.CTk()
    WebInjectorLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
