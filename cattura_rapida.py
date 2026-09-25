#!/usr/bin/env python3
# Autore: PaoloBrosio — © 2026 PaoloBrosio
"""
cattura_rapida.py — Preview live + salvataggio template + spostamento regione

Controlli:
  Frecce        →  sposta la regione (Left / Top)
  W / S         →  aumenta / diminuisce altezza
  A / D         →  diminuisce / aumenta larghezza
  + / -         →  cambia step di spostamento (1, 5, 10, 20 px)
  1             →  salva ATTIVA
  2             →  salva 5 SEC
  3             →  salva COOLDOWN
  Q             →  esci e salva regione in config.json
"""

import cv2
import numpy as np
import mss
import json
import shutil
from pathlib import Path
from datetime import datetime

BASE_DIR    = Path(__file__).parent
IMAGES_DIR  = BASE_DIR / "immagini"
CONFIG_FILE = BASE_DIR / "config.json"

# ─── LEGGI CONFIG ─────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_region(region: dict) -> None:
    cfg = load_config()
    cfg.update({
        "skill_region_left":   region["left"],
        "skill_region_top":    region["top"],
        "skill_region_width":  region["width"],
        "skill_region_height": region["height"],
    })
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

cfg = load_config()
region = {
    "left":   cfg.get("skill_region_left",   1820),
    "top":    cfg.get("skill_region_top",    1000),
    "width":  cfg.get("skill_region_width",    72),
    "height": cfg.get("skill_region_height",   72),
}

ON_DIR          = IMAGES_DIR / "on"
UNUSABLE_DIR    = IMAGES_DIR / "inutilizzabile"
ON_DIR.mkdir(exist_ok=True)
UNUSABLE_DIR.mkdir(exist_ok=True)

def _next_unusable_path() -> Path:
    existing = sorted(UNUSABLE_DIR.glob("inutilizzabile_*.png"))
    idx = len(existing) + 1
    return UNUSABLE_DIR / f"inutilizzabile_{idx:03d}.png"

def _next_on_path() -> Path:
    """Trova il prossimo nome disponibile: on_001.png, on_002.png ..."""
    existing = sorted(ON_DIR.glob("on_*.png"))
    idx = len(existing) + 1
    return ON_DIR / f"on_{idx:03d}.png"

# I tasti 2/3 salvano ancora i template ausiliari (usati solo come fallback)
SAVE_SINGLE = {
    ord('2'): ("devotion off in 5 dettaglio.png",  "5 SEC    (ausiliario)", (0, 180, 220)),
    ord('3'): ("devotion cd dettaglio.png",        "COOLDOWN (ausiliario)", (80, 80, 220)),
}

STEPS    = [1, 5, 10, 20]
step_idx = 1          # default 5px
ZOOM     = 7

print("=" * 52)
print("  Cattura Rapida — usa i tasti nella finestra CV2")
print("=" * 52)
print("  Frecce = sposta   A/D = larghezza   W/S = altezza")
print("  +/-    = cambia step (1/5/10/20 px)")
print("  1 = Aggiungi cattura ATTIVA in immagini/on/")
print("  4 = Aggiungi cattura INUTILIZZABILE in immagini/inutilizzabile/")
print("  X = Cancella ULTIMA cattura ON salvata")
print("  2 = Salva 5SEC (ausiliario)")
print("  3 = Salva COOLDOWN (ausiliario)")
print("  Q = esci + salva regione")
print()

last_msg   = ""
last_color = (80, 220, 80)
msg_timer  = 0

def capture() -> np.ndarray:
    with mss.MSS() as sct:
        raw = sct.grab({
            "left":   region["left"],
            "top":    region["top"],
            "width":  region["width"],
            "height": region["height"],
        })
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)

while True:
    frame = capture()
    big   = cv2.resize(frame, None, fx=ZOOM, fy=ZOOM,
                       interpolation=cv2.INTER_NEAREST)
    h, w  = big.shape[:2]

    # Overlay scuro in basso
    bar_h = 72
    overlay = big.copy()
    cv2.rectangle(overlay, (0, h - bar_h), (w, h), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.75, big, 0.25, 0, big)

    step = STEPS[step_idx]

    # Riga 1 — coordinate correnti
    cv2.putText(big,
                f"L={region['left']}  T={region['top']}  "
                f"W={region['width']}  H={region['height']}  step={step}px",
                (6, h - bar_h + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

    # Riga 2 — tasti
    cv2.putText(big,
                "Frecce=sposta  A/D=W  W/S=H  +/-=step",
                (6, h - bar_h + 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (130, 130, 130), 1)

    # Riga 3 — tasti salvataggio + contatore ON
    on_count       = len(list(ON_DIR.glob("on_*.png")))
    unusable_count = len(list(UNUSABLE_DIR.glob("inutilizzabile_*.png")))
    cv2.putText(big, f"1=+ON({on_count})  4=+INUTILIZ({unusable_count})  X=undoON  2=5sec  3=CD  Q=esci",
                (6, h - bar_h + 52),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (130, 130, 130), 1)

    # Messaggio ultimo salvataggio
    if msg_timer > 0:
        cv2.putText(big, last_msg, (6, h - bar_h + 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, last_color, 1)
        msg_timer -= 1

    # Bordo della preview
    cv2.rectangle(big, (0, 0), (w - 1, h - bar_h - 1), (60, 60, 60), 1)

    cv2.imshow("Cattura Rapida", big)
    # Su Windows i tasti freccia hanno codici > 255, non usare & 0xFF
    key = cv2.waitKey(30)
    ch  = key & 0xFF   # per tasti normali ASCII

    # ── Esci ─────────────────────────────────────────────────────────────────
    if ch == ord('q'):
        break

    # ── Step ─────────────────────────────────────────────────────────────────
    elif ch in (ord('+'), ord('=')):
        step_idx = min(step_idx + 1, len(STEPS) - 1)
    elif ch == ord('-'):
        step_idx = max(step_idx - 1, 0)

    # ── Spostamento (frecce) — codici Windows e Linux ─────────────────────────
    elif key in (2424832, 65361):   # ←
        region["left"] = max(0, region["left"] - STEPS[step_idx])
    elif key in (2555904, 65363):   # →
        region["left"] += STEPS[step_idx]
    elif key in (2490368, 65362):   # ↑
        region["top"] = max(0, region["top"] - STEPS[step_idx])
    elif key in (2621440, 65364):   # ↓
        region["top"] += STEPS[step_idx]

    # ── Dimensione ───────────────────────────────────────────────────────────
    elif ch == ord('a'):
        region["width"] = max(10, region["width"] - STEPS[step_idx])
    elif ch == ord('d'):
        region["width"] += STEPS[step_idx]
    elif ch == ord('s'):
        region["height"] += STEPS[step_idx]
    elif ch == ord('w'):
        region["height"] = max(10, region["height"] - STEPS[step_idx])

    # ── Salvataggio template INUTILIZZABILE ──────────────────────────────────
    elif ch == ord('4'):
        path = _next_unusable_path()
        cv2.imwrite(str(path), cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        count      = len(list(UNUSABLE_DIR.glob("inutilizzabile_*.png")))
        last_msg   = f"INUTILIZZABILE #{count} salvato: {path.name}"
        last_color = (80, 80, 220)
        msg_timer  = 60
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {last_msg}")

    # ── Salvataggio template ON (aggiunge in immagini/on/) ───────────────────
    elif ch == ord('1'):
        path = _next_on_path()
        cv2.imwrite(str(path), frame)
        count      = len(list(ON_DIR.glob("on_*.png")))
        last_msg   = f"ON #{count} salvato: {path.name}"
        last_color = (0, 220, 80)
        msg_timer  = 60
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {last_msg}")

    # ── Cancella ultima cattura ON ────────────────────────────────────────────
    elif ch == ord('x'):
        existing = sorted(ON_DIR.glob("on_*.png"))
        if existing:
            existing[-1].unlink()
            count      = len(list(ON_DIR.glob("on_*.png")))
            last_msg   = f"Cancellato {existing[-1].name}  (rimasti: {count})"
            last_color = (80, 80, 220)
            msg_timer  = 60
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {last_msg}")
        else:
            last_msg   = "Nessuna cattura ON da cancellare"
            last_color = (80, 80, 200)
            msg_timer  = 60

    # ── Salvataggio ausiliari (2/3) ───────────────────────────────────────────
    elif ch in SAVE_SINGLE:
        filename, label, color = SAVE_SINGLE[ch]
        path = IMAGES_DIR / filename
        if path.exists():
            ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy(path, IMAGES_DIR / filename.replace(".png", f"_bak_{ts}.png"))
        cv2.imwrite(str(path), frame)
        last_msg   = f"Salvato: {label}"
        last_color = color
        msg_timer  = 60
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {last_msg}  →  {filename}")

cv2.destroyAllWindows()

# Salva regione aggiornata in config.json
save_region(region)
print(f"\nRegione salvata: {region}")
print("Il monitor ricaricherà la nuova posizione al prossimo riavvio.")
