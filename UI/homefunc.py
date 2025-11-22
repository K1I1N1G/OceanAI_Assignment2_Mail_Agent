# UI/homefunc.py
import html
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

# Import backend loader module so we can query its in-memory error status
# (do this lazily inside try/except to avoid import-time failures stopping the UI)
try:
    import Backend.load_mail as loader
except Exception:
    loader = None


# Fallback: default builder for right-side HTML inside the card
# (used by home.py if Backend.helper.build_right_side_html is unavailable)
def default_build_right_side_html(ts, category_html, tasks_html):
    right = f"<div class='ocean-right'><div class='ocean-ts'>{html.escape(ts)}</div>{category_html}{tasks_html}</div>"
    return right


# --------------------------------------------------------------------
# LOCAL FALLBACKS FOR delete_mail / update_mail (operate on mail_inbox.json)
# These are used only if the imported functions are unavailable.
# They attempt to find the project's mail_inbox.json in a few common locations
# and perform the requested operation, returning truthy on success.
# --------------------------------------------------------------------
def _find_inbox_path():
    """Try to locate mail_inbox.json in likely project locations."""
    candidates = [
        Path("mail_inbox.json"),
        Path("Data_Storage_Vault") / "mail_inbox.json",
        Path("Data_Storage_Vault") / "Data_Storage_Vault" / "mail_inbox.json",
        Path("Data_Storage_Vault") / "vault" / "mail_inbox.json",
    ]
    # Also check loader's known path if available
    try:
        if loader and hasattr(loader, "INBOX_PATH"):
            candidates.insert(0, Path(getattr(loader, "INBOX_PATH")))
    except Exception:
        pass

    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    # if none exists, prefer the first candidate as the place to create one if needed
    return candidates[0]


def _read_inbox(path):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            # possible shapes: {"emails":[...], "counter":n} or list
            if isinstance(data, dict) and "emails" in data:
                return data
            else:
                # wrap list into dict for consistent writes
                if isinstance(data, list):
                    return {"emails": data}
                # unknown shape: try to coerce
                return {"emails": list(data.values()) if isinstance(data, dict) else []}
    except FileNotFoundError:
        return {"emails": []}
    except Exception:
        # if parse error, return empty but do not overwrite; caller may handle
        return {"emails": []}


def _write_inbox(path, payload):
    try:
        # Ensure parent exists
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def local_delete_mail(mail_id):
    """Fallback delete: remove mail with id from mail_inbox.json. Returns True on success."""
    try:
        inbox_path = _find_inbox_path()
        data = _read_inbox(inbox_path)
        emails = data.get("emails", [])
        new_emails = [e for e in emails if str(e.get("id")) != str(mail_id)]
        if len(new_emails) == len(emails):
            return False  # nothing removed
        data["emails"] = new_emails
        ok = _write_inbox(inbox_path, data)
        return ok
    except Exception:
        return False


def local_update_mail(mail_id, updated):
    """Fallback update: replace mail with id in mail_inbox.json. Returns True on success."""
    try:
        inbox_path = _find_inbox_path()
        data = _read_inbox(inbox_path)
        emails = data.get("emails", [])
        found = False
        for i, e in enumerate(emails):
            if str(e.get("id")) == str(mail_id):
                # preserve any keys not provided in updated
                merged = e.copy()
                merged.update(updated)
                emails[i] = merged
                found = True
                break
        if not found:
            # If not found, append as new mail (best-effort)
            emails.append(updated)
        data["emails"] = emails
        ok = _write_inbox(inbox_path, data)
        return ok
    except Exception:
        return False


# helper: format timestamp (safe fallback)
def fmt_ts(ts):
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return ts


def _get_backend_error():
    """Return backend last error dict or None (safe).
    Strategy:
      1) Prefer in-memory loader.get_last_error()
      2) Fallback to loader.ERROR_SIGNAL_PATH on disk (if available)
    This makes the UI robust to import/module caching or thread-sync edge cases.
    """
    # 1) in-memory fast check
    try:
        if loader:
            try:
                err = loader.get_last_error()
                if err:
                    return err
            except Exception:
                # ignore and fall back to file
                pass
    except Exception:
        pass

    # 2) on-disk fallback (tolerant)
    try:
        if loader and hasattr(loader, "ERROR_SIGNAL_PATH"):
            path = getattr(loader, "ERROR_SIGNAL_PATH")
            if path and path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    # ensure minimal shape
                    msg = data.get("message") or data.get("msg") or str(data)
                    ts = float(data.get("timestamp", 0) or 0)
                    return {"message": msg, "timestamp": ts}
                except Exception:
                    # if file corrupt, ignore (do not crash UI)
                    return None
    except Exception:
        pass

    return None


def _show_backend_modal_if_needed():
    """
    If backend reports an error via loader.get_last_error(), show a modal popup.
    The modal is dismissible and bound to the error timestamp so it reappears for new errors.
    """
    err = _get_backend_error()
    if not err:
        # if previously shown and now cleared, reset dismissal
        st.session_state["llm_modal_dismissed"] = False
        st.session_state["_backend_error_ts"] = 0.0
        return

    ts = float(err.get("timestamp", 0) or 0)
    # If there's a new error timestamp, reset dismissal so modal can reappear
    if ts != st.session_state.get("_backend_error_ts", 0.0):
        st.session_state["_backend_error_ts"] = ts
        st.session_state["llm_modal_dismissed"] = False

    if st.session_state.get("llm_modal_dismissed", False):
        return

    msg = err.get("message") or "LLM API quota/token exhausted or billing error."

    # Use Streamlit modal when available so buttons are clickable
    try:
        with st.modal("⚠️ LLM API problem", clear_on_submit=False):
            st.write("Draft generation is paused until the LLM API issue is resolved.")
            st.markdown(f"**Details:** {msg}")
            st.markdown("---")
            col1, col2 = st.columns([1, 1])
            if col1.button("Re-check LLM status / Reload mails"):
                # trigger a UI refresh by bumping reload counter
                st.session_state["_reload_counter"] = st.session_state.get("_reload_counter", 0) + 1
                st.session_state.pop("selected_mail", None)
                st.session_state["llm_modal_dismissed"] = True
            if col2.button("Dismiss"):
                st.session_state["llm_modal_dismissed"] = True
        return
    except Exception:
        # Fallback: render a warning banner with functional buttons (server-side)
        st.warning(f"⚠️ LLM API problem — {msg}\n\nDraft generation is paused until resolved.")
        col1, col2 = st.columns([1, 1])
        if col1.button("Re-check LLM status / Reload mails (server)"):
            st.session_state["_reload_counter"] = st.session_state.get("_reload_counter", 0) + 1
            st.session_state.pop("selected_mail", None)
            st.session_state["llm_modal_dismissed"] = True
        if col2.button("Dismiss (server)"):
            st.session_state["llm_modal_dismissed"] = True
        return


# --------------------------------------------------------------------
# NEW: helper to reset derived fields when prompts change
# --------------------------------------------------------------------
def reset_mail_fields_on_prompt_change(cat_changed: bool, action_changed: bool, auto_changed: bool) -> bool:
    """
    Reset derived fields in mail_inbox.json when prompts change.

    Rules:
      - If categorization prompt changed:
          For all mails where category != "draft":
              category -> ""
      - If action-extraction prompt changed:
          For ALL mails (including drafts):
              action_items -> []
      - If auto-reply prompt changed:
          For all mails where category != "draft":
              draftable -> ""
    """
    try:
        inbox_path = _find_inbox_path()
        data = _read_inbox(inbox_path)
        emails = data.get("emails", [])
        changed = False

        for e in emails:
            cat_val = e.get("category") or ""
            cat_lower = str(cat_val).lower()

            # Categorization prompt changed → clear category for non-drafts
            if cat_changed and cat_lower != "draft":
                if e.get("category", "") != "":
                    e["category"] = ""
                    changed = True

            # Action prompt changed → clear action_items for all mails
            if action_changed:
                if e.get("action_items") not in ([], None):
                    e["action_items"] = []
                    changed = True

            # Auto-reply prompt changed → clear draftable for non-drafts
            if auto_changed and cat_lower != "draft":
                if e.get("draftable", "") != "":
                    e["draftable"] = ""
                    changed = True

        if not changed:
            # Nothing to write; treat as success
            return True

        data["emails"] = emails
        return _write_inbox(inbox_path, data)
    except Exception:
        return False


# Small compatibility wrapper for home.py
def _reset_fields_for_prompt_change(cat_changed: bool, action_changed: bool, auto_changed: bool) -> bool:
    """
    Backwards-compatible alias for reset_mail_fields_on_prompt_change,
    so existing imports in home.py keep working.
    """
    return reset_mail_fields_on_prompt_change(cat_changed, action_changed, auto_changed)
