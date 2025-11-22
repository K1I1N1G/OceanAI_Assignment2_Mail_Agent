# UI/chat.py
"""
Chat page for OceanAI_Mail_Agent.

Features:
- Shows mail info in a header box (provided by prompter or fallback builder).
- Loads mail by mail_id query param (same routing style as home.py).
- Uses Backend.prompter.make_prompt(mail) when available to build an LLM prompt.
- Chat UI: user input box at bottom, messages stacked; user messages stored on the right,
  AI responses shown on the left. Chat inputs are combined with the prompter prompt before calling LLM.
- Uses Agent_Brain.connection_gateway.call for LLM queries (same API used elsewhere).
- Editable draft body for mails with category == "draft": textarea + Save Draft button -> update_mail.
- Minimal dependencies; graceful fallbacks if Backend modules missing.
- Keeps visual styling consistent with home.py.
"""

import streamlit as st
import html
from datetime import datetime
from pathlib import Path
import json
import time
import sys
import traceback

# Styling (kept consistent with home.py)
font_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800;900&display=swap');

html, body, [class*="css"]  {
    font-family: 'Montserrat', system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    color: #ffffff;
}
.oceanai-header { font-weight: 900; font-size: 28px; color: #ffffff; margin: 8px 0 12px 0; }
.ocean-mail-info {
  border-radius:10px;
  padding:12px;
  margin-bottom:12px;
  background: linear-gradient(180deg, rgba(8,20,30,0.95), rgba(6,12,20,0.95));
  border:1px solid rgba(255,255,255,0.06);
}
.ocean-chat {
  border-radius:10px;
  padding:12px;
  background: rgba(255,255,255,0.03);
  max-height: 56vh;
  overflow: auto;
}
.msg-left { background: rgba(60,160,120,0.14); border-radius:8px; padding:10px; margin:8px 0; color:#eafff1; }
.msg-right { background: linear-gradient(90deg, rgba(62,180,120,0.95), rgba(30,140,90,0.95)); border-radius:8px; padding:10px; margin:8px 0; color:#00210b; float:right; clear:both; }
.msg-meta { font-size:11px; color:rgba(255,255,255,0.6); margin-top:6px; }
.clearfix::after { content: ""; display: table; clear: both; }
.top-actions { display:flex; gap:8px; justify-content:flex-end; margin-bottom:8px; }
.small-muted { font-size:12px; color:rgba(255,255,255,0.6); }
textarea { width:100%; }
</style>
"""
st.markdown(font_css, unsafe_allow_html=True)

st.set_page_config(page_title="OceanAI_Mail_Agent — Chat", layout="wide")

# Try imports for backend utilities
loader = None
prompter_mod = None
update_mail = None
from_agent_call = None
try:
    import Backend.load_mail as loader
except Exception:
    loader = None

try:
    # prompter should expose make_prompt(mail) -> str
    import Backend.prompter as prompter_mod
except Exception:
    prompter_mod = None

# connection gateway
try:
    from Agent_Brain.connection_gateway import call as agent_call, ConnectionError
    from Agent_Brain.connection_gateway import ConnectionError as _ConnErr  # alias
    from update_mail import update_mail as top_update_mail
    update_mail = top_update_mail  # if available
except Exception:
    try:
        # alternative import path
        from Agent_Brain.connection_gateway import call as agent_call, ConnectionError
    except Exception:
        agent_call = None
    try:
        from Data_Storage_Vault.update_mail import update_mail as top_update_mail2
        update_mail = top_update_mail2
    except Exception:
        update_mail = None

# fallback extract helper (copied/adapted)
def _extract_text_from_call_output(out):
    try:
        if out is None:
            return ""
        if isinstance(out, dict):
            cands = out.get("candidates")
            if isinstance(cands, list) and len(cands) > 0:
                first = cands[0]
                content = first.get("content") if isinstance(first, dict) else None
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list) and len(parts) > 0 and isinstance(parts[0], dict):
                        txt = parts[0].get("text")
                        if isinstance(txt, str):
                            return txt
                if isinstance(first, dict):
                    for k in ("text", "output", "message"):
                        v = first.get(k)
                        if isinstance(v, str):
                            return v
            for k in ("response", "content", "output"):
                v = out.get(k)
                if isinstance(v, str):
                    return v
            return json.dumps(out)
        if isinstance(out, str):
            return out
        return str(out)
    except Exception:
        return str(out)

# helper: format timestamp
def fmt_ts(ts):
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return str(ts)

# Read mail_id from query params (same pattern used by home.py links)
# NOTE: use st.query_params (do not mix experimental_get_query_params)
query = st.query_params
mail_id = None
try:
    if "mail_id" in query:
        # query values are lists; keep same behavior
        v = query["mail_id"]
        if isinstance(v, list):
            mail_id = int(v[0])
        else:
            mail_id = int(v)
except Exception:
    mail_id = None

st.markdown('<div class="oceanai-header">Mail Chat</div>', unsafe_allow_html=True)

if mail_id is None:
    st.error("No mail selected. Go back to Inbox and click a mail card.")
    st.stop()

# Load mailbox and find mail
mail = None
try:
    import Backend.load_mail as _loader
    data = _loader.fast_return_mails()
    # fast_return_mails returns UI objects; match by id
    for m in data:
        try:
            if int(m.get("id")) == int(mail_id):
                mail = m.get("full") if m.get("full") else m
                break
        except Exception:
            if m.get("id") == mail_id:
                mail = m.get("full") if m.get("full") else m
                break
except Exception:
    # fallback: try to open the file directly
    try:
        MODULE_ROOT = Path(__file__).resolve().parents[1]
        inbox_path = MODULE_ROOT / "Data_Storage_Vault" / "mail_inbox.json"
        if inbox_path.exists():
            with inbox_path.open("r", encoding="utf-8") as f:
                inbox = json.load(f)
            for e in inbox.get("emails", []):
                try:
                    if int(e.get("id", -1)) == int(mail_id):
                        mail = e
                        break
                except Exception:
                    if e.get("id") == mail_id:
                        mail = e
                        break
    except Exception:
        mail = None

if mail is None:
    st.error(f"Mail id {mail_id} not found.")
    st.stop()

# Build prompter prompt (try prompter_mod, else fallback)
def build_prompt_for_mail(mail_obj):
    try:
        if prompter_mod and hasattr(prompter_mod, "make_prompt"):
            return prompter_mod.make_prompt(mail_obj)
    except Exception:
        # ignore and fallback
        traceback.print_exc()
    # fallback: simple structured prompt
    subj = mail_obj.get("subject", "")
    sender = mail_obj.get("sender", "")
    body = mail_obj.get("body") or json.dumps(mail_obj.get("body", "")) or ""
    prompt = f"MAIL INFORMATION\nFrom: {sender}\nSubject: {subj}\nBody:\n{body}\n\nWhen answering, base responses on this mail info."
    return prompt

base_prompt = build_prompt_for_mail(mail)

# Top box: show mail receiver info and basic fields
with st.container():
    st.markdown('<div class="ocean-mail-info">', unsafe_allow_html=True)
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**From:** {html.escape(str(mail.get('sender','')))}  \n**Subject:** {html.escape(str(mail.get('subject','')))}")
        body_preview = (mail.get("body") or "")[:1000]
        st.markdown(f"<div class='small-muted' style='margin-top:6px;'>Preview: {html.escape(str(body_preview))}</div>", unsafe_allow_html=True)
    with col2:
        ts = fmt_ts(mail.get("timestamp",""))
        st.markdown(f"<div class='small-muted'>{ts}</div>", unsafe_allow_html=True)
        # If mail is draft, show id and allow saving edits
        category = (mail.get("category") or "").lower()
        if category == "draft":
            st.markdown(f"<div class='small-muted'>DRAFT (editable)</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Editable draft area (if draft)
if (mail.get("category") or "").lower() == "draft":
    # show textarea prefilled with body (allow editing)
    st.markdown("**Edit draft body**")
    draft_body_key = f"draft_body_{mail_id}"
    if draft_body_key not in st.session_state:
        st.session_state[draft_body_key] = mail.get("body") or ""
    new_body = st.text_area("Draft body", value=st.session_state[draft_body_key], height=180, key=f"ta_{mail_id}")
    st.session_state[draft_body_key] = new_body

    col_a, col_b = st.columns([1,1])
    with col_a:
        if st.button("Save Draft", key=f"save_draft_{mail_id}"):
            # attempt update_mail
            if update_mail is None:
                st.error("update_mail function not available. Cannot save draft.")
            else:
                try:
                    ok = update_mail(mail_id, {"body": new_body})
                    if ok:
                        st.success("Draft saved.")
                        # reload mail object in session by forcing a small reload of the page
                        st.rerun()
                    else:
                        st.error("Failed to save draft (mail id not found).")
                except Exception as e:
                    st.error(f"Failed to save draft: {e}")
    with col_b:
        if st.button("Close Editor (reload)", key=f"close_edit_{mail_id}"):
            st.rerun()

st.markdown("---")

# Chat area
chat_box = st.container()
with chat_box:
    # initialize per-mail chat history in session state
    hist_key = f"chat_history_{mail_id}"
    if hist_key not in st.session_state:
        # Optionally pre-seed context with a system message containing the prompt
        st.session_state[hist_key] = [
            {"role": "system", "text": base_prompt, "ts": time.time()}
        ]

    st.markdown('<div class="ocean-chat">', unsafe_allow_html=True)
    # render history (skip the system base prompt when displaying)
    for msg in st.session_state[hist_key]:
        if msg.get("role") == "system":
            # show small muted box above chat once
            continue
        role = msg.get("role")
        text = msg.get("text")
        t = msg.get("ts")
        ts_text = datetime.fromtimestamp(t).strftime("%b %d %I:%M %p")
        if role == "user":
            # Right-aligned green bubble
            st.markdown(f'<div class="clearfix"><div class="msg-right">{html.escape(str(text))}<div class="msg-meta">{ts_text} • You</div></div></div>', unsafe_allow_html=True)
        else:
            # AI response - show left; use green-tinted left (per earlier design request)
            st.markdown(f'<div class="clearfix"><div class="msg-left">{html.escape(str(text))}<div class="msg-meta">{ts_text} • AI</div></div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# FIXED Input box and send button area (uses on_click callback to avoid Streamlit session_state gotcha)
# ---------------------------
st.markdown("**Ask about this mail / Instruct AI**")
input_key = f"user_input_{mail_id}"
if input_key not in st.session_state:
    st.session_state[input_key] = ""

# Callback invoked by the Send button. Mutations to st.session_state (including clearing the input)
# are allowed inside the on_click callback.
def _send_callback(mail_id=mail_id, hist_key=hist_key, input_key=input_key):
    txt = st.session_state.get(input_key, "").strip()
    if not txt:
        # mark a per-mail warning so main run can display it
        st.session_state[f"_send_warning_{mail_id}"] = "Please type a message before sending."
        return

    # clear any previous warning
    st.session_state.pop(f"_send_warning_{mail_id}", None)

    # append user message to history
    st.session_state[hist_key].append({"role": "user", "text": txt, "ts": time.time()})

    # clear input field (allowed inside callback)
    st.session_state[input_key] = ""

    # Prepare prompt to send to model: combine system prompt + user's message
    combined_prompt = ""
    for m in st.session_state[hist_key]:
        if m.get("role") == "system":
            combined_prompt = m.get("text") + "\n\n"
            break
    combined_prompt += "USER QUERY:\n" + txt + "\n\nRespond succinctly and in a professional tone."

    # call LLM (store results/errors into session state so main run can react)
    try:
        if agent_call is None:
            ai_text = "LLM not configured. Install connection_gateway for live responses."
        else:
            try:
                if loader and hasattr(loader, "_throttle"):
                    try:
                        loader._throttle()
                    except Exception:
                        pass
            except Exception:
                pass
            out = agent_call(combined_prompt)
            ai_text = _extract_text_from_call_output(out).strip()
            if ai_text == "":
                ai_text = "(empty response from model)"

        # append AI response
        st.session_state[hist_key].append({"role": "ai", "text": ai_text, "ts": time.time()})
        # signal success so main run can rerun and display messages immediately
        st.session_state[f"_send_success_{mail_id}"] = True
    except Exception as e:
        st.session_state[hist_key].append({"role": "ai", "text": f"Error: {e}", "ts": time.time()})
        st.session_state[f"_send_error_{mail_id}"] = str(e)


# Render the input widget (bound to session state key)
user_input = st.text_input("Your question or instruction", value=st.session_state[input_key], key=input_key)

col1, col2, col3 = st.columns([1,1,1])
with col1:
    # Use on_click callback to perform send logic (so clearing session_state key is legal)
    st.button("Send", key=f"send_{mail_id}", on_click=_send_callback, use_container_width=True)
with col2:
    if st.button("Save Chat as Draft Body", key=f"savechat_{mail_id}", use_container_width=True):
        # Optionally allow saving last AI output into draft body (only if mail is draft)
        if (mail.get("category") or "").lower() != "draft":
            st.warning("Can only save chat text into body for draft mails.")
        else:
            # find last AI message
            last_ai = None
            for m in reversed(st.session_state[hist_key]):
                if m.get("role") == "ai":
                    last_ai = m.get("text")
                    break
            if last_ai:
                if update_mail is None:
                    st.error("update_mail not available; cannot save draft.")
                else:
                    try:
                        ok = update_mail(mail_id, {"body": last_ai})
                        if ok:
                            st.success("Saved last AI response into draft body.")
                            st.rerun()
                        else:
                            st.error("Failed to save draft body (mail not found).")
                    except Exception as e:
                        st.error(f"Failed to save draft body: {e}")
            else:
                st.warning("No AI response in chat to save.")
with col3:
    if st.button("Clear Chat (session only)", key=f"clearchat_{mail_id}", use_container_width=True):
        # preserve system prompt, drop other messages
        sys_prompt = None
        for m in st.session_state[hist_key]:
            if m.get("role") == "system":
                sys_prompt = m
                break
        st.session_state[hist_key] = [sys_prompt] if sys_prompt else []
        st.rerun()

# After rendering buttons, check for any flags the callback set and react accordingly.
# Show warnings/errors and rerun if we recorded a successful send (so chat updates display).
warn = st.session_state.pop(f"_send_warning_{mail_id}", None)
if warn:
    st.warning(warn)

err = st.session_state.pop(f"_send_error_{mail_id}", None)
if err:
    st.error(f"LLM call failed: {err}")

if st.session_state.pop(f"_send_success_{mail_id}", False):
    # A message was sent & AI response appended; rerun to render updated chat history.
    st.rerun()

# End of file
