#!/usr/bin/env python3
"""
monitor.py — Devotion Bot con rilevamento attivazione + timer

Modalità di rilevamento (config.json → "detection_mode"):
  "visual"   — analisi visuale dello schermo (HSV bordo rosa + template matching)
  "keyboard" — pressione del tasto configurato (config.json → "keyboard_key", default "t")

Dopo l'attivazione (indipendentemente dal metodo), un timer gestisce tutto il resto:
  T+0s            → suono "devotion on"
  T+(durata-5)s   → suono "devotion off in 5"
  T+durata s      → suono "devotion off"
  T+(durata+cd)s  → torna in ascolto

Passthrough microfono → CABLE Input in continuo.
"""

import asyncio
import time
import cv2
import numpy as np
import mss
import sounddevice as sd
import soundfile as sf
import threading
import queue
from pathlib import Path
import logging

# ════════════════════════════════════════════════════════════════
#  CONFIGURAZIONE  (sovrascrivibile da config.json)
# ════════════════════════════════════════════════════════════════

MIC_DEVICE    = None
OUTPUT_DEVICE = "CABLE Input"

# ── Modalità rilevamento ──────────────────────────────────────────────────────
# "visual"   = analisi schermo (HSV + template)
# "keyboard" = pressione tasto
DETECTION_MODE = "visual"
KEYBOARD_KEY   = "t"

SKILL_REGION = {"left": 1820, "top": 1000, "width": 72, "height": 72}

# ── Rilevamento bordo rosa/magenta (metodo primario) ─────────────────────────
# Il bordo rosa appare SOLO quando la skill è attiva (buff in corso).
# In cooldown e in stato pronto non c'è bordo rosa → rilevamento molto affidabile.
PINK_PIXEL_THRESHOLD = 25    # pixel rosa minimi nel bordo per confermare attivazione
MIN_SIDES_WITH_PINK  = 2     # il bordo deve apparire su almeno 2 lati (evita animazioni parziali)

# ── Template matching (metodo secondario / backup) ────────────────────────────
ON_THRESHOLD              = 0.65   # soglia template matching
CONFIRM_FRAMES            = 2      # frame consecutivi per HSV; template usa +1 frame in più

# ── Rilevamento stato inutilizzabile (anti falsi positivi) ───────────────────
UNUSABLE_THRESHOLD        = 0.55   # soglia matching template inutilizzabile
UNUSABLE_LOCKOUT          = 2.5    # secondi di attesa dopo che la skill torna usabile

# ── Timer (secondi) ───────────────────────────────────────────────────────────
DEVOTION_DURATION = 20.0
WARNING_BEFORE    =  5.0
COOLDOWN_MIN      = 17.0
RESET_KEY         = ""    # tasto per tornare in ascolto (vuoto = disabilitato)

# ── Beep locale di conferma (sentito nelle cuffie, non su CABLE) ──────────────
BEEP_ENABLED  = True   # True = beep ogni volta che scatta un alert
BEEP_DURATION = 100    # millisecondi

# ════════════════════════════════════════════════════════════════

import json as _json, pathlib as _pl
_cfg_file = _pl.Path(__file__).parent / "config.json"
if _cfg_file.exists():
    try:
        _c = _json.loads(_cfg_file.read_text(encoding="utf-8"))
        MIC_DEVICE     = _c.get("mic_device",     MIC_DEVICE)    or None
        OUTPUT_DEVICE  = _c.get("output_device",  OUTPUT_DEVICE) or None
        DETECTION_MODE = _c.get("detection_mode", DETECTION_MODE)
        KEYBOARD_KEY   = _c.get("keyboard_key",   KEYBOARD_KEY)
        SKILL_REGION  = {
            "left":   _c.get("skill_region_left",   SKILL_REGION["left"]),
            "top":    _c.get("skill_region_top",    SKILL_REGION["top"]),
            "width":  _c.get("skill_region_width",  SKILL_REGION["width"]),
            "height": _c.get("skill_region_height", SKILL_REGION["height"]),
        }
        PINK_PIXEL_THRESHOLD = int(_c.get("pink_pixel_threshold",   PINK_PIXEL_THRESHOLD))
        MIN_SIDES_WITH_PINK  = int(_c.get("min_sides_with_pink",   MIN_SIDES_WITH_PINK))
        ON_THRESHOLD         = float(_c.get("on_threshold",         ON_THRESHOLD))
        CONFIRM_FRAMES       = int(_c.get("confirm_frames",         CONFIRM_FRAMES))
        UNUSABLE_THRESHOLD   = float(_c.get("unusable_threshold",   UNUSABLE_THRESHOLD))
        UNUSABLE_LOCKOUT     = float(_c.get("unusable_lockout",     UNUSABLE_LOCKOUT))
        DEVOTION_DURATION    = float(_c.get("devotion_duration",    DEVOTION_DURATION))
        WARNING_BEFORE       = float(_c.get("warning_before",       WARNING_BEFORE))
        COOLDOWN_MIN         = float(_c.get("cooldown_min",         COOLDOWN_MIN))
        RESET_KEY            = _c.get("reset_key",                  RESET_KEY)
        BEEP_ENABLED         = bool(_c.get("beep_enabled",          BEEP_ENABLED))
        BEEP_DURATION        = int(_c.get("beep_duration",          BEEP_DURATION))
    except Exception:
        pass

# ════════════════════════════════════════════════════════════════

BASE_DIR   = _pl.Path(__file__).parent
IMAGES_DIR = BASE_DIR / "immagini"
AUDIO_DIR  = BASE_DIR / "tracce audio"

# ─── KEYBOARD LISTENER ────────────────────────────────────────────────────────
_key_queue:   queue.Queue = queue.Queue(maxsize=8)
_reset_queue: queue.Queue = queue.Queue(maxsize=8)

# Path del file-flag creato dalla GUI per forzare il reset
_RESET_FLAG = _pl.Path(__file__).parent / "reset.flag"


def _start_key_listener(key: str,
                        target_queue: queue.Queue = None,
                        signal: str = "activate") -> object | None:
    """
    Avvia un listener globale per il tasto `key` in background.
    Ogni pressione mette `signal` in `target_queue` (default: _key_queue / "activate").
    Richiede: pip install pynput
    """
    if target_queue is None:
        target_queue = _key_queue
    try:
        from pynput import keyboard as _pynput_kb   # type: ignore

        target = key.lower()

        def _on_press(k):
            try:
                ch = getattr(k, 'char', None)
                if ch and ch.lower() == target:
                    try:
                        target_queue.put_nowait(signal)
                    except queue.Full:
                        pass
            except Exception:
                pass

        listener = _pynput_kb.Listener(on_press=_on_press)
        listener.daemon = True
        listener.start()
        return listener
    except ImportError:
        return None


def _flush_reset():
    """Svuota tutta la coda reset e cancella il file-flag senza triggerare nulla."""
    while not _reset_queue.empty():
        try:
            _reset_queue.get_nowait()
        except queue.Empty:
            break
    if _RESET_FLAG.exists():
        try:
            _RESET_FLAG.unlink()
        except Exception:
            pass

def _check_reset() -> bool:
    """
    Controlla se è arrivato almeno un segnale di reset (hotkey o file-flag dalla GUI).
    Drena TUTTA la coda e cancella il flag — click multipli = un solo reset.
    """
    triggered = False
    while not _reset_queue.empty():
        try:
            _reset_queue.get_nowait()
            triggered = True
        except queue.Empty:
            break
    if _RESET_FLAG.exists():
        try:
            _RESET_FLAG.unlink()
        except Exception:
            pass
        triggered = True
    return triggered

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("devotion")

S_WATCHING = "watching"
S_ACTIVE   = "active"
S_COOLDOWN = "cooldown"

AUDIO_ON   = "devotion on.wav"
AUDIO_WARN = "devotion off in 5.wav"
AUDIO_OFF  = "devotion off.wav"

# ─── DEVICE SETUP ─────────────────────────────────────────────────────────────
def _find_device(name, kind):
    if name is None:
        return None
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    for i, dev in enumerate(sd.query_devices()):
        if name.lower() in dev["name"].lower() and dev[key] > 0:
            return i
    log.warning("Dispositivo '%s' non trovato, uso predefinito.", name)
    return None

_mic_id    = _find_device(MIC_DEVICE,    "input")
_output_id = _find_device(OUTPUT_DEVICE, "output")

def _dev_info(device_id, kind):
    try:
        idx = device_id if device_id is not None else sd.default.device[0 if kind == "input" else 1]
        return sd.query_devices(idx)
    except Exception:
        return {}

_mic_info = _dev_info(_mic_id,    "input")
_out_info = _dev_info(_output_id, "output")

MIC_SR = int(_mic_info.get("default_samplerate", 48000))
OUT_SR = int(_out_info.get("default_samplerate", 44100))
CH_OUT = min(int(_out_info.get("max_output_channels", 2)), 2)

log.info("Microfono: %s (%d Hz)", _mic_info.get("name", "predefinito"), MIC_SR)
log.info("Uscita:    %s (%d Hz)", _out_info.get("name", "predefinito"), OUT_SR)

# ─── AUDIO CACHE ──────────────────────────────────────────────────────────────
def _resample(data, orig_sr, target_sr):
    mono = data.mean(axis=1) if data.ndim > 1 else data
    if orig_sr == target_sr:
        return mono.astype(np.float32)
    n = int(len(mono) * target_sr / orig_sr)
    return np.interp(np.linspace(0, len(mono)-1, n), np.arange(len(mono)), mono).astype(np.float32)

_audio_cache: dict[str, np.ndarray] = {}

def preload_audio():
    for fname in (AUDIO_ON, AUDIO_WARN, AUDIO_OFF):
        raw, sr = sf.read(str(AUDIO_DIR / fname), dtype="float32")
        mono = _resample(raw, sr, OUT_SR)
        _audio_cache[fname] = np.stack([mono] * CH_OUT, axis=1)
        log.info("Audio caricato: %s", fname)

_alert_data: np.ndarray | None = None
_alert_pos:  int               = 0
_alert_lock  = threading.Lock()

# Frequenze beep per evento (Hz): acuto=ON, medio=warning 5s, grave=OFF/cooldown
_BEEP_FREQS = {
    "devotion on.wav":        880,
    "devotion off in 5.wav":  660,
    "devotion off.wav":       440,
}

def _local_beep(freq: int, duration_ms: int):
    """Suona un beep diretto nelle cuffie tramite winsound (non va su CABLE)."""
    try:
        import winsound
        winsound.Beep(max(37, min(32767, freq)), max(1, duration_ms))
    except Exception:
        pass

def play_audio(fname: str):
    global _alert_data, _alert_pos
    data = _audio_cache.get(fname)
    if data is None:
        return
    log.info("===> AUDIO: %s", fname)
    with _alert_lock:
        _alert_data = data
        _alert_pos  = 0
    if BEEP_ENABLED:
        freq = _BEEP_FREQS.get(fname, 660)
        threading.Thread(target=_local_beep, args=(freq, BEEP_DURATION), daemon=True).start()

# ─── STREAM CALLBACKS ─────────────────────────────────────────────────────────
_pass_q:    queue.Queue = queue.Queue(maxsize=128)
_remainder: np.ndarray  = np.zeros(0, dtype=np.float32)

def _mic_cb(indata, frames, t, status):
    mono = indata[:, 0].copy() if indata.ndim > 1 else indata.flatten().copy()
    if MIC_SR != OUT_SR:
        n    = int(len(mono) * OUT_SR / MIC_SR)
        mono = np.interp(np.linspace(0, len(mono)-1, n), np.arange(len(mono)), mono).astype(np.float32)
    try:
        _pass_q.put_nowait(mono)
    except queue.Full:
        pass

def _out_cb(outdata, frames, t, status):
    global _remainder, _alert_data, _alert_pos
    buf = _remainder
    while len(buf) < frames:
        try:
            buf = np.concatenate([buf, _pass_q.get_nowait()])
        except queue.Empty:
            break
    n    = min(frames, len(buf))
    mono = np.zeros(frames, dtype=np.float32)
    if n > 0:
        mono[:n] = buf[:n]
    _remainder = buf[n:] if n < len(buf) else np.zeros(0, dtype=np.float32)
    outdata[:] = np.stack([mono] * CH_OUT, axis=1)
    with _alert_lock:
        if _alert_data is not None:
            rem = len(_alert_data) - _alert_pos
            if rem <= 0:
                _alert_data = None
                _alert_pos  = 0
            else:
                an = min(frames, rem)
                outdata[:an] += _alert_data[_alert_pos:_alert_pos + an]
                np.clip(outdata, -1.0, 1.0, out=outdata)
                _alert_pos += an

# ─── DETECTION: BORDO ROSA/MAGENTA ────────────────────────────────────────────
#
# La skill Devotion quando è ATTIVA mostra un bordo rosa/magenta brillante.
# In cooldown o pronta NON c'è bordo rosa.
# Rilevare il bordo rosa è molto più affidabile del template matching perché:
#   - non dipende dal timer che cambia ogni secondo
#   - non dipende dalla risoluzione o skin del gioco
#   - risponde nell'istante esatto in cui la skill si attiva
#
# Range HSV del bordo rosa in OpenCV (H: 0-180, S/V: 0-255):
#   H: 130-175  →  copre rosa/magenta/viola-rosa
#   S:  80-255  →  colore saturo
#   V: 100-255  →  colore brillante

_PINK_LOWER = np.array([130,  80, 100], dtype=np.uint8)
_PINK_UPPER = np.array([175, 255, 255], dtype=np.uint8)


def _check_pink_border(frame: np.ndarray) -> tuple[int, int]:
    """
    Analizza il bordo rosa/magenta su tutti e 4 i lati dell'icona.
    Restituisce (pixel_totali_rosa, numero_lati_con_rosa).

    Il bordo attivo è CONTINUO su tutti i lati → MIN_SIDES_WITH_PINK >= 2.
    Le animazioni di transizione di solito interessano solo 1 lato → falso positivo evitato.
    """
    hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _PINK_LOWER, _PINK_UPPER)

    H, W = frame.shape[:2]
    b = max(4, min(W, H) // 5)   # larghezza fascia di bordo

    # Soglia minima per contare un lato come "attivo"
    min_per_side = max(3, b * 2)

    strips = [
        mask[:b, :],    # top
        mask[-b:, :],   # bottom
        mask[:, :b],    # left
        mask[:, -b:],   # right
    ]

    total = 0
    sides = 0
    for strip in strips:
        c = int(np.count_nonzero(strip))
        total += c
        if c >= min_per_side:
            sides += 1

    return total, sides


# ─── DETECTION: TEMPLATE MATCHING (backup) ────────────────────────────────────
# ─── DETECTION: STATO INUTILIZZABILE ─────────────────────────────────────────
def _load_unusable_templates() -> list[np.ndarray]:
    """Carica template per lo stato 'skill inutilizzabile' da immagini/inutilizzabile/."""
    templates: list[np.ndarray] = []
    d = IMAGES_DIR / "inutilizzabile"
    if d.exists():
        for p in sorted(d.glob("*.png")):
            if p.name.startswith("_bak_"):
                continue
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                templates.append(img)
                log.info("Template INUTILIZZABILE caricato: %s", p.name)
    if not templates:
        log.info("Nessun template inutilizzabile — rilevamento stato disabilitato.")
    return templates

UNUSABLE_TEMPLATES: list[np.ndarray] = _load_unusable_templates()


def _score_unusable(frame: np.ndarray) -> float:
    """Score massimo di matching contro i template 'inutilizzabile'."""
    if not UNUSABLE_TEMPLATES:
        return 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best = 0.0
    for tmpl in UNUSABLE_TEMPLATES:
        th, tw = tmpl.shape[:2]
        res = cv2.resize(gray, (tw, th))
        s = float(cv2.matchTemplate(res, tmpl, cv2.TM_CCOEFF_NORMED).max())
        if s > best:
            best = s
    return best


# ─── DETECTION: TEMPLATE ON (backup) ─────────────────────────────────────────
def _load_on_templates() -> list[np.ndarray]:
    templates: list[np.ndarray] = []

    # Prima scelta: cartella immagini/on/ (grayscale)
    on_dir = IMAGES_DIR / "on"
    if on_dir.exists():
        for p in sorted(on_dir.glob("*.png")):
            if p.name.startswith("_bak_"):
                continue   # salta i backup
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                templates.append(img)
                log.info("Template ON caricato: on/%s", p.name)

    # Fallback: file singolo
    if not templates:
        fallback = IMAGES_DIR / "devotion skill on dettaglio.png"
        img = cv2.imread(str(fallback), cv2.IMREAD_GRAYSCALE)
        if img is not None:
            templates.append(img)
            log.info("Template ON caricato (fallback): %s", fallback.name)
        else:
            log.warning("Nessun template ON trovato (template matching disabilitato).")

    return templates

ON_TEMPLATES: list[np.ndarray] = _load_on_templates()


def _score_template(frame: np.ndarray) -> float:
    """Score massimo tra tutti i template ON (grayscale). 0.0 se nessun template."""
    if not ON_TEMPLATES:
        return 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best = 0.0
    for tmpl in ON_TEMPLATES:
        th, tw  = tmpl.shape[:2]
        resized = cv2.resize(gray, (tw, th))
        s = float(cv2.matchTemplate(resized, tmpl, cv2.TM_CCOEFF_NORMED).max())
        if s > best:
            best = s
    return best


def is_skill_active(frame: np.ndarray) -> tuple[bool, str]:
    """
    Determina se la skill Devotion è attiva.
    Restituisce (attiva: bool, descrizione: str).

    Logica:
      1. Bordo rosa su >= MIN_SIDES_WITH_PINK lati E pixel >= PINK_PIXEL_THRESHOLD → ATTIVA
         (metodo primario: il bordo continuo sui 4 lati è il segnale più affidabile)
      2. Se HSV non passa: template matching con soglia alzata → ATTIVA
         (metodo backup: richiede più frame consecutivi, vedi CONFIRM_FRAMES+1 nel loop)
      3. Nessuno supera soglia → NON attiva
    """
    pink_total, pink_sides = _check_pink_border(frame)

    if pink_total >= PINK_PIXEL_THRESHOLD and pink_sides >= MIN_SIDES_WITH_PINK:
        return True, f"bordo-rosa={pink_total}px su {pink_sides}/4 lati"

    score = _score_template(frame)
    if score >= ON_THRESHOLD:
        return True, f"template={score:.3f} (bordo={pink_total}px/{pink_sides}lati)"

    return False, f"rosa={pink_total}px/{pink_sides}lati tmpl={score:.3f}"


# ─── CATTURA SCHERMO ──────────────────────────────────────────────────────────
def capture_skill() -> np.ndarray:
    with mss.MSS() as sct:
        raw = sct.grab(SKILL_REGION)
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)


# ─── HOT-RELOAD ───────────────────────────────────────────────────────────────
_on_dir_mtime: float = (IMAGES_DIR / "on").stat().st_mtime if (IMAGES_DIR / "on").exists() else 0.0
_cfg_mtime:    float = _cfg_file.stat().st_mtime if _cfg_file.exists() else 0.0


def _check_reload():
    global ON_TEMPLATES, UNUSABLE_TEMPLATES, SKILL_REGION
    global ON_THRESHOLD, CONFIRM_FRAMES, PINK_PIXEL_THRESHOLD, MIN_SIDES_WITH_PINK
    global UNUSABLE_THRESHOLD, UNUSABLE_LOCKOUT
    global DEVOTION_DURATION, WARNING_BEFORE, COOLDOWN_MIN
    global DETECTION_MODE, KEYBOARD_KEY, RESET_KEY, BEEP_ENABLED, BEEP_DURATION
    global _on_dir_mtime, _cfg_mtime

    on_dir = IMAGES_DIR / "on"
    if on_dir.exists():
        mtime = on_dir.stat().st_mtime
        if mtime != _on_dir_mtime:
            _on_dir_mtime = mtime
            ON_TEMPLATES  = _load_on_templates()

    unusable_dir = IMAGES_DIR / "inutilizzabile"
    if unusable_dir.exists():
        mtime = unusable_dir.stat().st_mtime
        if mtime != getattr(_check_reload, "_unusable_mtime", 0.0):
            _check_reload._unusable_mtime = mtime
            UNUSABLE_TEMPLATES = _load_unusable_templates()

    if _cfg_file.exists():
        mtime = _cfg_file.stat().st_mtime
        if mtime != _cfg_mtime:
            _cfg_mtime = mtime
            try:
                _c = _json.loads(_cfg_file.read_text(encoding="utf-8"))
                SKILL_REGION = {
                    "left":   _c.get("skill_region_left",   SKILL_REGION["left"]),
                    "top":    _c.get("skill_region_top",    SKILL_REGION["top"]),
                    "width":  _c.get("skill_region_width",  SKILL_REGION["width"]),
                    "height": _c.get("skill_region_height", SKILL_REGION["height"]),
                }
                PINK_PIXEL_THRESHOLD = int(_c.get("pink_pixel_threshold",   PINK_PIXEL_THRESHOLD))
                MIN_SIDES_WITH_PINK  = int(_c.get("min_sides_with_pink",    MIN_SIDES_WITH_PINK))
                ON_THRESHOLD         = float(_c.get("on_threshold",          ON_THRESHOLD))
                CONFIRM_FRAMES       = int(_c.get("confirm_frames",          CONFIRM_FRAMES))
                UNUSABLE_THRESHOLD   = float(_c.get("unusable_threshold",    UNUSABLE_THRESHOLD))
                UNUSABLE_LOCKOUT     = float(_c.get("unusable_lockout",      UNUSABLE_LOCKOUT))
                DEVOTION_DURATION    = float(_c.get("devotion_duration",     DEVOTION_DURATION))
                WARNING_BEFORE       = float(_c.get("warning_before",        WARNING_BEFORE))
                COOLDOWN_MIN         = float(_c.get("cooldown_min",          COOLDOWN_MIN))
                DETECTION_MODE       = _c.get("detection_mode",              DETECTION_MODE)
                KEYBOARD_KEY         = _c.get("keyboard_key",                KEYBOARD_KEY)
                RESET_KEY            = _c.get("reset_key",                   RESET_KEY)
                BEEP_ENABLED         = bool(_c.get("beep_enabled",            BEEP_ENABLED))
                BEEP_DURATION        = int(_c.get("beep_duration",            BEEP_DURATION))
                log.info("Config ricaricato.")
            except Exception as e:
                log.warning("Errore ricaricamento config: %s", e)


# ─── MAIN ─────────────────────────────────────────────────────────────────────
async def main():
    preload_audio()

    # Copia in variabili locali (evita UnboundLocalError da assegnazione condizionale)
    mode    = DETECTION_MODE
    kb_key  = KEYBOARD_KEY

    log.info("Modalita' rilevamento: %s", mode.upper())

    # ── Avvio listener tastiera se richiesto ─────────────────────────────────
    _kb_listener    = None
    _reset_listener = None

    if mode == "keyboard":
        log.info("Tasto configurato: [%s]", kb_key.upper())
        _kb_listener = _start_key_listener(kb_key, _key_queue, "activate")
        if _kb_listener is None:
            log.error("pynput non disponibile — installa con: pip install pynput")
            log.warning("Fallback automatico a modalita' visuale.")
            mode = "visual"
        else:
            log.info("Listener tastiera ATTIVO — premi [%s] per attivare Devotion", kb_key.upper())

    reset_key = RESET_KEY
    if reset_key:
        _reset_listener = _start_key_listener(reset_key, _reset_queue, "reset")
        if _reset_listener:
            log.info("Tasto RESET configurato: [%s]  (torna subito in ascolto)", reset_key.upper())
        else:
            log.warning("pynput non disponibile — tasto reset non funzionera'.")

    if mode == "visual":
        log.info("Regione skill: left=%d top=%d width=%d height=%d",
                 SKILL_REGION["left"], SKILL_REGION["top"],
                 SKILL_REGION["width"], SKILL_REGION["height"])
        log.info("Rilevamento primario : bordo-rosa>=%dpx su >=%d/4 lati (conferma %d frame)",
                 PINK_PIXEL_THRESHOLD, MIN_SIDES_WITH_PINK, CONFIRM_FRAMES)
        log.info("Rilevamento backup   : template>=%.2f (conferma %d frame)",
                 ON_THRESHOLD, CONFIRM_FRAMES + 1)
        log.info("Anti-falsi positivi  : inutilizzabile>=%.2f → lockout %.1fs  [template: %d]",
                 UNUSABLE_THRESHOLD, UNUSABLE_LOCKOUT, len(UNUSABLE_TEMPLATES))

    in_stream  = sd.InputStream( samplerate=MIC_SR, channels=1,     dtype="float32",
                                  device=_mic_id,    callback=_mic_cb, latency="low")
    out_stream = sd.OutputStream(samplerate=OUT_SR, channels=CH_OUT, dtype="float32",
                                  device=_output_id, callback=_out_cb, latency="low")

    with in_stream, out_stream:
        log.info("Passthrough microfono ATTIVO.")
        log.info("In ascolto per attivazione Devotion...")

        state            = S_WATCHING
        activation_t     = 0.0
        confirm_count    = 0
        # counter separato per le due modalità di rilevamento
        confirm_hsv      = 0    # frame consecutivi con bordo rosa
        confirm_tmpl     = 0    # frame consecutivi con template
        warned           = False
        last_unusable_t  = -999.0   # ultima volta che la skill era inutilizzabile
        was_unusable     = False    # flag: nell'ultimo ciclo era inutilizzabile
        loop             = asyncio.get_event_loop()
        tick             = 0

        while True:
            tick += 1
            now = time.monotonic()

            # Cattura schermo solo in modalità visuale
            if mode == "visual":
                frame = await loop.run_in_executor(None, capture_skill)
            else:
                frame = None

            if tick % 67 == 0:
                _check_reload()

            # ── WATCHING ─────────────────────────────────────────────────────
            if state == S_WATCHING:

                # ── MODALITÀ TASTIERA ─────────────────────────────────────────
                if mode == "keyboard":
                    try:
                        _key_queue.get_nowait()
                        log.info("*** DEVOTION ATTIVATA via tasto [%s] ***", kb_key.upper())
                        state        = S_ACTIVE
                        activation_t = now
                        warned       = False
                        confirm_hsv  = 0
                        confirm_tmpl = 0
                        # Svuota la queue: lo spam durante active/cooldown viene ignorato
                        while not _key_queue.empty():
                            _key_queue.get_nowait()
                        _flush_reset()   # scarta reset accodati in WATCHING
                        play_audio(AUDIO_ON)
                    except queue.Empty:
                        pass
                    if tick % 40 == 0:
                        log.info("WATCHING (tastiera) | premi [%s] per attivare", kb_key.upper())
                    await asyncio.sleep(0.05)   # polling più frequente per la tastiera
                    continue

                # ── MODALITÀ VISUALE (codice esistente) ───────────────────────
                # ── 1. Check stato INUTILIZZABILE ────────────────────────────
                if UNUSABLE_TEMPLATES:
                    u_score = _score_unusable(frame)
                    if u_score >= UNUSABLE_THRESHOLD:
                        if not was_unusable:
                            log.info("Skill INUTILIZZABILE (score=%.3f) — ascolto sospeso", u_score)
                            was_unusable = True
                        last_unusable_t = now
                        confirm_hsv  = 0
                        confirm_tmpl = 0
                        if tick % 20 == 0:
                            log.info("UNUSABLE | score=%.3f | lockout-dopo=%.1fs",
                                     u_score, UNUSABLE_LOCKOUT)
                        await asyncio.sleep(0.15)
                        continue

                    # Appena uscita dall'inutilizzabile → applica lockout
                    if was_unusable:
                        was_unusable = False
                        log.info("Skill tornata utilizzabile — lockout %.1fs anti-falsi-positivi",
                                 UNUSABLE_LOCKOUT)

                # ── 2. Se in lockout post-inutilizzabile → ignora detection ─
                lockout_remaining = UNUSABLE_LOCKOUT - (now - last_unusable_t)
                if lockout_remaining > 0:
                    confirm_hsv  = 0
                    confirm_tmpl = 0
                    if tick % 20 == 0:
                        log.info("LOCKOUT  | rimasto=%.1fs", lockout_remaining)
                    await asyncio.sleep(0.15)
                    continue

                # ── 3. Rilevamento attivazione ────────────────────────────────
                pink_total, pink_sides = _check_pink_border(frame)
                tmpl_score             = _score_template(frame)

                # Metodo A: bordo rosa su 2+ lati (primario, veloce)
                hsv_ok = (pink_total >= PINK_PIXEL_THRESHOLD and
                          pink_sides >= MIN_SIDES_WITH_PINK)
                # Metodo B: template matching (backup, richiede 1 frame in più)
                tmpl_ok = tmpl_score >= ON_THRESHOLD

                if hsv_ok:
                    confirm_hsv  += 1
                    confirm_tmpl  = 0
                    reason = f"bordo-rosa={pink_total}px su {pink_sides}/4 lati"
                    log.debug("HSV conferma %d/%d [%s]", confirm_hsv, CONFIRM_FRAMES, reason)
                    if confirm_hsv >= CONFIRM_FRAMES:
                        log.info("*** DEVOTION ATTIVATA via HSV [%s] ***", reason)
                        state         = S_ACTIVE
                        activation_t  = now
                        warned        = False
                        confirm_hsv   = 0
                        confirm_tmpl  = 0
                        _flush_reset()   # scarta reset accodati in WATCHING
                        play_audio(AUDIO_ON)

                elif tmpl_ok:
                    confirm_tmpl += 1
                    confirm_hsv   = 0
                    reason = f"template={tmpl_score:.3f}"
                    log.debug("TMPL conferma %d/%d [%s]", confirm_tmpl, CONFIRM_FRAMES + 1, reason)
                    if confirm_tmpl >= CONFIRM_FRAMES + 1:   # +1 frame extra per template
                        log.info("*** DEVOTION ATTIVATA via template [%s] ***", reason)
                        state         = S_ACTIVE
                        activation_t  = now
                        warned        = False
                        confirm_hsv   = 0
                        confirm_tmpl  = 0
                        _flush_reset()   # scarta reset accodati in WATCHING
                        play_audio(AUDIO_ON)

                else:
                    if confirm_hsv > 0 or confirm_tmpl > 0:
                        log.debug("Conferma resettata — rosa=%dpx/%dlati tmpl=%.3f",
                                  pink_total, pink_sides, tmpl_score)
                    confirm_hsv  = 0
                    confirm_tmpl = 0

                if tick % 20 == 0:
                    log.info("WATCHING | rosa=%dpx/%dlati tmpl=%.3f | soglie rosa>=%d/%dlati tmpl>=%.2f",
                             pink_total, pink_sides, tmpl_score,
                             PINK_PIXEL_THRESHOLD, MIN_SIDES_WITH_PINK, ON_THRESHOLD)

            # ── ACTIVE ───────────────────────────────────────────────────────
            elif state == S_ACTIVE:
                # Reset manuale (bottone GUI o hotkey)
                if _check_reset():
                    log.info("*** RESET MANUALE — torno in ascolto (WATCHING) ***")
                    state        = S_WATCHING
                    warned       = False
                    confirm_hsv  = 0
                    confirm_tmpl = 0
                    while not _key_queue.empty():
                        _key_queue.get_nowait()
                    await asyncio.sleep(0.15)
                    continue

                elapsed   = now - activation_t
                remaining = DEVOTION_DURATION - elapsed

                if not warned and elapsed >= (DEVOTION_DURATION - WARNING_BEFORE):
                    log.info("Devotion: avviso %gs rimanenti", WARNING_BEFORE)
                    play_audio(AUDIO_WARN)
                    warned = True

                if elapsed >= DEVOTION_DURATION:
                    log.info("Devotion SCADUTA — cooldown %gs", COOLDOWN_MIN)
                    state = S_COOLDOWN
                    play_audio(AUDIO_OFF)

                if tick % 20 == 0:
                    log.info("ACTIVE   | trascorsi=%.1fs | rimangono=%.1fs", elapsed, max(0, remaining))

            # ── COOLDOWN ─────────────────────────────────────────────────────
            elif state == S_COOLDOWN:
                # Reset manuale (bottone GUI o hotkey)
                if _check_reset():
                    log.info("*** RESET MANUALE — torno in ascolto (WATCHING) ***")
                    state        = S_WATCHING
                    confirm_hsv  = 0
                    confirm_tmpl = 0
                    while not _key_queue.empty():
                        _key_queue.get_nowait()
                    await asyncio.sleep(0.15)
                    continue

                elapsed    = now - activation_t
                cd_elapsed = elapsed - DEVOTION_DURATION
                cd_left    = COOLDOWN_MIN - cd_elapsed

                if cd_elapsed >= COOLDOWN_MIN:
                    log.info("Cooldown terminato — torno in ascolto.")
                    state         = S_WATCHING
                    confirm_count = 0
                    # Scarta tasti premuti durante active/cooldown
                    while not _key_queue.empty():
                        _key_queue.get_nowait()

                if tick % 20 == 0:
                    log.info("COOLDOWN | cd_rimasto=%.1fs", max(0, cd_left))

            await asyncio.sleep(0.15)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Monitor fermato.")
