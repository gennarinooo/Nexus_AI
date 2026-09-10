# Nexus AI

## Avvio

Imposta la chiave Gemini senza inserirla nei file del progetto:

```bash
export GEMINI_API_KEY="la-tua-chiave"
python nexus.py
```

## Pubblicazione su Streamlit

Installa le dipendenze e avvia l'app Streamlit:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Su Streamlit Cloud, apri **Settings > Secrets** e inserisci:

```toml
GEMINI_API_KEY = "la-tua-chiave-gemini"
```

L'app Streamlit legge automaticamente questo secret. Dopo l'accesso, la chat è
disponibile direttamente nella pagina principale; il pulsante `+` nella barra di
scrittura permette di allegare immagini e file. Nexus riceve automaticamente
l'ora italiana corrente.

L'accesso ospite salva un identificatore casuale nel browser. Lo stesso dispositivo
riutilizza quell'ID, così le conversazioni restano separate da quelle degli altri utenti.