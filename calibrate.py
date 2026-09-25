#!/usr/bin/env python3
# Autore: PaoloBrosio — © 2026 PaoloBrosio
"""
calibrate.py — Trova le coordinate dello schermo per SKILL_REGION in bot.py

Come usarlo:
  1. Apri Throne and Liberty e vai in game con la hotbar visibile
  2. Esegui:  python calibrate.py
  3. Premi INVIO per catturare lo schermo
  4. Nella finestra che si apre, trascina un rettangolo attorno all'icona Devotion
  5. Premi INVIO o SPAZIO per confermare la selezione
  6. Copia le coordinate stampate in console dentro bot.py
"""

import cv2
import numpy as np
import mss
from pathlib import Path

BASE_DIR   = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "immagini"

def main():
    print("=" * 55)
    print("  Calibrazione SKILL_REGION per Devotion Bot")
    print("=" * 55)
    print()
    print("Assicurati che il gioco sia visibile sullo schermo.")
    input("Premi INVIO per catturare lo schermo...")

    with mss.mss() as sct:
        monitor = sct.monitors[1]  # monitor principale
        shot    = sct.grab(monitor)
        full    = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

    print()
    print("Si apre una finestra con lo screenshot.")
    print("Trascina un rettangolo attorno all'ICONA DEVOTION nella hotbar.")
    print("Poi premi INVIO o SPAZIO per confermare.")
    print()

    roi = cv2.selectROI(
        "Seleziona icona Devotion — INVIO per confermare, C per annullare",
        full,
        showCrosshair=True,
        fromCenter=False,
    )
    cv2.destroyAllWindows()

    x, y, w, h = roi
    if w == 0 or h == 0:
        print("Selezione annullata.")
        return

    print()
    print("=" * 55)
    print("  Copia questo blocco in bot.py:")
    print("=" * 55)
    print(f"""
SKILL_REGION = {{
    "left":   {x},
    "top":    {y},
    "width":  {w},
    "height": {h},
}}
""")

    # Salva un'anteprima della regione selezionata
    preview = full[y:y+h, x:x+w]
    preview_path = BASE_DIR / "preview_regione.png"
    cv2.imwrite(str(preview_path), preview)
    print(f"Anteprima della regione salvata in: {preview_path}")
    print("Verificala per assicurarti di aver selezionato l'icona corretta.")

    # Confronto con i template
    print()
    print("Confronto con i template esistenti...")
    from bot import TEMPLATES, MATCH_THRESHOLD, score_template

    for state, tmpl in TEMPLATES.items():
        s = score_template(preview, tmpl)
        match = "OK" if s >= MATCH_THRESHOLD else "basso"
        print(f"  [{state}] score={s:.3f}  ({match})")

    print()
    print("Se tutti gli score sono bassi, prova ad allargare la selezione")
    print("o abbassare MATCH_THRESHOLD in bot.py (minimo consigliato: 0.50).")


if __name__ == "__main__":
    main()
