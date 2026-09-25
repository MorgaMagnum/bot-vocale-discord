<p align="center">
  <img src="immagini/LOGO/Project_TL_logo.png" alt="Throne and Liberty" width="480">
</p>

# Devotion Bot — Throne and Liberty

<p align="center"><b>⚡ Creato da PaoloBrosio ⚡</b></p>

Bot vocale per **Throne and Liberty** che avvisa il gruppo su Discord quando la skill **Devotion** viene attivata, quando sta per scadere e quando termina.

Il bot passa il tuo microfono su un cavo audio virtuale (VB-Audio **CABLE**) e ci mescola sopra gli avvisi audio. Su Discord selezioni `CABLE Output` come microfono: i compagni sentono la tua voce e gli avvisi, senza usare un bot Discord separato.

---

## Come funziona

```
Microfono ──► monitor.py ──► CABLE Input ──► (Discord: microfono = CABLE Output)
                  ▲
                  │ avvisi audio (tracce audio/*.wav)
                  │
   Rilevamento attivazione (tasto oppure analisi schermo)
```

1. **Passthrough del microfono**: `monitor.py` inoltra in continuo il microfono verso `CABLE Input`.
2. **Rilevamento dell'attivazione**: due modalità, da scegliere in `config.json` → `detection_mode`:
   - `keyboard` (consigliata): alla pressione del tasto configurato (`keyboard_key`, default `t`) il bot considera la skill attivata. La risposta è immediata e non serve catturare lo schermo.
   - `visual`: il bot cattura una piccola regione dello schermo attorno all'icona della skill e riconosce lo stato *attiva* con due metodi:
     - **colore HSV** (metodo principale): cerca il bordo rosa/magenta che compare solo mentre il buff è attivo. Il bordo deve essere visibile su almeno 2 lati, così le animazioni di transizione non generano falsi positivi;
     - **template matching** (metodo di riserva): confronta la regione con i template in `immagini/on/`.

     Per evitare falsi allarmi il bot riconosce anche lo stato *inutilizzabile* (per esempio in acqua) tramite `immagini/inutilizzabile/`. Quando la skill torna utilizzabile, ignora i segnali per qualche secondo.
3. **Timer**: dopo l'attivazione, gli avvisi seguono solo il timer:

   | Momento | Avviso |
   |---|---|
   | T + 0 s | `devotion on.wav` |
   | T + (durata − 5) s | `devotion off in 5.wav` |
   | T + durata | `devotion off.wav` |
   | T + durata + cooldown | torna in ascolto |

   Nelle cuffie senti anche un beep di conferma (ON 880 Hz, avviso 660 Hz, OFF 440 Hz), che non passa su CABLE.

---

## Requisiti

- Windows con Python 3.11+
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)
- Dipendenze Python:

```bash
pip install -r requirements.txt
pip install pynput          # necessario per la modalità "keyboard" e per il tasto di reset
```

## Avvio

Fai doppio clic su **`avvia.bat`**, oppure esegui:

```bash
python app.py
```

Si apre l'interfaccia grafica (`app.py`), da cui puoi:
- scegliere il microfono, l'uscita (CABLE Input) e il metodo di rilevamento;
- modificare i timer (durata, preavviso, cooldown) e salvarli in `config.json`;
- avviare, fermare o resettare il monitor e vedere lo stato della skill e il log;
- spostare o ridimensionare la regione catturata con le frecce;
- lanciare gli strumenti di calibrazione e diagnosi.

Infine, **in Discord** imposta il dispositivo di input su `CABLE Output (VB-Audio Virtual Cable)`.

> Dopo aver cambiato il metodo di rilevamento o i timer, salva e riavvia il monitor.

---

## Configurazione (`config.json`)

| Chiave | Descrizione |
|---|---|
| `mic_device` | Nome del microfono reale |
| `output_device` | Uscita audio (di solito `CABLE Input (VB-Audio Virtual Cable)`) |
| `detection_mode` | `keyboard` oppure `visual` |
| `keyboard_key` | Tasto che segnala l'attivazione della skill |
| `reset_key` | Tasto per tornare subito in ascolto |
| `beep_enabled` / `beep_duration` | Beep di conferma in cuffia |
| `skill_region_left/top/width/height` | Regione dello schermo da analizzare (modalità visual) |
| `on_threshold` / `match_threshold` | Soglie del template matching |
| `confirm_frames` | Frame consecutivi necessari per confermare l'attivazione |
| `devotion_duration` | Durata della skill in secondi |
| `warning_before` | Secondi di preavviso prima della fine |
| `cooldown_min` | Cooldown prima di tornare in ascolto |
| `check_interval` | Intervallo tra due catture dello schermo |

---

## Calibrazione (solo modalità `visual`)

| Script | Uso |
|---|---|
| `calibra_da_calibrazione.py` | **Consigliato**: ricava regione e template dagli screenshot in `immagini di calibrazione/` |
| `calibra_auto.py` | Calibrazione automatica da screenshot |
| `ricalibra_template.py` | Cattura guidata dei template dal gioco (3 passi) |
| `cattura_rapida.py` | Cattura rapida dei template con i tasti 1/2/3 (4 = inutilizzabile) |
| `estrai_inutilizzabile.py` | Estrae il template dello stato "skill inutilizzabile" |
| `calibrate.py` | Selezione manuale della regione dello schermo |
| `diagnosi.py` | Vista live di ciò che vede il bot (pixel rosa, lati, punteggi). Tasti: `Q` esci, `+`/`−` soglia, `S` salva |

---

## Struttura del progetto

```
app.py                     GUI (tkinter) che avvia monitor.py
monitor.py                 Motore: passthrough mic, rilevamento, timer, avvisi
bot.py                     Variante alternativa con bot Discord (discord.py, vedi SETUP.txt)
config.json                Configurazione
immagini/                  Template per il riconoscimento
  on/                      Template della skill ATTIVA (i file _bak_* vengono ignorati)
  inutilizzabile/          Template della skill non utilizzabile
immagini di calibrazione/  Screenshot del gioco usati per la calibrazione
tracce audio/              Avvisi audio (.wav)
```

## Variante con bot Discord

`bot.py` è una versione alternativa che entra in un canale vocale come bot Discord e riproduce lì gli avvisi. Richiede `discord.py`, `ffmpeg` e un token. Le istruzioni sono in [`SETUP.txt`](SETUP.txt). **Non committare mai il token:** mettilo in `config.json` sotto `discord_token` solo in locale.

---

## Autore

Ideato e sviluppato da **PaoloBrosio** © 2026.

> Progetto amatoriale non ufficiale, non affiliato con NCSOFT o Amazon Games. *Throne and Liberty* e il relativo logo sono marchi dei rispettivi proprietari.
