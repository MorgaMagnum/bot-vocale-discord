#!/usr/bin/env python3
# Autore: PaoloBrosio — © 2026 PaoloBrosio
"""
calibra_da_calibrazione.py — Estrae coordinate e template della skill Devotion
                              direttamente dalle immagini di calibrazione salvate.

Usa le due immagini in 'immagini di calibrazione/':
  - immagine di calibrazione devotion.png       (skill OFF)
  - Immagine di calibrazione devotion on.png    (skill ON)

Come funziona:
  1. Mostra entrambe le immagini con la regione attuale evidenziata
  2. Premi S per usare la regione attuale, M per selezionarne una nuova
  3. Estrae i template ON e OFF dalla stessa regione in entrambe le immagini
  4. Salva il template ON in immagini/on/ e aggiorna config.json
"""

import cv2
import numpy as np
import json
import shutil
from pathlib import Path
from datetime import datetime

BASE_DIR    = Path(__file__).parent
IMAGES_DIR  = BASE_DIR / "immagini"
ON_DIR      = IMAGES_DIR / "on"
CALIB_DIR   = BASE_DIR / "immagini di calibrazione"
CONFIG_FILE = BASE_DIR / "config.json"

CALIB_OFF_NAME = "immagine di calibrazione devotion.png"
CALIB_ON_NAME  = "Immagine di calibrazione devotion on.png"

print("=" * 62)
print("  Calibrazione da Immagini — Devotion Bot")
print("=" * 62)

# ─── CARICA IMMAGINI ─────────────────────────────────────────────────────────
img_off = cv2.imread(str(CALIB_DIR / CALIB_OFF_NAME))
img_on  = cv2.imread(str(CALIB_DIR / CALIB_ON_NAME))

if img_off is None:
    print(f"\nERRORE: non trovo '{CALIB_OFF_NAME}'")
    print(f"  Cartella cercata: {CALIB_DIR}")
    input("Premi INVIO per uscire.")
    raise SystemExit
if img_on is None:
    print(f"\nERRORE: non trovo '{CALIB_ON_NAME}'")
    print(f"  Cartella cercata: {CALIB_DIR}")
    input("Premi INVIO per uscire.")
    raise SystemExit

H_off, W_off = img_off.shape[:2]
H_on,  W_on  = img_on.shape[:2]
print(f"\nImmagine OFF: {W_off}x{H_off}")
print(f"Immagine ON : {W_on}x{H_on}")

# ─── LEGGI REGIONE ATTUALE DA CONFIG ────────────────────────────────────────
cfg: dict = {}
if CONFIG_FILE.exists():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

ox = int(cfg.get("skill_region_left",   1820))
oy = int(cfg.get("skill_region_top",    1000))
ow = int(cfg.get("skill_region_width",   72))
oh = int(cfg.get("skill_region_height",  72))

print(f"\nRegione attuale in config.json:")
print(f"  left={ox}  top={oy}  width={ow}  height={oh}")

# ─── SCALA PER VISUALIZZAZIONE ───────────────────────────────────────────────
scale = min(1.0, 1280 / W_off, 720 / H_off)

def to_vis(img):
    return cv2.resize(img.copy(), (int(img.shape[1] * scale), int(img.shape[0] * scale)))

def draw_region_on_vis(vis, lx, ly, lw, lh, sc):
    vx = int(lx * sc)
    vy = int(ly * sc)
    vw = int(lw * sc)
    vh = int(lh * sc)
    cv2.rectangle(vis, (vx, vy), (vx + vw, vy + vh), (0, 255, 255), 2)
    cv2.putText(vis, "Devotion", (vx, max(vy - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)

vis_off = to_vis(img_off)
vis_on  = to_vis(img_on)

cv2.putText(vis_off, "DEVOTION OFF", (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 200, 255), 2, cv2.LINE_AA)
cv2.putText(vis_on, "DEVOTION ON", (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 80), 2, cv2.LINE_AA)

draw_region_on_vis(vis_off, ox, oy, ow, oh, scale)
draw_region_on_vis(vis_on,  ox, oy, ow, oh, scale)

# ─── ANTEPRIMA REGIONE ATTUALE ───────────────────────────────────────────────
def safe_crop(img, x, y, w, h):
    H, W = img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + w), min(H, y + h)
    if x2 <= x1 or y2 <= y1:
        return np.zeros((h, w, 3), dtype=np.uint8)
    return img[y1:y2, x1:x2].copy()

def zoom_labeled(img, label, zoom):
    if img.size == 0:
        img = np.zeros((10, 10, 3), dtype=np.uint8)
    big = cv2.resize(img, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((big.shape[0] + 24, max(big.shape[1], 80), 3), dtype=np.uint8)
    canvas[:big.shape[0], :big.shape[1]] = big
    cv2.putText(canvas, label, (4, big.shape[0] + 17),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)
    return canvas

crop_off = safe_crop(img_off, ox, oy, ow, oh)
crop_on  = safe_crop(img_on,  ox, oy, ow, oh)

ZOOM = max(2, min(8, 280 // max(ow, oh, 1)))

z_off = zoom_labeled(crop_off, "OFF (attuale)", ZOOM)
z_on  = zoom_labeled(crop_on,  "ON  (attuale)", ZOOM)

# Aggiusta altezze per hstack
max_h = max(z_off.shape[0], z_on.shape[0])
def pad_h(img, target_h):
    if img.shape[0] < target_h:
        pad = np.zeros((target_h - img.shape[0], img.shape[1], 3), dtype=np.uint8)
        return np.vstack([img, pad])
    return img

preview = np.hstack([pad_h(z_off, max_h), pad_h(z_on, max_h)])

print()
print("Si aprono 3 finestre:")
print("  1. Anteprima della regione attuale (OFF vs ON)")
print("  2. Screenshot OFF — riquadro giallo = regione attuale")
print("  3. Screenshot ON  — riferimento visivo")
print()
print("  S = usa regione ATTUALE e salva")
print("  M = seleziona regione MANUALMENTE")
print("  Q = esci senza modifiche")

cv2.imshow("Anteprima regione attuale (OFF vs ON)", preview)
cv2.imshow("Screenshot OFF — S=usa attuale  M=manuale  Q=esci", vis_off)
cv2.imshow("Screenshot ON  (riferimento visivo)", vis_on)
cv2.moveWindow("Anteprima regione attuale (OFF vs ON)", 0, 0)

key = cv2.waitKey(0) & 0xFF
cv2.destroyAllWindows()

if key == ord('q'):
    print("\nUscito senza modifiche.")
    input("Premi INVIO per chiudere.")
    raise SystemExit

# ─── SELEZIONE MANUALE ───────────────────────────────────────────────────────
if key == ord('m'):
    print("\nSelezione manuale:")
    print("Trascina un rettangolo attorno all'icona Devotion nell'immagine OFF.")
    print("INVIO o SPAZIO = conferma  |  C = annulla")
    print()

    roi = cv2.selectROI(
        "Seleziona icona Devotion (OFF) — INVIO=conferma  C=annulla",
        vis_off, showCrosshair=True, fromCenter=False,
    )
    cv2.destroyAllWindows()

    rx, ry, rw, rh = roi
    if rw == 0 or rh == 0:
        print("Selezione annullata.")
        input("Premi INVIO per chiudere.")
        raise SystemExit

    # Converti a coordinate originali (full resolution)
    ox = max(0, int(rx / scale))
    oy = max(0, int(ry / scale))
    ow = max(4, int(rw / scale))
    oh = max(4, int(rh / scale))
    print(f"Nuova regione: left={ox}  top={oy}  width={ow}  height={oh}")

# ─── ESTRAI TEMPLATE DALLA REGIONE ───────────────────────────────────────────
tmpl_off = safe_crop(img_off, ox, oy, ow, oh)
tmpl_on  = safe_crop(img_on,  ox, oy, ow, oh)

# Riepilogo finale
ZOOM2 = max(2, min(8, 280 // max(ow, oh, 1)))
z2_off = zoom_labeled(tmpl_off, "OFF", ZOOM2)
z2_on  = zoom_labeled(tmpl_on,  "ON",  ZOOM2)
max_h2 = max(z2_off.shape[0], z2_on.shape[0])
final_preview = np.hstack([pad_h(z2_off, max_h2), pad_h(z2_on, max_h2)])

print()
print("Riepilogo template estratti.")
print("  S = SALVA template e aggiorna config.json")
print("  Q = ANNULLA")

cv2.imshow("Template estratti — S=Salva  Q=Annulla", final_preview)
key2 = cv2.waitKey(0) & 0xFF
cv2.destroyAllWindows()

if key2 != ord('s'):
    print("Annullato senza salvare.")
    input("Premi INVIO per chiudere.")
    raise SystemExit

# ─── SALVA TEMPLATE ──────────────────────────────────────────────────────────
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
ON_DIR.mkdir(exist_ok=True)

# Template ON in grayscale per monitor.py (cartella on/)
tmpl_on_gray = cv2.cvtColor(tmpl_on, cv2.COLOR_BGR2GRAY)
on_path = ON_DIR / "devotion_calibrazione.png"
cv2.imwrite(str(on_path), tmpl_on_gray)
print(f"\n  Salvato: immagini/on/devotion_calibrazione.png  ({tmpl_on_gray.shape[1]}x{tmpl_on_gray.shape[0]} px, grayscale)")

# Rimuovi eventuali vecchi template ON dalla cartella on/ (rimpiazza tutto con quello nuovo)
for old in ON_DIR.glob("*.png"):
    if old.name != "devotion_calibrazione.png":
        old.rename(ON_DIR / f"_bak_{ts}_{old.name}")

# Fallback colore per bot.py
fallback_on = IMAGES_DIR / "devotion skill on dettaglio.png"
if fallback_on.exists():
    shutil.copy(fallback_on, IMAGES_DIR / f"devotion skill on dettaglio_bak_{ts}.png")
cv2.imwrite(str(fallback_on), tmpl_on)
print(f"  Salvato: immagini/devotion skill on dettaglio.png  (colore, fallback)")

# ─── AGGIORNA CONFIG.JSON ─────────────────────────────────────────────────────
cfg.update({
    "skill_region_left":   ox,
    "skill_region_top":    oy,
    "skill_region_width":  ow,
    "skill_region_height": oh,
    "on_threshold":        0.70,
    "confirm_frames":      2,
})
CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"\nconfig.json aggiornato:")
print(f"  skill_region : left={ox}, top={oy}, width={ow}, height={oh}")
print(f"  on_threshold : 0.70  (era {cfg.get('on_threshold', '?')})")
print(f"  confirm_frames: 2   (audio piu' rapido: ~0.15s dal rilevamento)")
print()
print("Riavvia il monitor per applicare le modifiche.")
input("\nPremi INVIO per chiudere.")
