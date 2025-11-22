# app.py — Streamlit app router (root)
import streamlit as st
import runpy
from pathlib import Path
import sys
import traceback

st.set_page_config(page_title="OceanAI", layout="wide")

ROOT = Path(__file__).resolve().parent
UI_HOME = ROOT / "UI" / "home.py"
UI_CHAT = ROOT / "UI" / "chat.py"

def _safe_run_file(file_path: Path):
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        return runpy.run_path(str(file_path), run_name="__main__")
    except Exception as e:
        st.error(f"Error running {file_path.name}: {e}")
        st.write(traceback.format_exc())
        return None

# Decide initial page from query params so ?page=chat opens Chat on startup
try:
    q = st.query_params  # new API for reading query params
except Exception:
    q = {}

initial_page = "Home"
if "page" in q:
    val = q.get("page")
    try:
        p = val[0].lower() if isinstance(val, list) else str(val).lower()
        if p == "chat":
            initial_page = "Chat"
    except Exception:
        initial_page = "Home"

st.sidebar.title("OceanAI")
st.sidebar.markdown("Navigation")

page = st.sidebar.radio("Go to", ["Home", "Chat"], index=0 if initial_page == "Home" else 1)

if page == "Home":
    st.sidebar.write("Showing inbox")
    if UI_HOME.exists():
        _safe_run_file(UI_HOME)
    else:
        st.error("UI/home.py not found.")
elif page == "Chat":
    st.sidebar.write("Agent chat")
    if UI_CHAT.exists():
        _safe_run_file(UI_CHAT)
    else:
        st.error("UI/chat.py not found.")
