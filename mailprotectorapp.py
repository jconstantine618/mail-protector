# mailprotectorapp.py

import os, json, random, re, datetime, textwrap, pathlib
import streamlit as st
from dotenv import load_dotenv
import openai

# ---------- ENV / CONFIG ----------
try:
    load_dotenv()
except ModuleNotFoundError:
    pass

OPENAI_KEY = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))
client = openai.OpenAI(api_key=OPENAI_KEY)

MODEL = "gpt-4o"
DATA_FILE = "data/prospects_mailprotector.json"
TRANSCRIPTS = pathlib.Path("transcripts")
TRANSCRIPTS.mkdir(exist_ok=True)
CLOSE_PHRASES = [
    r"\bmove forward\b", r"\bnext step\b", r"\bgo ahead\b",
    r"\bgreen light\b", r"\bget started\b", r"\bsign\b", r"\bdeal\b"
]

# ---------- LOAD PROSPECTS ----------
@st.cache_data(show_spinner=False)
def load_prospects():
    try:
        return json.loads(pathlib.Path(DATA_FILE).read_text())
    except FileNotFoundError:
        st.error(f"❌ File not found: {DATA_FILE}")
        st.stop()

prospects = load_prospects()

# ---------- SIDEBAR ----------
st.sidebar.title("📄 Prospect Selector")
if "prospect" not in st.session_state:
    st.session_state.prospect = random.choice(prospects)
    st.session_state.chat_log = []
    st.session_state.ended = False
    st.session_state.score = None

def pick_new(name):
    st.session_state.prospect = next(p for p in prospects if p["scenarioId"] == name)
    st.session_state.chat_log = []
    st.session_state.ended = False
    st.session_state.score = None

for p in prospects:
    if st.sidebar.button(f"{p['scenarioId']} – {p['company']}", key=p["scenarioId"]):
        pick_new(p["scenarioId"])

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reset Chat"):
    pick_new(st.session_state.prospect["scenarioId"])

# ---------- SYSTEM PROMPT ----------
PROMPT_TMPL = """
You are {persona_name}, the {persona_title} at {company} ({industry}, {location}).

GOAL:
– Have an authentic dialogue with a sales trainee about {company}’s email-security needs.
– Reveal pain points only when the trainee asks thoughtful questions.
– Raise objections from the list below naturally.
– Reward good rapport, open questions, and insights.
– If the trainee proposes next steps that meet your criteria, agree to move forward.

PAIN POINTS: {pain_points}
OBJECTIONS: {likely_objections}
DECISION CRITERIA: {decision_criteria}
OUTCOME: {desired_outcome}
TRIGGER: {trigger_event}
CURRENT SOLUTION: {current_solution}

Speak in ~2–4 sentences, plain and professional.
Never break character.
"""

def build_system_prompt(prospect):
    ctx = {
        "persona_name": prospect["persona"]["name"],
        "persona_title": prospect["persona"]["title"],
        "company": prospect["company"],
        "industry": prospect["industry"],
        "location": prospect["location"],
        "pain_points": ", ".join(prospect["painPoints"]),
        "likely_objections": ", ".join(prospect["likelyObjections"]),
        "decision_criteria": ", ".join(prospect["decisionCriteria"]),
        "desired_outcome": prospect["desiredOutcome"],
        "trigger_event": prospect.get("triggerEvent", ""),
        "current_solution": prospect.get("currentSolution", "")
    }
    return PROMPT_TMPL.format(**ctx)

# ---------- CHAT COMPLETION ----------
def persona_reply(user_msg):
    messages = [{"role": "system", "content": build_system_prompt(st.session_state.prospect)}]
    for entry in st.session_state.chat_log:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": user_msg})

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.8
    )
    return resp.choices[0].message.content.strip()

# ---------- SCORING ----------
def score_conversation():
    log = " ".join([e["content"].lower() for e in st.session_state.chat_log if e["role"]=="user"])
    score = 0
    if re.search(st.session_state.prospect["persona"]["name"].split()[0].lower(), log):
        score += 15
    if len(re.findall(r"\?\s", log)) >= 4:
        score += 20
    if "zero trust" in log or "insight" in log:
        score += 15
    if re.search(r"\b(address|understand|resolve)\b", log):
        score += 20
    if any(re.search(p, log) for p in CLOSE_PHRASES):
        score += 30
    return min(score, 100)

# ---------- MAIN UI ----------
st.title("💬 Mailprotector Sales Training Chatbot")

p = st.session_state.prospect
st.markdown(f"""
<div style='border:1px solid #ccc; border-radius:10px; padding:10px; background:#f9f9f9'>
<b>Persona:</b> {p['persona']['name']} ({p['persona']['title']})  <br>
<b>Company:</b> {p['company']}  <br>
<b>Industry:</b> {p['industry']}  <br>
<b>Location:</b> {p['location']}  <br>
<b>Difficulty:</b> Medium  
</div>
""", unsafe_allow_html=True)

chat_placeholder = st.container()

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("💬 Your message to the prospect", key="input")
    submitted = st.form_submit_button("Send")
    if submitted and user_input.strip():
        st.session_state.chat_log.append({"role": "user", "content": user_input.strip()})
        with st.spinner("Prospect typing..."):
            assistant_msg = persona_reply(user_input)
        st.session_state.chat_log.append({"role": "assistant", "content": assistant_msg})

# ---------- RENDER CHAT ----------
for entry in st.session_state.chat_log:
    if entry["role"] == "assistant":
        chat_placeholder.chat_message("assistant").markdown(f"🟡 **Prospect:** {entry['content']}")
    else:
        chat_placeholder.chat_message("user").markdown(f"🔴 **You:** {entry['content']}")

# ---------- END + SCORE ----------
st.markdown("---")
if st.button("🛑 End Chat & Score", disabled=st.session_state.ended):
    st.session_state.ended = True
    st.session_state.score = score_conversation()
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fname = TRANSCRIPTS / f"{p['scenarioId']}_{ts}.md"
    with fname.open("w") as f:
        for e in st.session_state.chat_log:
            role = "Prospect" if e["role"] == "assistant" else "Trainee"
            f.write(f"**{role}:** {e['content']}\n\n")
        f.write(f"**Final Score:** {st.session_state.score}\n")
    st.success(f"✅ Scoring complete! **Your score: {st.session_state.score}/100**")
    st.info(f"Transcript saved → {fname}")

if st.session_state.ended and st.session_state.score is not None:
    st.metric("Your Score", st.session_state.score)
