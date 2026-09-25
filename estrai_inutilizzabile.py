#!/usr/bin/env python3
# Autore: PaoloBrosio — © 2026 PaoloBrosio
"""
estrai_inutilizzabile.py — Estrae il template "skill inutilizzabile" dall'immagine
                           di calibrazione e lo salva in immagini/inutilizzabile/

Usalo dopo aver messo uno screenshot dello stato "skill non utilizzabile"
(es. in acqua, area locked) nella cartella 'immagini di calibrazione/'.
"""

import cv2
import numpy as np
import json
from pathlib import Path

BASE_DIR   = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "immagini"
CALIB_DIR  = BASE_DIR / "immagini di calibrazione"
CONFIG_FILE = BASE_DIR / "config.json"
OUT_DIR    = IMAGES_DIR / "inutilizzabile"

CALIB_NAME = "immagine calibrazione skill inutilizzabile.png"

print("=" * 58)
print("  Estrai Template Inutilizzabile — Devotion Bot")
print("=" * 58)

img = cv2.imread(str(CALIB_DIR / CALIB_NAME))
if img is None:
    print(f"\nERRORE: non trovo '{CALIB_NAME}'")
    print(f"  Cartella: {CALIB_DIR}")
    input("Premi INVIO per uscire.")
    raise SystemExit

H, W = img.shape[:2]
print(f"\nImmagine caricata: {W}x{H}")

cfg = {}
if CONFIG_FILE.exists():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

ox = int(cfg.get("skill_region_left",   1820))
oy = int(cfg.get("skill_region_top",    1000))
ow = int(cfg.get("skill_region_width",    72))
oh = int(cfg.get("skill_region_height",   72))

print(f"Regione da config.json: left={ox} top={oy} width={ow} height={oh}")

# Estrai la regione
crop = img[oy:min(H, oy+oh), ox:min(W, ox+ow)].copy()
if crop.size == 0:
    print("\nERRORE: coordinate fuori dall'immagine.")
    print("Controlla che SKILL_REGION in config.json sia corretta.")
    input("Premi INVIO per uscire.")
    raise SystemExit

scale = min(1.0, 1280 / W, 720 / H)
vis   = cv2.resize(img.copy(), (int(W * scale), int(H * scale)))
cv2.rectangle(vis,
              (int(ox * scale), int(oy * scale)),
              (int((ox+ow) * scale), int((oy+oh) * scale)),
              (0, 255, 255), 2)
cv2.putText(vis, "Regione skill", (int(ox * scale), max(12, int(oy * scale) - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
cv2.putText(vis, "INUTILIZZABILE", (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (60, 60, 220), 2, cv2.LINE_AA)

ZOOM = max(2, min(8, 280 // max(ow, oh, 1)))
big  = cv2.resize(crop, None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)

print()
print("  S = Salva template inutilizzabile")
print("  M = Seleziona regione manualmente")
print("  Q = Esci senza salvare")

cv2.imshow("Screenshot inutilizzabile — S=salva  M=manuale  Q=esci", vis)
cv2.imshow("Preview regione (zoom)", big)
key = cv2.waitKey(0) & 0xFF
cv2.destroyAllWindows()

if key == ord('q'):
    print("Uscito senza salvare.")
    input("Premi INVIO per chiudere.")
    raise SystemExit

if key == ord('m'):
    print("\nSelezione manuale: trascina il rettangolo sull'icona.")
    roi = cv2.selectROI("Selezione manuale — INVIO=conferma  C=annulla",
                        vis, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    rx, ry, rw, rh = roi
    if rw == 0 or rh == 0:
        print("Annullato.")
        input("Premi INVIO per chiudere.")
        raise SystemExit
    ox, oy = int(rx / scale), int(ry / scale)
    ow, oh = int(rw / scale), int(rh / scale)
    crop = img[oy:oy+oh, ox:ox+ow].copy()

OUT_DIR.mkdir(exist_ok=True)
# Conta file esistenti
existing = sorted(OUT_DIR.glob("inutilizzabile_*.png"))
idx = len(existing) + 1
out_path = OUT_DIR / f"inutilizzabile_{idx:03d}.png"
cv2.imwrite(str(out_path), cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
print(f"\nSalvato: {out_path}  ({crop.shape[1]}x{crop.shape[0]} px, grayscale)")
print("\nOra puoi avviare il monitor — rileva automaticamente lo stato inutilizzabile.")
input("\nPremi INVIO per chiudere.")
