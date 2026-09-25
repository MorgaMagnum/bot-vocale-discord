#!/usr/bin/env python3
"""
ricalibra_template.py — Ricrea i template dal tuo schermo attuale

Guida passo-passo per catturare la skill Devotion nei tre stati:
  1. Attiva  (timer durata visibile, es. "20s")
  2. 5 sec   (timer ~5s rimasti)
  3. Cooldown (icona scura con timer cooldown)

I nuovi template sostituiscono quelli nella cartella 'immagini/'.
"""

import cv2
import numpy as np
import mss
import json
import time
from pathlib import Path

BASE_DIR    = Path(__file__).parent
IMAGES_DIR  = BASE_DIR / "immagini"
CONFIG_FILE = BASE_DIR / "config.json"

# ─── LEGGI REGIONE DA CONFIG ─────────────────────────────────────────────────
region = {"left": 1820, "top": 1000, "width": 72, "height": 72}
if CONFIG_FILE.exists():
    try:
        c = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        region = {
            "left":   c.get("skill_region_left",   region["left"]),
            "top":    c.get("skill_region_top",    region["top"]),
            "width":  c.get("skill_region_width",  region["width"]),
            "height": c.get("skill_region_height", region["height"]),
        }
    except Exception:
        pass

print("=" * 58)
print("  Ricalibratore Template — Devotion Bot")
print("=" * 58)
print(f"\nRegione attuale: left={region['left']}  top={region['top']}")
print(f"                 width={region['width']}  height={region['height']}")
print()
print("Assicurati che il gioco sia visibile sullo schermo.")
print("La finestra 'Anteprima' mostra in tempo reale cosa")
print("sta vedendo il bot nella regione configurata.")
print()

# ─── CATTURA LIVE ────────────────────────────────────────────────────────────
def capture() -> np.ndarray:
    with mss.MSS() as sct:
        raw = sct.grab(region)
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)

ZOOM = 6   # zoom della preview

def show_preview(label: str, extra: str = "") -> np.ndarray | None:
    """
    Mostra anteprima live. Restituisce il frame al momento della pressione
    di SPAZIO, oppure None se si preme Q.
    """
    print(f"\n>>> {label}")
    if extra:
        print(f"    {extra}")
    print("    SPAZIO = cattura questo frame   |   Q = esci")
    print()

    while True:
        frame = capture()
        big   = cv2.resize(frame, None, fx=ZOOM, fy=ZOOM,
                           interpolation=cv2.INTER_NEAREST)

        # Bordo colorato come indicatore
        cv2.rectangle(big, (0, 0), (big.shape[1]-1, big.shape[0]-1), (0, 200, 255), 3)

        # Testo istruzioni
        cv2.putText(big, label, (6, 20), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(big, "SPAZIO=cattura  Q=esci", (6, big.shape[0]-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

        cv2.imshow("Anteprima live (zoom 6x)", big)
        key = cv2.waitKey(30) & 0xFF

        if key == ord(' '):
            return frame
        if key == ord('q'):
            return None

# ─── STEP 1: ATTIVA ──────────────────────────────────────────────────────────
print("PASSO 1 / 3 — Skill ATTIVA")
print("-" * 40)
print("Attiva la Devotion nel gioco in modo che il timer")
print("di durata sia visibile (es. '20s', '18s', ecc.).")

frame_on = show_preview("STATO: ATTIVA — timer durata visibile",
                        "Es: icona illuminata con '20s'")
if frame_on is None:
    cv2.destroyAllWindows()
    print("\nUscito senza salvare.")
    input("Premi INVIO per chiudere.")
    raise SystemExit

cv2.destroyAllWindows()

# ─── STEP 2: 5 SECONDI ───────────────────────────────────────────────────────
print("\nPASSO 2 / 3 — 5 SECONDI RIMANENTI")
print("-" * 40)
print("Aspetta che il timer scenda a circa 5 secondi.")
print("Alcuni setup mostrano un cambio visivo (bordo lampeggiante")
print("o colore diverso). Se non c'è differenza visiva rispetto")
print("allo stato 'on', cattura comunque con ~5s sul timer.")

frame_5 = show_preview("STATO: 5 SEC — timer ~5s rimasti",
                       "Es: icona con '5s' o bordo giallo")
if frame_5 is None:
    cv2.destroyAllWindows()
    print("\nUscito senza salvare.")
    input("Premi INVIO per chiudere.")
    raise SystemExit

cv2.destroyAllWindows()

# ─── STEP 3: COOLDOWN ────────────────────────────────────────────────────────
print("\nPASSO 3 / 3 — COOLDOWN")
print("-" * 40)
print("Aspetta che la skill scada e entri in cooldown.")
print("L'icona di solito diventa scura con il timer di ricarica.")

frame_cd = show_preview("STATO: COOLDOWN — icona scura con timer ricarica",
                        "Es: icona grigia/scura con '45s'")
if frame_cd is None:
    cv2.destroyAllWindows()
    print("\nUscito senza salvare.")
    input("Premi INVIO per chiudere.")
    raise SystemExit

cv2.destroyAllWindows()

# ─── RIEPILOGO ───────────────────────────────────────────────────────────────
print("\nRiepilogo catture:")

def show_summary():
    h = max(frame_on.shape[0], frame_5.shape[0], frame_cd.shape[0])
    imgs = []
    for f, label in [(frame_on, "ATTIVA"), (frame_5, "5 SEC"), (frame_cd, "COOLDOWN")]:
        big = cv2.resize(f, None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
        # Aggiungi etichetta
        canvas = np.zeros((big.shape[0] + 22, big.shape[1], 3), dtype=np.uint8)
        canvas[:big.shape[0]] = big
        cv2.putText(canvas, label, (4, big.shape[0] + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
        imgs.append(canvas)
    combined = np.hstack(imgs)
    cv2.imshow("Riepilogo — S=SALVA   Q=ricomincia", combined)
    key = cv2.waitKey(0) & 0xFF
    cv2.destroyAllWindows()
    return key

key = show_summary()

if key != ord('s'):
    print("\nNon salvato. Riavvia lo script per riprovare.")
    input("Premi INVIO per chiudere.")
    raise SystemExit

# ─── SALVA TEMPLATE ──────────────────────────────────────────────────────────
saves = [
    (frame_on, "devotion skill on dettaglio.png"),
    (frame_5,  "devotion off in 5 dettaglio.png"),
    (frame_cd, "devotion cd dettaglio.png"),
]

for frame, filename in saves:
    path = IMAGES_DIR / filename
    # Backup del vecchio
    backup = IMAGES_DIR / (filename.replace(".png", "_backup.png"))
    if path.exists():
        import shutil
        shutil.copy(path, backup)
    cv2.imwrite(str(path), frame)
    print(f"  Salvato: {filename}  ({frame.shape[1]}x{frame.shape[0]} px)")

print("\nTemplate aggiornati! I backup sono in 'immagini/*_backup.png'.")
print("Riavvia il monitor nell'app per usare i nuovi template.")
input("\nPremi INVIO per chiudere.")
