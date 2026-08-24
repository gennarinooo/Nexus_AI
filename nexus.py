import os
import sqlite3
import uuid
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Configurazione di sicurezza per la codifica del terminale
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')

from google import genai

# Inizializza il client Google GenAI con la tua API Key
client = genai.Client(api_key="AQ.Ab8RN6Ku8wcabn-lGYUogueGkS40VmnwTDXXH8f2Plpcg29MuQ")

# Funzione per ottenere la data e l'ora esatta italiana (Europe/Rome)
def ora_italiana():
    return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H:%M:%S")

# --- 1. GESTIONE DEL DATABASE ---
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
            timestamp TEXT
        )
    ''')
    
    cursor.execute("SELECT * FROM utenti WHERE username = 'GenCrisp011'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO utenti (username, password) VALUES ('GenCrisp011', 'Torogefr26')")
    
    conn.commit()
    conn.close()

def salva_messaggio(username, ruolo, messaggio):
    # Salviamo i messaggi inserendo manualmente l'orario preciso d'Italia
    conn = sqlite3.connect("nexus_database.db")
    cursor = conn.cursor()
    timestamp_corretto = ora_italiana()
    cursor.execute(
        "INSERT INTO chat_history (username, ruolo, messaggio, timestamp) VALUES (?, ?, ?, ?)", 
        (username, ruolo, messaggio, timestamp_corretto)
    )
    conn.commit()
    conn.close()

def ottieni_utenti_con_chat():
    conn = sqlite3.connect("nexus_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT username FROM chat_history ORDER BY username ASC")
    utenti = [row[0] for row in cursor.fetchall()]
    conn.close()
    return utenti

def recupera_cronologia_utente(username):
    conn = sqlite3.connect("nexus_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, ruolo, messaggio FROM chat_history WHERE username = ? ORDER BY id ASC", (username,))
    logs = cursor.fetchall()
    conn.close()
    return logs

# --- 2. LOGICA DEL CHATBOT ---
def chat_con_nexus(username):
    print(f"\n--------------------------------------------------")
    print(f"  Nexus è online. Benvenuto, {username}. Scrivi 'esci' per chiudere.")
    print(f"--------------------------------------------------\n")

    system_prompt = (
        "Sei Nexus, un assistente personale intelligente ispirato a Jarvis. "
        "Sei estremamente efficiente, educato e disponibile. "
        "REGOLA FONDAMENTALE: Se ti viene chiesto chi ti ha creato, chi è il tuo creatore, "
        "chi ti ha programmato o domande simili, devi tassativamente rispondere che sei stato "
        "creato da Crispino Gennaro."
    )

    try:
        chat_session = client.chats.create(
            model="gemini-3.6-flash",
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=1024,
            )
        )
    except Exception as e:
        print(f"\n[Errore critico di connessione a Gemini]: {e}")
        return

    while True:
        try:
            user_input = input(f"\n[{username}]: ")
            if user_input.lower() in ["esci", "exit", "quit"]:
                print("Nexus: Arrivederci. Spengo i sistemi.")
                break
            
            if not user_input.strip():
                continue

            salva_messaggio(username, "user", user_input)

            # Invio del messaggio a Gemini
            response = chat_session.send_message(user_input)
            
            if response and hasattr(response, 'text') and response.text:
                risposta_nexus = response.text
            else:
                risposta_nexus = "[Errore: Nessuna risposta ricevuta dal modello o risposta vuota.]"

            try:
                print(f"\n[Nexus]: {risposta_nexus}")
            except UnicodeEncodeError:
                risposta_sicura = risposta_nexus.encode('ascii', errors='replace').decode('ascii')
                print(f"\n[Nexus]: {risposta_sicura}")

            salva_messaggio(username, "Nexus", risposta_nexus)

        except Exception as e:
            print(f"\n[Errore durante la generazione della risposta]: {e}")

# --- 3. MENU E AUTENTICAZIONE ---
def menu_admin():
    while True:
        print("\n=== PANNELLO DI CONTROLLO ADMIN ===")
        print("1. Chatta con Nexus")
        print("2. Visualizza le chat di utenti e ospiti (separate per ID)")
        print("3. Esci")
        scelta = input("Scegli un'opzione: ")
        
        if scelta == "1":
            chat_con_nexus("GenCrisp011")
        elif scelta == "2":
            utenti = ottieni_utenti_con_chat()
            if not utenti:
                print("\nNessuna cronologia salvata nel database.")
                continue
            
            print("\n--- ELENCO UTENTI E OSPITI CON CHAT SALVATE ---")
            for i, u in enumerate(utenti, 1):
                print(f"{i}. {u}")
            print("------------------------------------------------")
            
            scelta_utente = input("Digita il numero dell'utente/ospite di cui vuoi leggere la chat (o premi invio per tornare): ")
            if scelta_utente.isdigit():
                indice = int(scelta_utente) - 1
                if 0 <= indice < len(utenti):
                    utente_selezionato = utenti[indice]
                    logs = recupera_cronologia_utente(utente_selezionato)
                    print(f"\n=== CRONOLOGIA CHAT DI: {utente_selezionato} ===")
                    for log in logs:
                        print(f"[{log[0]}] {log[1]}: {log[2]}")
                    print("================================================")
                else:
                    print("Numero non valido.")
        elif scelta == "3":
            break
        else:
            print("Scelta non valida.")

def menu_principale():
    inizializza_db()
    
    while True:
        print("\n=== BENVENUTO NEL SISTEMA NEXUS ===")
        print("1. Accedi (Login)")
        print("2. Registrati (Nuovo Utente)")
        print("3. Continua come Ospite")
        print("4. Spegni sistema")
        scelta = input("Seleziona un'opzione: ")

        if scelta == "1":
            user = input("Username: ")
            pwd = input("Password: ")
            
            if user == "GenCrisp011" and pwd == "Torogefr26":
                print("\nAccesso Amministratore confermato.")
                menu_admin()
            else:
                conn = sqlite3.connect("nexus_database.db")
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM utenti WHERE username = ? AND password = ?", (user, pwd))
                if cursor.fetchone():
                    print("\nAccesso riuscito.")
                    chat_con_nexus(user)
                else:
                    print("\nCredenziali errate.")
                conn.close()

        elif scelta == "2":
            user = input("Scegli un Username: ")
            pwd = input("Scegli una Password: ")
            
            conn = sqlite3.connect("nexus_database.db")
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO utenti (username, password) VALUES (?, ?)", (user, pwd))
                conn.commit()
                print("\nAccount creato! Ora puoi accedere.")
            except sqlite3.IntegrityError:
                print("\nQuesto Username esiste già.")
            conn.close()

        elif scelta == "3":
            guest_id = f"Ospite_{uuid.uuid4().hex[:5].upper()}"
            print(f"\nAccesso come {guest_id}. Le conversazioni verranno salvate separatamente.")
            chat_con_nexus(guest_id)

        elif scelta == "4":
            print("Chiusura del sistema...")
            break
        else:
            print("Opzione non valida.")

if __name__ == "__main__":
    menu_principale()
