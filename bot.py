#!/usr/bin/env python3
"""
Bot Discord - Monitoraggio Skill Devotion (Throne and Liberty)
Riproduce audio nel canale vocale Discord in base allo stato della skill.

Setup:
  1. Installa dipendenze:  pip install -r requirements.txt
  2. Installa ffmpeg e aggiungilo al PATH di sistema
  3. Crea un bot Discord su https://discord.com/developers/applications
  4. Imposta DISCORD_TOKEN e VOICE_CHANNEL_ID qui sotto
  5. Esegui calibrate.py per trovare le coordinate dello schermo
  6. Avvia il bot:  python bot.py
"""

import asyncio
import discord
from discord.ext import tasks
import cv2
import numpy as np
import mss
from pathlib import Path
import logging

# ════════════════════════════════════════════════════════════════
#  CONFIGURAZIONE — modifica questi valori prima di avviare
# ════════════════════════════════════════════════════════════════

DISCORD_TOKEN    = "IL_TUO_TOKEN_QUI"
VOICE_CHANNEL_ID = 0       # ID numerico del canale vocale (tasto destro sul canale → Copia ID)

# Regione dello schermo dove appare l'icona Devotion (slot T nella hotbar).
# Esegui calibrate.py per trovare le coordinate esatte sul tuo schermo.
SKILL_REGION = {
    "left":   1820,   # coordinata X (pixel da sinistra del monitor)
    "top":    1000,   # coordinata Y (pixel dall'alto del monitor)
    "width":   72,    # larghezza in pixel
    "height":  72,    # altezza in pixel
}

MATCH_THRESHOLD = 0.65    # soglia di confidenza template matching (0.0–1.0)
CHECK_INTERVAL  = 0.15    # secondi tra ogni scansione dello schermo

# Carica override da config.json (se esiste — gestito da app.py)
import json as _json, pathlib as _pl
_cfg_file = _pl.Path(__file__).parent / "config.json"
if _cfg_file.exists():
    try:
        _c = _json.loads(_cfg_file.read_text(encoding="utf-8"))
        if _c.get("discord_token"):
            DISCORD_TOKEN = _c["discord_token"]
        if _c.get("voice_channel_id"):
            VOICE_CHANNEL_ID = int(_c["voice_channel_id"])
        SKILL_REGION = {
            "left":   _c.get("skill_region_left",   SKILL_REGION["left"]),
            "top":    _c.get("skill_region_top",    SKILL_REGION["top"]),
            "width":  _c.get("skill_region_width",  SKILL_REGION["width"]),
            "height": _c.get("skill_region_height", SKILL_REGION["height"]),
        }
        MATCH_THRESHOLD = float(_c.get("match_threshold", MATCH_THRESHOLD))
        CHECK_INTERVAL  = float(_c.get("check_interval",  CHECK_INTERVAL))
    except Exception:
        pass

# ════════════════════════════════════════════════════════════════

BASE_DIR   = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "immagini"
AUDIO_DIR  = BASE_DIR / "tracce audio"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("devotion-bot")

# ─── STATI ───────────────────────────────────────────────────────────────────
STATE_UNKNOWN  = "unknown"
STATE_ON       = "on"        # skill attiva (timer durata in corso)
STATE_OFF_IN_5 = "off_in_5"  # 5 secondi rimanenti di durata attiva
STATE_COOLDOWN = "cooldown"  # skill scaduta, in cooldown

AUDIO_MAP = {
    STATE_ON:       "devotion on.wav",
    STATE_OFF_IN_5: "devotion off in 5.wav",
    STATE_COOLDOWN: "devotion off.wav",
}

# ─── CARICA TEMPLATE ─────────────────────────────────────────────────────────
def load_template(filename: str) -> np.ndarray:
    path = IMAGES_DIR / filename
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Immagine template non trovata: {path}")
    return img

TEMPLATES: dict[str, np.ndarray] = {
    STATE_ON:       load_template("devotion skill on dettaglio.png"),
    STATE_OFF_IN_5: load_template("devotion off in 5 dettaglio.png"),
    STATE_COOLDOWN: load_template("devotion cd dettaglio.png"),
}

log.info("Template caricati: %s", list(TEMPLATES.keys()))

# ─── RICONOSCIMENTO STATO ────────────────────────────────────────────────────
def capture_skill() -> np.ndarray:
    """Cattura la regione dello schermo con l'icona Devotion."""
    with mss.mss() as sct:
        raw = sct.grab(SKILL_REGION)
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)

def score_template(frame: np.ndarray, template: np.ndarray) -> float:
    """Confronta il frame con il template (ridimensiona al volo se necessario)."""
    th, tw = template.shape[:2]
    resized = cv2.resize(frame, (tw, th))
    result  = cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)
    return float(result.max())

def detect_state(frame: np.ndarray) -> str:
    """Restituisce lo stato con il punteggio di matching più alto."""
    best_state = STATE_UNKNOWN
    best_score = 0.0
    for state, tmpl in TEMPLATES.items():
        s = score_template(frame, tmpl)
        log.debug("  [%s] score=%.3f", state, s)
        if s > best_score:
            best_state, best_score = state, s
    if best_score >= MATCH_THRESHOLD:
        return best_state
    return STATE_UNKNOWN

# ─── BOT DISCORD ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
client  = discord.Client(intents=intents)

_current_state: str = STATE_UNKNOWN
_voice_client:  discord.VoiceClient | None = None

def play_audio(filename: str) -> None:
    """Riproduce un file WAV nel canale vocale Discord."""
    if _voice_client is None or not _voice_client.is_connected():
        log.warning("Non connesso al canale vocale — audio non riprodotto")
        return
    if _voice_client.is_playing():
        _voice_client.stop()
    path = AUDIO_DIR / filename
    log.info(">>> AUDIO: %s", filename)
    _voice_client.play(discord.FFmpegPCMAudio(str(path)))

def handle_transition(old: str, new: str) -> None:
    """Gestisce le transizioni di stato e decide quale audio riprodurre."""
    log.info("Stato: [%s] → [%s]", old, new)

    # Non riprodurre audio alla prima rilevazione (avvio del bot)
    if old == STATE_UNKNOWN:
        return

    if new == STATE_ON:
        # Skill appena attivata
        play_audio(AUDIO_MAP[STATE_ON])

    elif new == STATE_OFF_IN_5:
        # 5 secondi rimanenti di durata attiva
        play_audio(AUDIO_MAP[STATE_OFF_IN_5])

    elif new == STATE_COOLDOWN:
        # Skill scaduta → entra in cooldown
        # Suona solo se arriva da uno stato attivo (non da UNKNOWN o già in cooldown)
        if old in (STATE_ON, STATE_OFF_IN_5):
            play_audio(AUDIO_MAP[STATE_COOLDOWN])

@tasks.loop(seconds=CHECK_INTERVAL)
async def monitor_loop() -> None:
    """Task periodico: cattura schermo, rileva stato, gestisce transizioni."""
    global _current_state
    loop      = asyncio.get_event_loop()
    frame     = await loop.run_in_executor(None, capture_skill)
    new_state = detect_state(frame)
    if new_state != _current_state:
        handle_transition(_current_state, new_state)
        _current_state = new_state

@client.event
async def on_ready() -> None:
    global _voice_client
    log.info("Bot connesso come: %s (ID: %s)", client.user, client.user.id)

    channel = client.get_channel(VOICE_CHANNEL_ID)
    if channel is None:
        log.error("Canale vocale non trovato! Controlla VOICE_CHANNEL_ID.")
        await client.close()
        return
    if not isinstance(channel, discord.VoiceChannel):
        log.error("Il canale %s non e' un canale vocale!", channel)
        await client.close()
        return

    _voice_client = await channel.connect()
    log.info("Connesso al canale vocale: %s", channel.name)
    log.info("Monitoraggio avviato — intervallo %.2fs, soglia %.2f",
             CHECK_INTERVAL, MATCH_THRESHOLD)
    monitor_loop.start()

client.run(DISCORD_TOKEN)
