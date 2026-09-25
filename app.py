#!/usr/bin/env python3
"""
app.py — Interfaccia grafica Devotion Bot (Throne and Liberty)

La tua voce passa in continuo dal mic reale → CABLE Input.
Quando la skill cambia stato, l'alert si mixa sopra alla tua voce.
Discord usa "CABLE Output" come microfono e sente tutto.
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import json
import sys
import queue
from pathlib import Path
from datetime import datetime

try:
    import sounddevice as sd
    _all_devs    = sd.query_devices()
    _input_devs  = ["(predefinito)"] + [d["name"] for d in _all_devs if d["max_input_channels"]  > 0]
    _output_devs = ["(predefinito)"] + [d["name"] for d in _all_devs if d["max_output_channels"] > 0]
except Exception:
    _input_devs  = ["(predefinito)"]
    _output_devs = ["(predefinito)", "CABLE Input"]

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
PYTHON      = sys.executable

# ─── TEMA ────────────────────────────────────────────────────────────────────
BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"
BORDER = "#30363d"
ACCENT = "#58a6ff"
GREEN  = "#3fb950"
RED    = "#f85149"
YELLOW = "#e3b341"
TEXT   = "#c9d1d9"
TEXT2  = "#8b949e"
FONT   = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_T = ("Segoe UI", 12, "bold")
FONT_M = ("Consolas", 9)

DEFAULT_CONFIG = {
    "mic_device":          "",
    "output_device":       "CABLE Input",
    "detection_mode":      "visual",
    "keyboard_key":        "t",
    "reset_key":           "",
    "beep_enabled":        True,
    "beep_duration":       100,
    "skill_region_left":   1820,
    "skill_region_top":    1000,
    "skill_region_width":   72,
    "skill_region_height":  72,
    "on_threshold":         0.65,
    "confirm_frames":       2,
    "devotion_duration":    20.0,
    "warning_before":        5.0,
    "cooldown_min":         17.0,
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── APP ─────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Devotion Bot — Throne and Liberty")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(820, 560)

        self.cfg    = load_config()
        self.log_q: queue.Queue = queue.Queue()
        self.process: subprocess.Popen | None = None

        self._build_ui()
        self._poll_log()

        self.update_idletasks()
        w, h = 920, 650
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._log("Configura i dispositivi audio, salva e clicca Avvia.", "info")

    # ── BUILD UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG, padx=20, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="DEVOTION BOT", font=("Segoe UI", 17, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(hdr, text="  Throne and Liberty", font=FONT,
                 bg=BG, fg=TEXT2).pack(side="left", anchor="s", pady=(0, 2))
        tk.Label(hdr, text="⚡ POWERED BY PAOLOBROSIO", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg="#FFD700").pack(side="right", anchor="s", pady=(0, 3))
        tk.Frame(self, height=1, bg=BORDER).pack(fill="x")

        # Body
        body = tk.Frame(self, bg=BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG, width=360)
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_log(right)

    def _build_left(self, parent):
        # ── Bottone Salva fisso in fondo (fuori dallo scroll) ─────────────────
        tk.Button(
            parent, text="Salva configurazione", font=FONT_B,
            bg=ACCENT, fg="#0d1117", relief="flat", padx=12, pady=8,
            cursor="hand2", command=self._save,
        ).pack(side="bottom", fill="x", pady=(6, 0))

        # ── Scrollable canvas ──────────────────────────────────────────────────
        scrollbar = tk.Scrollbar(parent, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0,
                           yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=canvas.yview)

        inner = tk.Frame(canvas, bg=BG)
        _win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_resize)

        def _on_canvas_resize(e):
            canvas.itemconfig(_win, width=e.width)
        canvas.bind("<Configure>", _on_canvas_resize)

        def _on_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>",  lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>",  lambda e: canvas.unbind_all("<MouseWheel>"))

        # Da qui tutto il contenuto va in `inner` invece di `parent`
        parent = inner

        # ── Status pannello ───────────────────────────────────────────────────
        self._section(parent, "MONITOR")

        # ── Modalità rilevamento ──────────────────────────────────────────────
        self._mode    = self.cfg.get("detection_mode", "visual")
        self._kb_key  = self.cfg.get("keyboard_key", "t")
        self._kb_only = tk.BooleanVar(value=(self._mode == "keyboard"))

        mode_box = tk.Frame(parent, bg=BG3, padx=12, pady=10)
        mode_box.pack(fill="x", pady=(0, 8))

        cb = tk.Checkbutton(
            mode_box,
            text=f"Usa solo tasto  [{self._kb_key.upper()}]  — disattiva analisi schermo",
            variable=self._kb_only,
            font=FONT_B,
            bg=BG3, fg=TEXT,
            activebackground=BG3, activeforeground=TEXT,
            selectcolor=BG2,
            relief="flat", bd=0,
            cursor="hand2",
            command=self._on_mode_change,
        )
        cb.pack(anchor="w")

        self._mode_hint = tk.Label(
            mode_box,
            text=self._mode_hint_text(),
            font=("Segoe UI", 9),
            bg=BG3, fg=TEXT2,
            justify="left",
        )
        self._mode_hint.pack(anchor="w", pady=(4, 0))

        status_box = tk.Frame(parent, bg=BG2)
        status_box.pack(fill="x", pady=(0, 10))
        tk.Frame(status_box, height=2, bg=GREEN).pack(fill="x")
        inner = tk.Frame(status_box, bg=BG2, padx=14, pady=12)
        inner.pack(fill="x")

        hdr2 = tk.Frame(inner, bg=BG2)
        hdr2.pack(fill="x")
        tk.Label(hdr2, text="Passthrough Mic + Alert", font=FONT_T, bg=BG2, fg=TEXT).pack(side="left")
        self.dot = tk.Label(hdr2, text=" \u25cf", font=("Segoe UI", 14), bg=BG2, fg=RED)
        self.dot.pack(side="left", padx=(8, 0))
        self.status_lbl = tk.Label(hdr2, text="Inattivo", font=FONT, bg=BG2, fg=TEXT2)
        self.status_lbl.pack(side="left", padx=(2, 0))

        btns = tk.Frame(inner, bg=BG2)
        btns.pack(fill="x", pady=(10, 0))
        self.btn_start = tk.Button(
            btns, text="  Avvia", font=FONT_B,
            bg=GREEN, fg="#0d1117", relief="flat", padx=18, pady=8,
            cursor="hand2", command=self._start,
        )
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_stop = tk.Button(
            btns, text="  Ferma", font=FONT_B,
            bg=BG3, fg=TEXT2, relief="flat", padx=18, pady=8,
            cursor="hand2", command=self._stop, state="disabled",
        )
        self.btn_stop.pack(side="left")
        self.btn_reset = tk.Button(
            btns, text="⟳  Reset", font=FONT_B,
            bg=BG3, fg=TEXT2, relief="flat", padx=18, pady=8,
            cursor="hand2", command=self._reset_monitor, state="disabled",
        )
        self.btn_reset.pack(side="left", padx=(8, 0))

        # Stato skill rilevato
        skill_box = tk.Frame(inner, bg=BG3, padx=10, pady=8)
        skill_box.pack(fill="x", pady=(12, 0))
        tk.Label(skill_box, text="Skill rilevata:", font=FONT,
                 bg=BG3, fg=TEXT2).pack(side="left")
        self.skill_dot = tk.Label(skill_box, text=" \u25cf", font=("Segoe UI", 13),
                                  bg=BG3, fg=TEXT2)
        self.skill_dot.pack(side="left")
        self.skill_lbl = tk.Label(skill_box, text="—", font=FONT_B,
                                  bg=BG3, fg=TEXT2)
        self.skill_lbl.pack(side="left", padx=(2, 0))

        # Calibra
        tk.Button(
            parent, text="Diagnosi live (cosa vede il bot)", font=FONT,
            bg="#b45309", fg="white", relief="flat", padx=10, pady=6,
            cursor="hand2", command=self._diagnosi,
        ).pack(fill="x", pady=(0, 4))
        tk.Button(
            parent, text="Estrai template inutilizzabile", font=FONT,
            bg="#7f1d1d", fg="white", relief="flat", padx=10, pady=6,
            cursor="hand2", command=self._estrai_inutilizzabile,
        ).pack(fill="x", pady=(0, 4))
        tk.Button(
            parent, text="Calibra da immagini di calibrazione", font=FONT,
            bg="#7c3aed", fg="white", relief="flat", padx=10, pady=6,
            cursor="hand2", command=self._calibra_da_calibrazione,
        ).pack(fill="x", pady=(0, 4))
        tk.Button(
            parent, text="Calibra automatico da screenshot", font=FONT,
            bg=ACCENT, fg="#0d1117", relief="flat", padx=10, pady=6,
            cursor="hand2", command=self._calibrate_auto,
        ).pack(fill="x", pady=(0, 4))
        tk.Button(
            parent, text="Cattura rapida template  (1/2/3)", font=FONT,
            bg=YELLOW, fg="#0d1117", relief="flat", padx=10, pady=6,
            cursor="hand2", command=self._cattura_rapida,
        ).pack(fill="x", pady=(0, 4))
        tk.Button(
            parent, text="Ricalibra template guidato (3 passi)", font=FONT,
            bg=BG3, fg=TEXT2, relief="flat", padx=10, pady=6,
            cursor="hand2", command=self._ricalibra_template,
        ).pack(fill="x", pady=(0, 4))
        tk.Button(
            parent, text="Calibra regione schermo (manuale)", font=FONT,
            bg=BG3, fg=TEXT2, relief="flat", padx=10, pady=6,
            cursor="hand2", command=self._calibrate,
        ).pack(fill="x", pady=(0, 2))

        # ── Separatore ────────────────────────────────────────────────────────
        tk.Frame(parent, height=1, bg=BORDER).pack(fill="x", pady=14)

        # ── Configurazione ────────────────────────────────────────────────────
        self._section(parent, "CONFIGURAZIONE")

        box = tk.Frame(parent, bg=BG2, padx=14, pady=12)
        box.pack(fill="x")
        tk.Frame(box, height=2, bg=YELLOW).pack(fill="x", pady=(0, 10))

        self.vars: dict[str, tk.Variable] = {}

        # Device dropdowns
        self._dropdown(box, "Microfono", "mic_device", _input_devs)
        self._dropdown(box, "Uscita (CABLE)", "output_device", _output_devs)
        self._entry(box, "Tasto skill (keyboard)", "keyboard_key")
        self._entry(box, "Tasto reset (hotkey)", "reset_key")

        tk.Frame(box, height=1, bg=BORDER).pack(fill="x", pady=(8, 6))

        beep_row = tk.Frame(box, bg=BG2)
        beep_row.pack(fill="x", pady=3)
        self._beep_var = tk.BooleanVar(value=bool(self.cfg.get("beep_enabled", True)))
        tk.Checkbutton(
            beep_row,
            text="Beep locale di conferma alle cuffie",
            variable=self._beep_var,
            font=FONT_B, bg=BG2, fg=TEXT,
            activebackground=BG2, activeforeground=TEXT,
            selectcolor=BG3, relief="flat", bd=0, cursor="hand2",
        ).pack(anchor="w")
        tk.Label(beep_row,
                 text="  ON=880Hz  •  warning=660Hz  •  OFF=440Hz",
                 font=("Segoe UI", 8), bg=BG2, fg=TEXT2).pack(anchor="w", pady=(2, 0))
        self.vars["beep_enabled"] = self._beep_var
        self._entry(box, "Durata beep (ms)", "beep_duration")

        tk.Frame(box, height=1, bg=BORDER).pack(fill="x", pady=(8, 6))

        # Skill region & thresholds
        self._entry(box, "Region — Left",    "skill_region_left")
        self._entry(box, "Region — Top",     "skill_region_top")
        self._entry(box, "Region — Width",   "skill_region_width")
        self._entry(box, "Region — Height",  "skill_region_height")
        self._entry(box, "ON Threshold",     "on_threshold")
        self._entry(box, "Conferma frame",   "confirm_frames")

        tk.Frame(box, height=1, bg=BORDER).pack(fill="x", pady=(8, 6))

        timer_hdr = tk.Frame(box, bg=BG2)
        timer_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(timer_hdr, text="Timer (secondi)", font=("Segoe UI", 8, "bold"),
                 bg=BG2, fg=TEXT2).pack(side="left")
        tk.Label(timer_hdr, text="  modificabili → Salva → riavvia monitor",
                 font=("Segoe UI", 8), bg=BG2, fg=TEXT2).pack(side="left")

        self._entry(box, "Durata Devotion",  "devotion_duration")
        self._entry(box, "Avviso anticipo",  "warning_before")
        self._entry(box, "Cooldown minimo",  "cooldown_min")

        # ── Nudge panel ───────────────────────────────────────────────────────
        tk.Frame(box, height=1, bg=BORDER).pack(fill="x", pady=(10, 8))
        tk.Label(box, text="Sposta cattura", font=("Segoe UI", 8, "bold"),
                 bg=BG2, fg=TEXT2).pack(anchor="w", pady=(0, 6))

        nudge_outer = tk.Frame(box, bg=BG2)
        nudge_outer.pack(fill="x")

        # Step selector
        step_row = tk.Frame(nudge_outer, bg=BG2)
        step_row.pack(fill="x", pady=(0, 6))
        tk.Label(step_row, text="Step (px):", font=FONT, bg=BG2, fg=TEXT2).pack(side="left")
        self._nudge_step = tk.IntVar(value=5)
        for v in (1, 5, 10, 20):
            tk.Radiobutton(
                step_row, text=str(v), variable=self._nudge_step, value=v,
                font=FONT, bg=BG2, fg=TEXT, selectcolor=BG3,
                activebackground=BG2, activeforeground=TEXT,
                relief="flat", bd=0,
            ).pack(side="left", padx=(6, 0))

        # Frecce direzionali (posizione)
        arrow_frame = tk.Frame(nudge_outer, bg=BG2)
        arrow_frame.pack()

        btn_kw = dict(font=("Segoe UI", 12, "bold"), bg=BG3, fg=TEXT,
                      relief="flat", width=3, pady=4, cursor="hand2")

        tk.Button(arrow_frame, text="↑", **btn_kw,
                  command=lambda: self._nudge("skill_region_top", -1)).grid(row=0, column=1, padx=2, pady=2)
        tk.Button(arrow_frame, text="←", **btn_kw,
                  command=lambda: self._nudge("skill_region_left", -1)).grid(row=1, column=0, padx=2, pady=2)
        tk.Label(arrow_frame, text="pos", font=("Segoe UI", 8), bg=BG2, fg=TEXT2,
                 width=3).grid(row=1, column=1)
        tk.Button(arrow_frame, text="→", **btn_kw,
                  command=lambda: self._nudge("skill_region_left", +1)).grid(row=1, column=2, padx=2, pady=2)
        tk.Button(arrow_frame, text="↓", **btn_kw,
                  command=lambda: self._nudge("skill_region_top", +1)).grid(row=2, column=1, padx=2, pady=2)

        # Ridimensiona larghezza/altezza
        size_frame = tk.Frame(nudge_outer, bg=BG2)
        size_frame.pack(pady=(8, 0))

        for label, key, col in (("W", "skill_region_width", 0), ("H", "skill_region_height", 3)):
            tk.Label(size_frame, text=label, font=FONT_B, bg=BG2, fg=TEXT2).grid(
                row=0, column=col, padx=(8 if col else 0, 2))
            tk.Button(size_frame, text="−", **btn_kw,
                      command=lambda k=key: self._nudge(k, -1)).grid(row=0, column=col+1, padx=2)
            tk.Button(size_frame, text="+", **btn_kw,
                      command=lambda k=key: self._nudge(k, +1)).grid(row=0, column=col+2, padx=2)

    def _section(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI", 8, "bold"),
                 bg=BG, fg=TEXT2).pack(anchor="w", pady=(0, 8))

    def _dropdown(self, parent, label: str, key: str, options: list):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=FONT, bg=BG2, fg=TEXT2,
                 width=20, anchor="w").pack(side="left")

        current_val = str(self.cfg.get(key, ""))
        # Mappa: valore "" → "(predefinito)"
        display = current_val if current_val and current_val in options else "(predefinito)"
        var = tk.StringVar(value=display)
        self.vars[key] = var

        menu = tk.OptionMenu(row, var, *options)
        menu.config(font=FONT_M, bg=BG3, fg=TEXT, activebackground=ACCENT,
                    activeforeground="#0d1117", relief="flat", bd=0,
                    highlightthickness=0, padx=4)
        menu["menu"].config(font=FONT_M, bg=BG3, fg=TEXT,
                            activebackground=ACCENT, activeforeground="#0d1117")
        menu.pack(side="left", fill="x", expand=True)

    def _entry(self, parent, label: str, key: str):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=FONT, bg=BG2, fg=TEXT2,
                 width=20, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get(key, "")))
        tk.Entry(row, textvariable=var, font=FONT_M, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief="flat", bd=4).pack(
            side="left", fill="x", expand=True)
        self.vars[key] = var

    def _build_log(self, parent):
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="LOG", font=("Segoe UI", 8, "bold"),
                 bg=BG, fg=TEXT2).pack(side="left")
        tk.Button(hdr, text="Pulisci", font=("Segoe UI", 8),
                  bg=BG3, fg=TEXT2, relief="flat", padx=8, pady=2,
                  cursor="hand2", command=self._clear_log).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(
            parent, font=FONT_M, bg=BG2, fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, wrap="word", state="disabled",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("time",    foreground=TEXT2)
        self.log_box.tag_config("info",    foreground=TEXT)
        self.log_box.tag_config("success", foreground=GREEN)
        self.log_box.tag_config("warning", foreground=YELLOW)
        self.log_box.tag_config("error",   foreground=RED)

        # Istruzioni fisse in basso
        info = tk.Frame(parent, bg=BG3, padx=12, pady=8)
        info.pack(fill="x", pady=(8, 0))
        istr = (
            "Discord: Impostazioni → Voce → Microfono → CABLE Output\n"
            "Parli normalmente, gli alert si mixano alla tua voce automaticamente."
        )
        tk.Label(info, text=istr, font=("Segoe UI", 9), bg=BG3, fg=TEXT2,
                 justify="left", anchor="w").pack(fill="x")

    # ── AZIONI ────────────────────────────────────────────────────────────────
    def _start(self):
        if self.process and self.process.poll() is None:
            return
        try:
            self.process = subprocess.Popen(
                [PYTHON, str(BASE_DIR / "monitor.py")],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                cwd=str(BASE_DIR),
                encoding="utf-8", errors="replace",
            )
        except Exception as e:
            self._log(f"Impossibile avviare monitor.py: {e}", "error")
            return
        self._set_running(True)
        threading.Thread(target=self._read_output, daemon=True).start()

    def _stop(self):
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
        self._set_running(False)

    def _read_output(self):
        try:
            for line in self.process.stdout:
                self.log_q.put(("log", line.rstrip()))
        except Exception:
            pass
        finally:
            if self.process:
                self.process.wait()
            self.log_q.put(("stopped", None))

    def _set_running(self, running: bool):
        if running:
            self.dot.config(fg=GREEN)
            self.status_lbl.config(text="In esecuzione", fg=GREEN)
            self.btn_start.config(state="disabled", bg=BG3, fg=TEXT2)
            self.btn_stop.config(state="normal", bg=RED, fg="white")
            self.btn_reset.config(state="normal", bg=YELLOW, fg="#0d1117")
        else:
            self.dot.config(fg=RED)
            self.status_lbl.config(text="Inattivo", fg=TEXT2)
            self.btn_start.config(state="normal", bg=GREEN, fg="#0d1117")
            self.btn_stop.config(state="disabled", bg=BG3, fg=TEXT2)
            self.btn_reset.config(state="disabled", bg=BG3, fg=TEXT2)

    def _reset_monitor(self):
        """Crea il file-flag reset.flag → monitor.py torna immediatamente in WATCHING."""
        flag = BASE_DIR / "reset.flag"
        try:
            flag.write_text("reset", encoding="utf-8")
            self._log("Reset inviato — monitor torna in ascolto (WATCHING).", "warning")
        except Exception as e:
            self._log(f"Errore reset: {e}", "error")

    def _nudge(self, key: str, direction: int):
        """Sposta/ridimensiona la regione di `step` pixel e salva subito."""
        step = self._nudge_step.get() * direction
        try:
            current = int(self.vars[key].get())
        except ValueError:
            return
        new_val = max(0, current + step)
        self.vars[key].set(str(new_val))
        self.cfg[key] = new_val
        save_config(self.cfg)
        self._log(f"Regione aggiornata: {key} = {new_val}  (step {step:+d})", "info")

    def _save(self):
        INT_KEYS   = ("skill_region_left", "skill_region_top",
                      "skill_region_width", "skill_region_height",
                      "confirm_frames", "beep_duration")
        FLOAT_KEYS = ("on_threshold", "devotion_duration",
                      "warning_before", "cooldown_min")

        for key, var in self.vars.items():
            raw = var.get()
            # BooleanVar → salva direttamente come bool
            if isinstance(raw, bool):
                self.cfg[key] = raw
                continue
            val = str(raw).strip()
            if key in INT_KEYS:
                try:
                    self.cfg[key] = int(val)
                except ValueError:
                    messagebox.showerror("Errore", f"'{key}' deve essere un numero intero.")
                    return
            elif key in FLOAT_KEYS:
                try:
                    self.cfg[key] = float(val)
                except ValueError:
                    messagebox.showerror("Errore", f"'{key}' deve essere un numero decimale.")
                    return
            else:
                # Dispositivo: "(predefinito)" → ""
                self.cfg[key] = "" if val == "(predefinito)" else val

        save_config(self.cfg)
        self._log("Configurazione salvata in config.json", "success")

    def _cattura_rapida(self):
        try:
            subprocess.Popen(
                [PYTHON, str(BASE_DIR / "cattura_rapida.py")],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("cattura_rapida.py aperto — usa 1/2/3 per salvare i template.", "info")
        except Exception as e:
            self._log(f"Errore: {e}", "error")

    def _ricalibra_template(self):
        try:
            subprocess.Popen(
                [PYTHON, str(BASE_DIR / "ricalibra_template.py")],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("ricalibra_template.py avviato — segui i 3 passi nella finestra.", "warning")
        except Exception as e:
            self._log(f"Errore: {e}", "error")

    # ── MODALITÀ RILEVAMENTO ──────────────────────────────────────────────────
    def _mode_hint_text(self) -> str:
        if self._kb_only.get():
            return (f"Premi [{self._kb_key.upper()}] in gioco per attivare il buff.\n"
                    "Nessuna analisi schermo — zero falsi positivi.")
        return ("Il bot analizza lo schermo e rileva il bordo rosa dell'icona.\n"
                "Alternativa: spunta la casella sopra per usare solo il tasto.")

    def _on_mode_change(self):
        self._mode = "keyboard" if self._kb_only.get() else "visual"
        self._mode_hint.config(text=self._mode_hint_text())
        self.cfg["detection_mode"] = self._mode
        save_config(self.cfg)
        if self._mode == "keyboard":
            self._log(f"Modalita' TASTIERA attivata — tasto [{self._kb_key.upper()}]  "
                      "(riavvia il monitor)", "warning")
        else:
            self._log("Modalita' VISUALE attivata  (riavvia il monitor)", "warning")

    def _estrai_inutilizzabile(self):
        try:
            subprocess.Popen(
                [PYTHON, str(BASE_DIR / "estrai_inutilizzabile.py")],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("estrai_inutilizzabile.py avviato.", "info")
        except Exception as e:
            self._log(f"Errore: {e}", "error")

    def _diagnosi(self):
        try:
            subprocess.Popen(
                [PYTHON, str(BASE_DIR / "diagnosi.py")],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("diagnosi.py avviato — osserva i valori mentre usi la skill.", "info")
        except Exception as e:
            self._log(f"Errore: {e}", "error")

    def _calibra_da_calibrazione(self):
        try:
            subprocess.Popen(
                [PYTHON, str(BASE_DIR / "calibra_da_calibrazione.py")],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("calibra_da_calibrazione.py avviato — segui le istruzioni nella finestra.", "info")
        except Exception as e:
            self._log(f"Errore: {e}", "error")

    def _calibrate_auto(self):
        try:
            subprocess.Popen(
                [PYTHON, str(BASE_DIR / "calibra_auto.py")],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("calibra_auto.py avviato — segui le istruzioni nella finestra.", "info")
        except Exception as e:
            self._log(f"Errore: {e}", "error")

    def _calibrate(self):
        try:
            subprocess.Popen(
                [PYTHON, str(BASE_DIR / "calibrate.py")],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("calibrate.py avviato — segui le istruzioni nella finestra nera.", "info")
        except Exception as e:
            self._log(f"Errore avvio calibrate.py: {e}", "error")

    _SKILL_COLORS = {
        "on":       ("#3fb950", "ATTIVA"),
        "off_in_5": ("#e3b341", "5 SEC"),
        "cooldown": ("#f85149", "COOLDOWN"),
        "unknown":  ("#8b949e", "—"),
    }

    def _update_skill_state(self, line: str):
        """Aggiorna l'indicatore skill parsando le righe di log."""
        lo = line.lower()
        # Riga periodica: "SKILL: ON | ..."
        if "skill:" in lo:
            for key, (color, label) in self._SKILL_COLORS.items():
                if f" {key} " in lo or lo.endswith(key) or f"skill: {key}" in lo:
                    self.skill_dot.config(fg=color)
                    self.skill_lbl.config(text=label, fg=color)
                    break
        # Transizione di stato: "Stato: [on] → [cooldown]"
        elif "stato:" in lo and "→" in line:
            for key, (color, label) in self._SKILL_COLORS.items():
                if f"[{key}]" in lo.split("→")[-1]:
                    self.skill_dot.config(fg=color)
                    self.skill_lbl.config(text=label, fg=color)
                    break
        # Audio trigger
        elif "audio trigger" in lo:
            if "on.wav" in lo:
                self.skill_dot.config(fg="#3fb950"); self.skill_lbl.config(text="ATTIVA  ♪", fg="#3fb950")
            elif "in 5" in lo:
                self.skill_dot.config(fg="#e3b341"); self.skill_lbl.config(text="5 SEC  ♪", fg="#e3b341")
            elif "off.wav" in lo:
                self.skill_dot.config(fg="#f85149"); self.skill_lbl.config(text="COOLDOWN  ♪", fg="#f85149")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    # ── LOG ───────────────────────────────────────────────────────────────────
    def _log(self, text: str, tag: str = "info"):
        self.log_box.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}]  ", "time")
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _poll_log(self):
        try:
            while True:
                kind, data = self.log_q.get_nowait()
                if kind == "stopped":
                    self._log("Monitor fermato.", "warning")
                    self._set_running(False)
                else:
                    lo = data.lower()
                    if any(w in lo for w in ["error", "errore", "exception", "traceback"]):
                        tag = "error"
                    elif any(w in lo for w in ["warning", "warn", "non trovato"]):
                        tag = "warning"
                    elif any(w in lo for w in ["attivo", "avviato", "caricato",
                                               "audio trigger", "monitoraggio"]):
                        tag = "success"
                    else:
                        tag = "info"
                    self._log(data, tag)
                    self._update_skill_state(data)
        except Exception:
            pass
        finally:
            self.after(100, self._poll_log)


if __name__ == "__main__":
    App().mainloop()
