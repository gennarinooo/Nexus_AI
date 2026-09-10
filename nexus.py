import io
import os
import random
import re
import sqlite3
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image
from flask import Flask, jsonify, render_template, request, session
from google import genai

app = Flask(__name__)
app.secret_key = 'nexus_secret_key_sicreta'

# Il segreto resta fuori dal repository. Impostare GEMINI_API_KEY nell'ambiente.
client = None
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOADS = {
    'image/jpeg', 'image/png', 'image/webp', 'image/gif',
    'application/pdf', 'text/plain',
}


def get_client():
    global client
    if client is None:
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            try:
                import streamlit as st

                api_key = st.secrets.get('GEMINI_API_KEY')
            except (ImportError, FileNotFoundError, KeyError):
                api_key = None
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY non configurata')
        client = genai.Client(api_key=api_key)
    return client


# --- DATABASE ---
def inizializza_db():
    conn = sqlite3.connect('nexus_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utenti (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            ruolo TEXT,
            messaggio TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()


inizializza_db()


def ora_italiana():
    return datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m-%d %H:%M:%S')


def aggiorna_file_archivio():
    """Aggiorna automaticamente il file di testo nel Codespace con tutte le chat divise per utente o ID ospite."""
    conn = sqlite3.connect('nexus_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT username FROM chat_history ORDER BY timestamp DESC')
    utenti = [row[0] for row in cursor.fetchall()]

    with open('archivio_conversazioni.txt', 'w', encoding='utf-8') as f:
        f.write("=== ARCHIVIO GENERALE CONVERSAZIONI NEXUS ===\n\n")
        for user in utenti:
            f.write(f"--------------------------------------------------\n")
            f.write(f"UTENTE / DISPOSITIVO ID: {user}\n")
            f.write(f"--------------------------------------------------\n")

            cursor.execute('SELECT timestamp, ruolo, messaggio FROM chat_history WHERE username = ? ORDER BY id ASC', (user,))
            logs = cursor.fetchall()
            for log in logs:
                f.write(f"[{log[0]}] {log[1]}: {log[2]}\n")
            f.write("\n\n")

    conn.close()


def salva_messaggio(username, ruolo, messaggio):
    if str(username).startswith('Ospite_'):
        return

    conn = sqlite3.connect('nexus_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO chat_history (username, ruolo, messaggio, timestamp)'
        ' VALUES (?, ?, ?, ?)',
        (username, ruolo, messaggio, ora_italiana()),
    )
    conn.commit()
    conn.close()

    # Aggiorna in automatico il file di testo nel Codespace
    aggiorna_file_archivio()


# --- MOTORE IMMAGINI ---
def traduci_e_ottimizza_prompt(prompt_utente):
    try:
        istruzione = (
            'Sei un ottimizzatore di prompt fotografici per AI. Converti la'
            ' richiesta in un prompt dettagliato in inglese (high quality, 8k,'
            ' detailed). Restituisci SOLO il testo del prompt in inglese.'
        )
        response = get_client().models.generate_content(
            model='gemini-3.6-flash',
            contents=f'{istruzione}\n\nRichiesta utente: {prompt_utente}',
        )
        if response and response.text:
            return response.text.strip()
    except Exception:
        pass
    return prompt_utente


def genera_immagine(prompt_testo):
    try:
        prompt_inglese = traduci_e_ottimizza_prompt(prompt_testo)
        seed_random = random.randint(1, 999999)
        prompt_encoded = urllib.parse.quote(prompt_inglese)
        url = f'https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=1024&seed={seed_random}&nologo=true'

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            image_bytes = response.read()

        os.makedirs('static', exist_ok=True)
        nome_file = f'static/immagine_nexus_{int(datetime.now().timestamp())}.png'
        with open(nome_file, 'wb') as f:
            f.write(image_bytes)

        return (
            f'/{nome_file}',
            'Immagine HD generata con successo e salvata in locale!',
        )
    except Exception:
        return None, 'Non riesco a generare l\'immagine in questo momento.'


def normalizza_id_dispositivo(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        return None
    return value.upper()


def e_richiesta_immagine(testo):
    testo = re.sub(r"[’‘`´]", "'", testo.lower())
    testo = re.sub(r'[^a-zàèéìòù0-9\s\']', ' ', testo)
    testo = re.sub(r'\s+', ' ', testo).strip()
    parole_chiave = {
        'genera immagine', 'genera un immagine', "genera un'immagine",
        'generami un immagine', "generami un'immagine", 'crea immagine',
        'crea un immagine', "crea un'immagine", 'creami un immagine',
        "creami un'immagine", 'crea foto', 'crea una foto', 'genera foto',
        'genera una foto', 'disegna', 'disegnami', 'illustra', 'illustrami',
        'realizza immagine', 'realizza una immagine', 'fammi vedere una immagine',
        'fammi un immagine', "fammi un'immagine", 'produci immagine',
        'crea artwork', 'genera artwork', 'genera un disegno',
        'crea un disegno', 'crea un illustrazione', "crea un'illustrazione",
        'genera un illustrazione', "genera un'illustrazione", 'image generation',
        'generate image', 'create image', 'draw an image', 'make an image',
        'generate a picture', 'create a picture', 'text to image',
    }
    return any(chiave in testo for chiave in parole_chiave)


def leggi_allegato(file):
    if not file or not file.filename:
        return None
    if file.mimetype not in ALLOWED_UPLOADS:
        raise ValueError('Formato allegato non supportato')
    contenuto = file.read(MAX_UPLOAD_BYTES + 1)
    if len(contenuto) > MAX_UPLOAD_BYTES:
        raise ValueError('L\'allegato supera il limite di 10 MB')
    return genai.types.Part.from_bytes(data=contenuto, mime_type=file.mimetype)


# --- ROTTE WEB ---
@app.route('/')
def index():
    if 'utente' not in session:
        return render_template('login.html')
    return render_template('chat.html', username=session['utente'])


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user = data.get('username')
    pwd = data.get('password')

    conn = sqlite3.connect('nexus_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM utenti WHERE username = ? AND password = ?', (user, pwd)
    )
    if cursor.fetchone():
        session['utente'] = user
        conn.close()
        return jsonify({'success': True})
    conn.close()
    return jsonify({'success': False, 'error': 'Credenziali errate'})


@app.route('/registra', methods=['POST'])
def registra():
    data = request.json
    user = data.get('username')
    pwd = data.get('password')

    conn = sqlite3.connect('nexus_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO utenti (username, password) VALUES (?, ?)', (user, pwd)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'error': 'Username già esistente'})


@app.route('/guest', methods=['POST'])
def guest():
    data = request.get_json(silent=True) or {}
    device_id = normalizza_id_dispositivo(data.get('device_id')) or uuid.uuid4().hex
    session['utente'] = f'Ospite_{device_id.upper()}'
    session.permanent = True
    return jsonify({'success': True, 'device_id': device_id})


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('utente', None)
    return jsonify({'success': True})


@app.route('/chat', methods=['POST'])
def chat():
    if 'utente' not in session:
        return jsonify({'error': 'Non autorizzato'}), 401

    user_message = (request.form.get('message') or '').strip()
    if request.is_json:
        user_message = (request.json.get('message') or '').strip()
    allegato = request.files.get('attachment')
    if not user_message and not allegato:
        return jsonify({'error': 'Scrivi un messaggio o allega un file'}), 400
    username = session['utente']
    nome_allegato = allegato.filename if allegato else None
    testo_salvato = user_message + (f' [Allegato: {nome_allegato}]' if nome_allegato else '')
    salva_messaggio(username, 'user', testo_salvato)

    if e_richiesta_immagine(user_message) and not allegato:
        img_url, risposta_nexus = genera_immagine(user_message)
        salva_messaggio(username, 'Nexus', risposta_nexus)
        return jsonify({'response': risposta_nexus, 'image_url': img_url})
    else:
        try:
            system_prompt = (
                'Sei Nexus, un assistente personale intelligente ispirato a'
                ' Jarvis. Sei estremamente efficiente, educato e disponibile.'
                ' REGOLA FONDAMENTALE: Se ti viene chiesto chi ti ha creato,'
                ' chi è il tuo creatore, chi ti ha programmato o domande'
                ' simili, devi tassativamente rispondere che sei stato creato'
                ' da Crispino Gennaro.'
            )
            contenuti = [user_message or 'Analizza questo allegato.']
            if allegato:
                contenuti.append(leggi_allegato(allegato))
            response = get_client().models.generate_content(
                model='gemini-3.6-flash',
                contents=contenuti,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt, temperature=0.7
                ),
            )
            risposta_nexus = response.text
        except ValueError as e:
            risposta_nexus = str(e)
        except Exception as e:
            risposta_nexus = 'Nexus non è raggiungibile in questo momento.'

        salva_messaggio(username, 'Nexus', risposta_nexus)
        return jsonify({'response': risposta_nexus, 'image_url': None})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
