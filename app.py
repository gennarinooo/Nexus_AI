import sqlite3
import uuid
from flask import Flask, render_template, request, jsonify, session
from google import genai
from google.genai import types

app = Flask(__name__)
app.secret_key = "nexus_secret_key_super_sicura"

# Inizializza il client Google GenAI con la tua API Key di Gemini
client = genai.Client(api_key="LA_TUA_API_KEY_GEMINI_QUI")

# --- DATABASE SETUP ---
def inizializza_db():
    conn = sqlite3.connect("nexus_database.db")
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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Account Admin di default
    cursor.execute("SELECT * FROM utenti WHERE username = 'GenCrisp011'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO utenti (username, password) VALUES ('GenCrisp011', 'Torogefr26')")
    conn.commit()
    conn.close()

inizializza_db()

def salva_messaggio(username, ruolo, messaggio):
    conn = sqlite3.connect("nexus_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (username, ruolo, messaggio) VALUES (?, ?, ?)", (username, ruolo, messaggio))
    conn.commit()
    conn.close()

# --- ROTTE FLASK ---

@app.route("/")
def home():
    return render_template("index.html")

# API Autenticazione & Gestione Ospiti
@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.json
    azione = data.get("action")
    user = data.get("username", "").strip()
    pwd = data.get("password", "").strip()

    if azione == "guest":
        # Assegna un ID univoco all'ospite (es. Ospite_B49A1)
        guest_id = f"Ospite_{uuid.uuid4().hex[:5].upper()}"
        session['username'] = guest_id
        return jsonify({"success": True, "username": guest_id})

    elif azione == "login":
        conn = sqlite3.connect("nexus_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM utenti WHERE username = ? AND password = ?", (user, pwd))
        row = cursor.fetchone()
        conn.close()
        if row:
            session['username'] = user
            return jsonify({"success": True, "username": user})
        return jsonify({"success": False, "message": "Credenziali errate!"})

    elif azione == "register":
        conn = sqlite3.connect("nexus_database.db")
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO utenti (username, password) VALUES (?, ?)", (user, pwd))
            conn.commit()
            conn.close()
            session['username'] = user
            return jsonify({"success": True, "username": user})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"success": False, "message": "Username già in uso!"})

    return jsonify({"success": False, "message": "Azione non valida"})

# API Chat con Gemini AI
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    username = data.get("username", "Ospite_Anonimo")
    user_input = data.get("message", "")

    system_prompt = (
        "Sei Nexus, un assistente personale intelligente ispirato a Jarvis. "
        "Sei estremamente efficiente, educato e disponibile. "
        "REGOLA FONDAMENTALE: Se ti viene chiesto chi ti ha creato, chi è il tuo creatore, "
        "chi ti ha programmato o domande simili, devi tassativamente rispondere che sei stato "
        "creato da Crispino Gennaro."
    )

    try:
        # Salva il messaggio dell'utente nel database
        salva_messaggio(username, "user", user_input)

        # Chiamata a Gemini tramite SDK google-genai
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=1024,
            )
        )

        risposta_nexus = response.text if response and response.text else "Nessuna risposta generata."
        
        # Salva la risposta dell'AI nel database
        salva_messaggio(username, "Nexus", risposta_nexus)

        return jsonify({"reply": risposta_nexus})
    except Exception as e:
        return jsonify({"reply": f"Errore Gemini: {str(e)}"}), 500

# Pannello Admin per leggere le chat di tutti (Ospiti inclusi)
@app.route("/admin/logs")
def visualizza_logs():
    conn = sqlite3.connect("nexus_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT username FROM chat_history ORDER BY username ASC")
    utenti = [row[0] for row in cursor.fetchall()]
    
    html = "<h2>Pannello Admin Nexus - Elenco Utenti & Ospiti</h2><ul>"
    for u in utenti:
        html += f'<li><a href="/admin/logs/{u}">{u}</a></li>'
    html += "</ul>"
    conn.close()
    return html

@app.route("/admin/logs/<username>")
def visualizza_log_utente(username):
    conn = sqlite3.connect("nexus_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, ruolo, messaggio FROM chat_history WHERE username = ? ORDER BY id ASC", (username,))
    logs = cursor.fetchall()
    conn.close()
    
    html = f"<h2>Cronologia Chat di: {username}</h2><a href='/admin/logs'>← Torna all'elenco</a><hr>"
    for log in logs:
        html += f"<p><b>[{log[0]}] {log[1]}:</b> {log[2]}</p>"
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
