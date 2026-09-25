#!/usr/bin/env python3
"""
calibra_auto.py — Trova automaticamente la skill Devotion nello screenshot

Carica lo screenshot nella cartella 'calibrazione default', cerca l'icona
Devotion con template matching a scale multiple, mostra il risultato e
salva le coordinate in config.json.
"""

import cv2
import numpy as np
import json
from pathlib import Path

BASE_DIR    = Path(__file__).parent
IMAGES_DIR  = BASE_DIR / "immagini"
CONFIG_FILE = BASE_DIR / "config.json"
CALIB_DIR   = BASE_DIR / "calibrazione default"

# ─── CARICA SCREENSHOT ───────────────────────────────────────────────────────
screenshots = sorted(CALIB_DIR.glob("*.png")) + sorted(CALIB_DIR.glob("*.jpg"))
if not screenshots:
    print("Nessuno screenshot trovato in 'calibrazione default/'")
    input("Premi INVIO per uscire.")
    raise SystemExit

screenshot_path = screenshots[0]
full = cv2.imread(str(screenshot_path))
if full is None:
    print(f"Impossibile aprire: {screenshot_path}")
    input("Premi INVIO per uscire.")
    raise SystemExit

H, W = full.shape[:2]
print(f"Screenshot: {screenshot_path.name}  ({W}x{H})")

# ─── TEMPLATE CANDIDATES ─────────────────────────────────────────────────────
# Prova tutti i template disponibili, in ordine di preferenza
template_files = [
    "devotion skill on dettaglio.png",
    "devotion cd dettaglio.png",
    "devotion off in 5 dettaglio.png",
    "devotion skill dettaglio.png",
]

# ─── RICERCA MULTI-SCALA ─────────────────────────────────────────────────────
best = {"score": 0.0, "loc": None, "size": None, "name": None, "scale": 1.0}

for tmpl_name in template_files:
    tmpl_path = IMAGES_DIR / tmpl_name
    if not tmpl_path.exists():
        continue
    tmpl = cv2.imread(str(tmpl_path))
    if tmpl is None:
        continue
    th, tw = tmpl.shape[:2]

    # Cerca a scale da 0.5× a 3.0× (copre risoluzioni 720p–4K se il template è 1080p)
    for scale in np.arange(0.5, 3.05, 0.05):
        nw, nh = int(tw * scale), int(th * scale)
        if nw >= W or nh >= H or nw < 4 or nh < 4:
            continue
        scaled = cv2.resize(tmpl, (nw, nh), interpolation=cv2.INTER_LINEAR)
        res = cv2.matchTemplate(full, scaled, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best["score"]:
            best = {"score": max_val, "loc": max_loc,
                    "size": (nw, nh), "name": tmpl_name, "scale": scale}

print(f"\nMigliore corrispondenza:")
print(f"  Template : {best['name']}")
print(f"  Score    : {best['score']:.3f}  (soglia consigliata: 0.65)")
print(f"  Posizione: {best['loc']}")
print(f"  Scala    : {best['scale']:.2f}×")

if best["score"] < 0.40:
    print("\nATTENZIONE: score molto basso — l'icona Devotion potrebbe non essere")
    print("visibile nello screenshot (skill non attiva, hotbar nascosta, ecc.).")
    print("Puoi comunque continuare e selezionare la regione manualmente.")

# ─── VISUALIZZA RISULTATO ────────────────────────────────────────────────────
PAD = 10
x, y   = best["loc"] if best["loc"] else (0, 0)
tw, th = best["size"] if best["size"] else (72, 72)

# Regione finale con padding
region = {
    "left":   max(0, x - PAD),
    "top":    max(0, y - PAD),
    "width":  tw + PAD * 2,
    "height": th + PAD * 2,
}

# Disegna sul full screenshot per review
vis = full.copy()
cv2.rectangle(vis, (x, y), (x + tw, y + th), (0, 255, 0), 3)
cv2.rectangle(vis,
              (region["left"], region["top"]),
              (region["left"] + region["width"], region["top"] + region["height"]),
              (0, 200, 255), 1)

# Zoom sulla zona trovata (per ispezionare)
pad_zoom = 60
x1 = max(0, x - pad_zoom)
y1 = max(0, y - pad_zoom)
x2 = min(W, x + tw + pad_zoom)
y2 = min(H, y + th + pad_zoom)
zoom = cv2.resize(vis[y1:y2, x1:x2], None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)

# Mostra entrambi
print("\n--- FINESTRA 1: screenshot completo con la regione evidenziata (verde)")
print("--- FINESTRA 2: zoom 3× sulla zona trovata")
print("\nControlla che il riquadro verde sia sull'icona Devotion nella hotbar.")
print("  Premi  S  per SALVARE le coordinate in config.json")
print("  Premi  M  per selezionare MANUALMENTE la regione")
print("  Premi  Q  per USCIRE senza salvare")

# Ridimensiona il full per farlo stare nello schermo
scale_vis = min(1.0, 1280 / W, 720 / H)
vis_small = cv2.resize(vis, (int(W * scale_vis), int(H * scale_vis)))

cv2.imshow("Screenshot completo — S=salva  M=manuale  Q=esci", vis_small)
cv2.imshow("Zoom zona trovata", zoom)
cv2.moveWindow("Zoom zona trovata", 0, 0)

key = cv2.waitKey(0) & 0xFF
cv2.destroyAllWindows()

# ─── SELEZIONE MANUALE ───────────────────────────────────────────────────────
if key == ord('m'):
    print("\nSelezione manuale: trascina un rettangolo sull'icona Devotion.")
    print("Premi SPAZIO o INVIO per confermare, C per annullare.")
    roi = cv2.selectROI(
        "Selezione manuale — INVIO per confermare",
        vis_small, showCrosshair=True, fromCenter=False,
    )
    cv2.destroyAllWindows()
    rx, ry, rw, rh = roi
    if rw > 0 and rh > 0:
        # Ri-scala al coordinate originali
        region = {
            "left":   int(rx / scale_vis),
            "top":    int(ry / scale_vis),
            "width":  int(rw / scale_vis),
            "height": int(rh / scale_vis),
        }
        key = ord('s')  # procedi al salvataggio
    else:
        print("Selezione annullata.")
        key = ord('q')

# ─── SALVA CONFIG ────────────────────────────────────────────────────────────
if key == ord('s'):
    cfg: dict = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg.update({
        "skill_region_left":   region["left"],
        "skill_region_top":    region["top"],
        "skill_region_width":  region["width"],
        "skill_region_height": region["height"],
    })
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSalvato in config.json:")
    print(f'  "skill_region_left":   {region["left"]}')
    print(f'  "skill_region_top":    {region["top"]}')
    print(f'  "skill_region_width":  {region["width"]}')
    print(f'  "skill_region_height": {region["height"]}')
    print("\nRiavvia l'app per applicare le nuove coordinate.")
else:
    print("Nessuna modifica salvata.")

input("\nPremi INVIO per chiudere.")
