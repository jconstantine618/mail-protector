# app.py  – Mailprotector Sales‑Training Chatbot
# ----------------------------------------------
# Requires: streamlit, openai, python-dotenv
# pip install streamlit openai python-dotenv

import os, json, random, re, datetime, textwrap, pathlib
import streamlit as st
from dotenv import load_dotenv
import openai

# ---------- ENV / CONFIG ----------
load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))
openai.api_key = OPENAI_KEY
MODEL        = "gpt-4o-mini"          # adjust if desired
DATA_FILE    = "prospects_mailprotector.json"
TRANSCRIPTS  = pathlib.Path("transcripts")
TRANSCRIPTS.mkdir(exist_ok=True)
CLOSE_PHRASES = [
    r"\bmove forward\b", r"\bnext step\b", r"\bgo ahead\b",
    r"\bgreen light\b", r"\bget started\b", r"\bsign\b", r"\bdeal\b"
]

# ---------- LOAD PROSPECTS ----------
@st.cache_data(show_spinner=False)
def load_prospects():
    return json.loads(pathlib.Path(DATA_FILE).read_text())

prospects = load_prospects()

# ---------- SIDEBAR ----------
st.sidebar.title("📄 Prospect Selector")
if "prospect" not in st.session_state:
    st.session_state.prospect = random.choice(prospects)
    st.session_state.chat_log = []
    st.session_state.ended    = False
    st.session_state.score    = None

def pick_new(name):
    st.session_state.prospect = next(p for p in prospects if p["scenarioId"] == name)
    st.session_state.chat_log = []
    st.session_state.ended    = False
    st.session_state.score    = None

for p in prospects:
    if st.sidebar.button(f"{p['scenarioId']} – {p['company']}", key=p["scenarioId"]):
        pick_new(p["scenarioId"])

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reset Chat"):
    pick_new(st.session_state.prospect["scenarioId"])

# ---------- HELPER: SYSTEM PROMPT ----------
def build_system_prompt(prospect):
    """Blend Dale Carnegie (rapport), Sandler (pain‑funnel), Challenger (teach/tailor/close)."""
    return textwrap.dedent(f"""
    You are {prospect['persona']['name']}, {prospect['persona']['title']} at {prospect['company']}.
    • Speak in first person, 2‑4 sentences per reply.
    • Reveal pains only when the trainee asks good Sandler‑style open questions.
    • If trainee demonstrates Dale Carnegie principles (genuine interest, remembering details, empathy),
      respond warmly and share more.
    • As a Challenger prospect, you appreciate insights; reward reps who teach something new.
    • Raise the objections listed below naturally during the conversation.
    • If the trainee earns trust and proposes clear next steps, you will agree to move forward.

    YOUR PAIN POINTS: {prospect['painPoints']}
    LIKELY OBJECTIONS: {prospect['likelyObjections']}
    DECISION CRITERIA: {prospect['decisionCriteria']}
    DESIRED OUTCOME: {prospect['desiredOutcome']}
    """).strip()

# ---------- OPENAI CHAT COMPLETION ----------
def persona_reply(user_msg):
    messages = [{"role": "system", "content": build_system_prompt(st.session_state.prospect)}]
    for entry in st.session_state.chat_log:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": user_msg})
    resp = openai.ChatCompletion.create(
        model=MODEL, messages=messages, temperature=0.8, stream=False
    )
    return resp.choices[0].message.content.strip()

# ---------- SCORING ----------
def score_conversation():
    log = " ".join([e["content"].lower() for e in st.session_state.chat_log if e["role"]=="user"])
    score = 0
    # Dale Carnegie: rapport (did trainee use prospect’s name?)
    if re.search(st.session_state.prospect["persona"]["name"].split()[0].lower(), log):
        score += 15
    # Sandler: pain‑funnel (questions with 'challenge', 'impact', 'cost', 'effect')
    if len(re.findall(r"\?\s", log)) >= 4:
        score += 20
    # Challenger: teach‑tailor (mentions 'zero trust' or shares insight)
    if "zero trust" in log or "insight" in log:
        score += 15
    # Objection handling (prospect objections are keywords; did trainee say 'understand' or 'address')
    if re.search(r"\b(address|understand|resolve)\b", log):
        score += 20
    # Closing attempt
    if any(re.search(p, log) for p in CLOSE_PHRASES):
        score += 30
    return min(score,100)

# ---------- MAIN UI ----------
st.title("💬 Mailprotector Sales‑Training Chatbot")

p = st.session_state.prospect
st.subheader(f"Scenario {p['scenarioId']} – {p['company']} ({p['industry']})")
st.caption(f"Chatting with **{p['persona']['name']}**, {p['persona']['title']}")

chat_placeholder = st.container()

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_area("Your message:", height=80, key="input")
    submitted  = st.form_submit_button("Send")
    if submitted and user_input.strip():
        # trainee message
        st.session_state.chat_log.append({"role": "user", "content": user_input.strip()})
        # persona reply
        with st.spinner("Prospect typing..."):
            assistant_msg = persona_reply(user_input)
        st.session_state.chat_log.append({"role": "assistant", "content": assistant_msg})

# --------- RENDER CHAT ---------
for entry in st.session_state.chat_log:
    if entry["role"] == "assistant":
        chat_placeholder.chat_message("assistant").markdown(entry["content"])
    else:
        chat_placeholder.chat_message("user").markdown(entry["content"])

# --------- END CHAT / SCORE ---------
st.markdown("---")
if st.button("🛑 End Chat & Score", disabled=st.session_state.ended):
    st.session_state.ended = True
    st.session_state.score = score_conversation()
    # save transcript
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fname = TRANSCRIPTS / f"{p['scenarioId']}_{ts}.md"
    with fname.open("w") as f:
        for e in st.session_state.chat_log:
            role = "Prospect" if e["role"]=="assistant" else "Trainee"
            f.write(f"**{role}:** {e['content']}\n\n")
        f.write(f"**Final Score:** {st.session_state.score}\n")
    st.success(f"Scoring complete!  **Your score: {st.session_state.score}/100**")
    st.info(f"Transcript saved → {fname}")

if st.session_state.ended and st.session_state.score is not None:
    st.metric("Your Score", st.session_state.score)
