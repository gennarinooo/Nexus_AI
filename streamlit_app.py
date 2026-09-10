import json
import re
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from google import genai

import nexus


st.set_page_config(page_title="Nexus AI", page_icon="N", layout="wide")

st.markdown(
    """
    <style>
    :root { --ink: #163300; --lime: #9FE870; --paper: #F4F8ED; --line: #CAD8C2; }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stSidebar"] { background: var(--ink); }
    [data-testid="stSidebar"] * { color: var(--paper); }
    .nexus-title { color: var(--ink); font-family: Georgia, serif; font-size: 2.4rem; font-weight: 700; }
    div[data-testid="stChatMessage"], div[data-testid="stForm"] { border-radius: 4px; border: 1px solid var(--line); }
    .auth-card { max-width: 560px; margin: 10vh auto 0; padding: 2.5rem; background: white; border: 1px solid var(--line); border-radius: 4px; }
    .square-panel { padding: 1.2rem; background: white; border: 1px solid var(--line); border-radius: 4px; }
    button, [data-testid="stFileUploader"] section { border-radius: 4px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_device_id():
    device_id = st.query_params.get("device_id")
    if not device_id or not re.fullmatch(r"[a-f0-9]{32}", device_id):
        device_id = uuid.uuid4().hex
        st.query_params["device_id"] = device_id
    return device_id.upper()


def account_action(username, password, action):
    username = username.strip()
    if not username or not password:
        return False, "Inserisci username e password."
    conn = __import__("sqlite3").connect("nexus_database.db")
    try:
        if action == "register":
            conn.execute(
                "INSERT INTO utenti (username, password) VALUES (?, ?)",
                (username, password),
            )
            conn.commit()
            return True, "Registrazione completata. Ora puoi accedere."
        user = conn.execute(
            "SELECT username FROM utenti WHERE username = ? AND password = ?",
            (username, password),
        ).fetchone()
        return (True, "Accesso effettuato.") if user else (False, "Credenziali errate.")
    except __import__("sqlite3").IntegrityError:
        return False, "Username già esistente."
    finally:
        conn.close()


def render_auth_screen():
    st.markdown('<div class="auth-card">', unsafe_allow_html=True)
    st.markdown('<div class="nexus-title">Nexus AI</div>', unsafe_allow_html=True)
    st.caption("Accedi per continuare oppure usa Nexus come ospite.")
    username = st.text_input("Username", key="auth_username")
    password = st.text_input("Password", type="password", key="auth_password")
    login_col, register_col, guest_col = st.columns(3)
    if login_col.button("Accedi", use_container_width=True):
        success, message = account_action(username, password, "login")
        if success:
            st.session_state.authenticated_user = username.strip()
            st.rerun()
        st.error(message)
    if register_col.button("Registrati", use_container_width=True):
        success, message = account_action(username, password, "register")
        (st.success if success else st.error)(message)
    if guest_col.button("Continua come ospite", use_container_width=True):
        st.session_state.guest_device_id = get_device_id()
        st.session_state.authenticated_user = f"Ospite_{st.session_state.guest_device_id}"
        st.session_state.is_guest = True
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    return False


def geocode(location):
    query = urllib.parse.quote(location)
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={query}&count=1&language=it&format=json"
    request = urllib.request.Request(url, headers={"User-Agent": "NexusAI/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        results = json.loads(response.read().decode("utf-8")).get("results", [])
    if not results:
        raise ValueError("Località non trovata")
    result = results[0]
    return result["name"], result["latitude"], result["longitude"], result.get("timezone", "auto")


def get_weather(location):
    name, latitude, longitude, timezone = geocode(location)
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,"
        f"apparent_temperature,weather_code,wind_speed_10m&timezone={urllib.parse.quote(timezone)}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "NexusAI/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        current = json.loads(response.read().decode("utf-8")).get("current", {})
    return {
        "location": name,
        "timezone": timezone,
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind": current.get("wind_speed_10m"),
        "weather_code": current.get("weather_code"),
    }


def parse_calendar(uploaded_file):
    if not uploaded_file:
        return []
    text = uploaded_file.getvalue().decode("utf-8", errors="replace")
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        summary = re.search(r"(?:^|\n)SUMMARY(?:;[^:]*)?:(.*)", block)
        start = re.search(r"(?:^|\n)DTSTART(?:;[^:]*)?:(\d{8}T?\d{0,6}Z?)", block)
        if not summary or not start:
            continue
        raw_start = start.group(1)
        try:
            event_start = datetime.strptime(raw_start.rstrip("Z"), "%Y%m%dT%H%M%S")
        except ValueError:
            try:
                event_start = datetime.strptime(raw_start.rstrip("Z"), "%Y%m%d")
            except ValueError:
                continue
        events.append({"title": summary.group(1).strip(), "start": event_start})
    return sorted(events, key=lambda event: event["start"])


def context_text():
    now = datetime.now(ZoneInfo("Europe/Rome"))
    lines = [f"Ora italiana attuale: {now:%A %d %B %Y, %H:%M:%S}"]
    weather = st.session_state.get("weather")
    if weather:
        lines.append(
            "Meteo richiesto per {location}: {temperature}°C, percepiti {feels_like}°C, "
            "umidità {humidity}%, vento {wind} km/h, codice meteo {weather_code}.".format(**weather)
        )
    events = st.session_state.get("events", [])
    if events:
        lines.append("Prossimi eventi calendario: " + "; ".join(
            f"{event['title']} ({event['start']:%d/%m %H:%M})" for event in events[:8]
        ))
    return "\n".join(lines)


def history_for(username):
    if username.startswith("Ospite_"):
        return []

    conn = __import__("sqlite3").connect("nexus_database.db")
    rows = conn.execute(
        "SELECT ruolo, messaggio FROM chat_history WHERE username = ? ORDER BY id ASC",
        (username,),
    ).fetchall()
    conn.close()
    return rows


def ask_nexus(prompt, attachment=None):
    system_prompt = (
        "Sei Nexus, un assistente personale rapido e preciso. Rispondi in italiano. "
        "Usa il contesto dinamico fornito per rispondere a domande su ora, meteo, "
        "posizione e calendario; se un dato manca, dichiaralo invece di inventarlo. "
        "Se ti chiedono chi ti ha creato, rispondi che sei stato creato da Crispino Gennaro.\n\n"
        f"CONTESTO DINAMICO:\n{context_text()}"
    )
    contents = [prompt or "Analizza l'allegato."]
    if attachment:
        contents.append(genai.types.Part.from_bytes(
            data=attachment.getvalue(), mime_type=attachment.type
        ))
    response = nexus.get_client().models.generate_content(
        model="gemini-3.6-flash",
        contents=contents,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt, temperature=0.4
        ),
    )
    return response.text or "Non ho ricevuto una risposta testuale."


def render_history(username):
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Ciao, sono Nexus. Posso aiutarti anche con ora, meteo, calendario e allegati."}
        ]
        for role, message in history_for(username)[-30:]:
            st.session_state.messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": message,
            })
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


if "authenticated_user" not in st.session_state:
    render_auth_screen()
    st.stop()

username = st.session_state.authenticated_user
is_guest = st.session_state.get("is_guest", False)
top_col, action_col = st.columns([5, 1])
with top_col:
    st.markdown('<div class="nexus-title">Nexus AI</div>', unsafe_allow_html=True)
    st.caption("Il tuo assistente personale, con contesto aggiornato.")
    if is_guest:
        st.caption(f"ID ospite di questo dispositivo: {st.session_state.guest_device_id}")
with action_col:
    if st.button("Esci", use_container_width=True):
        for key in ("authenticated_user", "is_guest", "guest_device_id", "messages"):
            st.session_state.pop(key, None)
        st.rerun()

with st.container(border=True):
    st.markdown("#### Configura il contesto")
    st.caption("Queste opzioni servono solo a dare a Nexus informazioni più precise.")
    context_col, calendar_col, update_col = st.columns([2, 2, 1])
    with context_col:
        location = st.text_input(
            "Località per il meteo", value=st.session_state.get("location", "Roma"),
            key="context_location",
        )
    with calendar_col:
        calendar_file = st.file_uploader("Calendario .ics", type=["ics"], key="context_calendar")
    with update_col:
        st.write("")
        st.write("")
        if st.button("Applica", use_container_width=True):
            try:
                st.session_state.weather = get_weather(location)
                st.session_state.location = location
                if calendar_file:
                    st.session_state.events = parse_calendar(calendar_file)
                st.success("Contesto aggiornato.")
            except Exception as error:
                st.error(f"Contesto non disponibile: {error}")
    if st.session_state.get("weather"):
        weather = st.session_state.weather
        st.caption(f"Meteo: {weather['location']} · {weather['temperature']}°C · umidità {weather['humidity']}%")
    if st.session_state.get("events"):
        st.caption(f"Eventi calendario caricati: {len(st.session_state.events)}")

if st.session_state.get("conversation_user") != username:
    st.session_state.pop("messages", None)
    st.session_state.conversation_user = username
render_history(username)
attachment = st.file_uploader(
    "Allega un file o una foto", type=["jpg", "jpeg", "png", "webp", "gif", "pdf", "txt"],
    key="chat_attachment",
)
prompt = st.chat_input("Scrivi a Nexus...")

if prompt or attachment:
    visible_prompt = prompt or "Analizza questo allegato."
    st.session_state.messages.append({"role": "user", "content": visible_prompt})
    nexus.salva_messaggio(username, "user", visible_prompt)
    with st.chat_message("user"):
        st.markdown(visible_prompt)
        if attachment:
            st.caption(f"Allegato: {attachment.name}")
    with st.chat_message("assistant"):
        with st.spinner("Nexus sta elaborando..."):
            try:
                if nexus.e_richiesta_immagine(prompt or "") and not attachment:
                    image_url, response = nexus.genera_immagine(prompt)
                    if image_url:
                        image_path = Path(image_url.lstrip("/"))
                        if image_path.exists():
                            st.image(str(image_path))
                else:
                    response = ask_nexus(prompt, attachment)
            except Exception:
                response = "Nexus non è raggiungibile in questo momento."
            st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
    nexus.salva_messaggio(username, "Nexus", response)
