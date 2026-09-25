#!/usr/bin/env python3
"""
diagnosi.py — Visualizzazione live del riconoscimento skill Devotion

Mostra in tempo reale:
  - Cosa sta catturando il bot nella regione configurata
  - Quanti pixel rosa/magenta rileva nel bordo (metodo primario)
  - Il punteggio del template matching per ogni template (metodo backup)
  - La decisione finale: ATTIVA / non attiva

Usa: tieni aperto mentre il gioco è in esecuzione e attiva/disattiva la skill
     per vedere come reagiscono i valori. Se la skill è attiva ma i valori
     non salgono → regola PINK_PIXEL_THRESHOLD o la regione in config.json.

Tasti:
  Q = esci
  + = aumenta soglia rosa (+5)
  - = diminuisce soglia rosa (-5)
  S = salva soglia corrente in config.json
"""

import cv2
import numpy as np
import mss
import json
from pathlib import Path
import time

BASE_DIR    = Path(__file__).parent
IMAGES_DIR  = BASE_DIR / "immagini"
CONFIG_FILE = BASE_DIR / "config.json"

# ─── LEGGI CONFIG ─────────────────────────────────────────────────────────────
cfg = {}
if CONFIG_FILE.exists():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

SKILL_REGION = {
    "left":   int(cfg.get("skill_region_left",   1820)),
    "top":    int(cfg.get("skill_region_top",    1000)),
    "width":  int(cfg.get("skill_region_width",    72)),
    "height": int(cfg.get("skill_region_height",   72)),
}
PINK_THRESHOLD = int(cfg.get("pink_pixel_threshold", 25))
ON_THRESHOLD   = float(cfg.get("on_threshold", 0.65))

# ─── PARAMETRI COLORE ROSA ────────────────────────────────────────────────────
PINK_LOWER = np.array([130,  80, 100], dtype=np.uint8)
PINK_UPPER = np.array([175, 255, 255], dtype=np.uint8)
MIN_SIDES  = int(cfg.get("min_sides_with_pink", 2))
UNUSABLE_THRESHOLD = float(cfg.get("unusable_threshold", 0.55))

# ─── CARICA TEMPLATE ─────────────────────────────────────────────────────────
def load_templates(folder, prefix=""):
    templates = []
    d = IMAGES_DIR / folder
    if d.exists():
        for p in sorted(d.glob("*.png")):
            if p.name.startswith("_bak_"):
                continue
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                templates.append((p.name, img))
    return templates

TEMPLATES          = load_templates("on")
UNUSABLE_TEMPLATES = load_templates("inutilizzabile")

if not TEMPLATES:
    fb = IMAGES_DIR / "devotion skill on dettaglio.png"
    img = cv2.imread(str(fb), cv2.IMREAD_GRAYSCALE)
    if img is not None:
        TEMPLATES.append((fb.name, img))

print(f"Template ON caricati: {len(TEMPLATES)}")
for name, _ in TEMPLATES:
    print(f"  {name}")
print(f"Template INUTILIZZABILE caricati: {len(UNUSABLE_TEMPLATES)}")
for name, _ in UNUSABLE_TEMPLATES:
    print(f"  {name}")
print()
print(f"Regione: left={SKILL_REGION['left']} top={SKILL_REGION['top']} "
      f"w={SKILL_REGION['width']} h={SKILL_REGION['height']}")
print(f"Soglia rosa: {PINK_THRESHOLD}px su >={MIN_SIDES}/4 lati   Soglia template: {ON_THRESHOLD:.2f}")
print()
print("Q=esci  +=soglia rosa+5  -=soglia rosa-5  S=salva soglia")
print()

ZOOM = 6   # zoom per la preview dell'icona

def capture():
    with mss.MSS() as sct:
        raw = sct.grab(SKILL_REGION)
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)

def count_pink_border(frame):
    hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, PINK_LOWER, PINK_UPPER)
    H, W = frame.shape[:2]
    b = max(4, min(W, H) // 5)
    min_per_side = max(3, b * 2)
    border = np.zeros_like(mask)
    border[:b, :]  = 255
    border[-b:, :] = 255
    border[:, :b]  = 255
    border[:, -b:] = 255
    strips = [mask[:b, :], mask[-b:, :], mask[:, :b], mask[:, -b:]]
    total  = 0
    sides  = 0
    for s in strips:
        c = int(np.count_nonzero(s))
        total += c
        if c >= min_per_side:
            sides += 1
    return total, sides, mask, border

def best_template_score(frame, tmpl_list):
    if not tmpl_list:
        return 0.0, "—"
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best_s, best_n = 0.0, "—"
    for name, tmpl in tmpl_list:
        th, tw = tmpl.shape[:2]
        res = cv2.resize(gray, (tw, th))
        s = float(cv2.matchTemplate(res, tmpl, cv2.TM_CCOEFF_NORMED).max())
        if s > best_s:
            best_s, best_n = s, name
    return best_s, best_n

# ─── PANEL DI DIAGNOSTICA ─────────────────────────────────────────────────────
PANEL_W = 520
PANEL_H = 340

BG     = (20,  20,  20)
WHITE  = (220, 220, 220)
GREEN  = (60,  200,  60)
RED    = (60,   60, 220)
YELLOW = (60,  200, 200)
PINK   = (180,  80, 220)

def make_panel(frame, pink_total, pink_sides, pink_mask, border_mask,
               tmpl_score, tmpl_name, unusable_score, threshold):
    panel = np.full((PANEL_H, PANEL_W, 3), BG, dtype=np.uint8)

    hsv_ok     = pink_total >= threshold and pink_sides >= MIN_SIDES
    tmpl_ok    = tmpl_score >= ON_THRESHOLD
    unusable   = unusable_score >= UNUSABLE_THRESHOLD
    is_active  = (hsv_ok or tmpl_ok) and not unusable

    # ── Titolo ────────────────────────────────────────────────────────────────
    if unusable:
        color_title, label = (60, 60, 220), "INUTILIZZABILE"
    elif is_active:
        color_title, label = GREEN, "ATTIVA"
    else:
        color_title, label = RED, "non attiva"
    cv2.putText(panel, f"SKILL: {label}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color_title, 2, cv2.LINE_AA)

    # ── Preview icona (zoom) ──────────────────────────────────────────────────
    icon_big = cv2.resize(frame, None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
    ih, iw = min(icon_big.shape[0], PANEL_H - 10), min(icon_big.shape[1], 160)
    panel[50:50+ih, 10:10+iw] = icon_big[:ih, :iw]
    cv2.putText(panel, "Cattura live", (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, WHITE, 1, cv2.LINE_AA)

    # ── Maschera rosa (zoom) ──────────────────────────────────────────────────
    pink_vis = cv2.cvtColor(pink_mask & border_mask, cv2.COLOR_GRAY2BGR)
    pink_vis[pink_mask > 0] = (220, 80, 220)
    pink_big = cv2.resize(pink_vis, None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
    px = 180
    ph, pw = min(pink_big.shape[0], PANEL_H - 55), min(pink_big.shape[1], 160)
    panel[50:50+ph, px:px+pw] = pink_big[:ph, :pw]
    cv2.putText(panel, "Bordo rosa", (px, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, PINK, 1, cv2.LINE_AA)

    # ── Dati numerici ─────────────────────────────────────────────────────────
    tx = 360
    lines = [
        (f"Pixel rosa bordo: {pink_total:4d}", PINK if hsv_ok else WHITE),
        (f"Lati con rosa:    {pink_sides}/4  (min {MIN_SIDES})", GREEN if pink_sides >= MIN_SIDES else WHITE),
        (f"Soglia rosa px:   {threshold}  (+/-)", YELLOW),
        ("", WHITE),
        (f"Template score:   {tmpl_score:.3f}", GREEN if tmpl_ok else WHITE),
        (f"Soglia template:  {ON_THRESHOLD:.2f}", YELLOW),
        (f"Best template:    {tmpl_name[:18]}", WHITE),
        ("", WHITE),
        (f"INUTILIZZ score:  {unusable_score:.3f}", (60, 60, 220) if unusable else WHITE),
        (f"Soglia inutiliz:  {UNUSABLE_THRESHOLD:.2f}", YELLOW),
        ("", WHITE),
        ("Attivazione:", WHITE),
        (f"  HSV:      {'SI <--' if hsv_ok else 'no'}", GREEN if hsv_ok else WHITE),
        (f"  Template: {'SI <--' if tmpl_ok else 'no'}", GREEN if tmpl_ok else WHITE),
        (f"  Bloccato: {'SI (inutiliz)' if unusable else 'no'}", (60, 60, 220) if unusable else WHITE),
    ]
    y = 48
    for text, col in lines:
        cv2.putText(panel, text, (tx, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.37, col, 1, cv2.LINE_AA)
        y += 19

    # ── Barra pixel rosa ─────────────────────────────────────────────────────
    bx, by, bw, bh = 10, PANEL_H - 55, 330, 18
    cv2.rectangle(panel, (bx, by), (bx + bw, by + bh), (50, 50, 50), -1)
    fill = min(bw, int(bw * pink_total / max(threshold * 3, 1)))
    bar_col = GREEN if hsv_ok else (100, 100, 200)
    cv2.rectangle(panel, (bx, by), (bx + fill, by + bh), bar_col, -1)
    cv2.rectangle(panel, (bx, by), (bx + bw, by + bh), WHITE, 1)
    thr_x = bx + int(bw * threshold / max(threshold * 3, 1))
    cv2.line(panel, (thr_x, by - 4), (thr_x, by + bh + 4), YELLOW, 2)
    cv2.putText(panel, f"Pixel rosa: {pink_total}  lati: {pink_sides}/4  (soglia: >={threshold}px su >={MIN_SIDES} lati)",
                (bx, by - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.35, WHITE, 1, cv2.LINE_AA)

    cv2.putText(panel, "Q=esci  +=soglia+5  -=soglia-5  S=salva",
                (10, PANEL_H - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 120), 1, cv2.LINE_AA)

    return panel

# ─── LOOP PRINCIPALE ──────────────────────────────────────────────────────────
fps_t = time.monotonic()
fps_n = 0

while True:
    frame = capture()
    pink_total, pink_sides, pink_mask, border_mask = count_pink_border(frame)
    tmpl_score, tmpl_name   = best_template_score(frame, TEMPLATES)
    unusable_score, _       = best_template_score(frame, UNUSABLE_TEMPLATES)

    panel = make_panel(frame, pink_total, pink_sides, pink_mask, border_mask,
                       tmpl_score, tmpl_name, unusable_score, PINK_THRESHOLD)

    fps_n += 1
    now = time.monotonic()
    if now - fps_t >= 1.0:
        fps = fps_n / (now - fps_t)
        fps_n = 0
        fps_t = now
        cv2.putText(panel, f"{fps:.0f} fps", (PANEL_W - 60, PANEL_H - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (80, 80, 80), 1)

    cv2.imshow("Diagnosi Devotion Bot — Q=esci", panel)
    key = cv2.waitKey(30) & 0xFF

    if key == ord('q'):
        break
    elif key == ord('+') or key == ord('='):
        PINK_THRESHOLD += 5
        print(f"Soglia rosa → {PINK_THRESHOLD}px")
    elif key == ord('-') or key == ord('_'):
        PINK_THRESHOLD = max(5, PINK_THRESHOLD - 5)
        print(f"Soglia rosa → {PINK_THRESHOLD}px")
    elif key == ord('s'):
        cfg2 = {}
        if CONFIG_FILE.exists():
            try:
                cfg2 = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        cfg2["pink_pixel_threshold"] = PINK_THRESHOLD
        CONFIG_FILE.write_text(json.dumps(cfg2, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Salvato: pink_pixel_threshold = {PINK_THRESHOLD}")

cv2.destroyAllWindows()
print("Chiuso.")
