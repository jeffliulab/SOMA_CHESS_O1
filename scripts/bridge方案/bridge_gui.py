"""bridge_gui.py — SOMA Gamepad Bridge GUI.

Manages bridge_worker.py as a subprocess.  If XInput DLL causes a C-level
crash inside the worker, only the worker process dies.  The GUI survives,
logs the event, and auto-restarts the worker after 3 seconds.

Requirements (Windows Python):
    pip install XInput-Python
    (tkinter is built into Python — no extra install needed)

Usage:
    python \\\\wsl$\\Ubuntu-22.04\\home\\jeffliu\\SOMA\\soma-arm\\scripts\\bridge方案\\bridge_gui.py
"""

from __future__ import annotations

import json
import logging
import queue
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import scrolledtext

# Ignore Ctrl+C so an accidental keypress in the terminal doesn't kill the GUI.
signal.signal(signal.SIGINT, signal.SIG_IGN)

# File log (survives any crash)
import tempfile as _tempfile
import logging as _logging
_log_path = _tempfile.gettempdir() + "\\bridge_gui.log"
_logging.basicConfig(
    level=_logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[_logging.FileHandler(_log_path, encoding="utf-8")],
)
_flog = _logging.getLogger("bridge_gui")
_flog.info("bridge_gui.py started")

WORKER = Path(__file__).parent / "bridge_worker.py"


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App:
    COLORS = {
        "ok":           "#2ecc71",
        "waiting":      "#f39c12",
        "error":        "#e74c3c",
        "disconnected": "#95a5a6",
        "streaming":    "#2ecc71",
        "stopped":      "#95a5a6",
        "unknown":      "#95a5a6",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("SOMA Bridge")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        # Keep the bridge window readable, but make it a poor target for
        # keyboard/gamepad focus navigation. Windows 11 can route controller
        # input into focused app widgets, which risks accidental Start/Stop
        # clicks while teleoping.
        for seq in ("<Tab>", "<ISO_Left_Tab>", "<Return>", "<space>",
                    "<Left>", "<Right>", "<Up>", "<Down>"):
            root.bind_all(seq, lambda _e: "break", add="+")

        mono = tkfont.Font(family="Consolas", size=9)
        bold = tkfont.Font(family="Consolas", size=9, weight="bold")

        # ── Status row ──
        frm_status = tk.Frame(root, padx=6, pady=4)
        frm_status.pack(fill=tk.X)

        tk.Label(frm_status, text="Bridge:", font=bold).grid(row=0, column=0, sticky="w")
        self._bridge_lbl = tk.Label(frm_status, text="●  stopped", font=mono, width=20, anchor="w")
        self._bridge_lbl.grid(row=0, column=1, sticky="w")

        tk.Label(frm_status, text="WSL2:", font=bold).grid(row=1, column=0, sticky="w")
        self._client_lbl = tk.Label(frm_status, text="●  disconnected", font=mono, width=20, anchor="w")
        self._client_lbl.grid(row=1, column=1, sticky="w")

        tk.Label(frm_status, text="Ctrl:", font=bold).grid(row=2, column=0, sticky="w")
        self._ctrl_lbl = tk.Label(frm_status, text="●  unknown", font=mono, width=20, anchor="w")
        self._ctrl_lbl.grid(row=2, column=1, sticky="w")

        # ── Axes row ──
        frm_axes = tk.Frame(root, padx=6)
        frm_axes.pack(fill=tk.X)
        tk.Label(frm_axes, text="Axes:", font=bold).pack(side=tk.LEFT)
        self._axes_lbl = tk.Label(frm_axes, text="L(+0.00,+0.00) R(+0.00,+0.00)", font=mono)
        self._axes_lbl.pack(side=tk.LEFT)

        # ── Log ──
        self._log = scrolledtext.ScrolledText(
            root, height=8, width=52, font=mono,
            state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4", takefocus=0,
        )
        self._log.pack(padx=6, pady=(4, 2))

        # ── Buttons ──
        frm_btn = tk.Frame(root, padx=6, pady=4)
        frm_btn.pack(fill=tk.X)
        self._start_btn = tk.Button(
            frm_btn, text="Start", width=10, command=self._start, takefocus=0
        )
        self._start_btn.pack(side=tk.LEFT, padx=2)
        self._stop_btn = tk.Button(
            frm_btn, text="Stop", width=10, command=self._stop,
            state=tk.DISABLED, takefocus=0
        )
        self._stop_btn.pack(side=tk.LEFT, padx=2)
        self._auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frm_btn, text="Auto-restart", variable=self._auto_var, takefocus=0
        ).pack(side=tk.LEFT)

        # Internal state
        self._q: queue.Queue = queue.Queue()
        self._proc: subprocess.Popen | None = None
        self._running = False       # user intent: should worker be running?
        self._crashes = 0
        self._state: dict = {
            "bridge": "stopped", "client": "disconnected",
            "ctrl": "unknown", "axes": [0.0] * 6,
        }

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

        # Auto-start
        self._start()

    # ── Worker control ──────────────────────────────────────────────────────

    def _start(self) -> None:
        """Launch bridge_worker.py as a subprocess."""
        if self._proc and self._proc.poll() is None:
            return  # already alive
        self._running = True
        try:
            self._proc = subprocess.Popen(
                [sys.executable, str(WORKER)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr into stdout so we see all output
                text=True,
                bufsize=1,
            )
        except Exception as e:
            self._append_log(f"ERROR launching worker: {e}")
            _flog.error(f"ERROR launching worker: {e}")
            return
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        _flog.info(f"Worker started (pid={self._proc.pid})")
        t = threading.Thread(target=self._reader_thread, daemon=True)
        t.start()

    def _stop(self) -> None:
        """User-requested stop: kill worker and don't auto-restart."""
        self._running = False
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._state["bridge"] = "stopped"
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()

    # ── Background reader thread ─────────────────────────────────────────────

    def _reader_thread(self) -> None:
        """Read stdout of worker, parse JSON, push to queue.
        Runs until the worker process exits (stdout closes)."""
        assert self._proc is not None
        for raw_line in self._proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                obj = {"type": "log", "msg": line}
            self._q.put(obj)
        rc = self._proc.wait()
        self._q.put({"type": "exited", "rc": rc})

    # ── Periodic UI update ──────────────────────────────────────────────────

    def _poll(self) -> None:
        # Drain message queue from reader thread
        try:
            while True:
                obj = self._q.get_nowait()
                t = obj.get("type")

                if t == "log":
                    msg = obj.get("msg", "")
                    self._append_log(msg)
                    _flog.info(msg)

                elif t == "status":
                    for k in ("bridge", "client", "ctrl"):
                        if k in obj:
                            self._state[k] = obj[k]
                    if "axes" in obj:
                        self._state["axes"] = obj["axes"]

                elif t == "exited":
                    rc = obj.get("rc", -1)
                    crash_msg = f"Worker exited (rc={rc})"
                    self._append_log(crash_msg)
                    _flog.error(crash_msg)
                    self._state["bridge"] = "stopped"
                    self._state["client"] = "disconnected"
                    if self._running and self._auto_var.get():
                        self._crashes += 1
                        restart_msg = f"CRASH #{self._crashes} — auto-restarting in 3 s..."
                        self._append_log(restart_msg)
                        _flog.error(restart_msg)
                        self.root.after(3000, self._start)
                    else:
                        self._start_btn.config(state=tk.NORMAL)
                        self._stop_btn.config(state=tk.DISABLED)

        except queue.Empty:
            pass

        # Update labels
        self._set_label(self._bridge_lbl, self._state["bridge"], self._state["bridge"])
        self._set_label(self._client_lbl, self._state["client"], self._state["client"])
        self._set_label(self._ctrl_lbl,   self._state["ctrl"],   self._state["ctrl"])

        axes = self._state["axes"]
        if axes:
            lx, ly, _, rx, ry, _ = (list(axes) + [0] * 6)[:6]
            self._axes_lbl.config(
                text=f"L({lx:+.2f},{ly:+.2f}) R({rx:+.2f},{ry:+.2f})"
            )

        self.root.after(200, self._poll)

    def _set_label(self, lbl: tk.Label, text: str, state: str) -> None:
        color = self.COLORS.get(state, "#ffffff")
        lbl.config(text=f"●  {text}", fg=color)

    def _append_log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._log.config(state=tk.NORMAL)
        self._log.insert(tk.END, f"{ts}  {msg}\n")
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)


# ---------------------------------------------------------------------------

def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
