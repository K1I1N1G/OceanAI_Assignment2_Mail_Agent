# UI/home.py
import os
import streamlit as st
from datetime import datetime
from textwrap import shorten
import html
import time
import json

# import CSS blocks from separate module
from UI.homecss import font_css, card_css, bottom_editor_css

# import helper functions from separate module
from UI.homefunc import (
    fmt_ts,
    local_delete_mail,
    local_update_mail,
    _show_backend_modal_if_needed,
    default_build_right_side_html,
    _reset_fields_for_prompt_change,  # NEW: prompt-change reset helper (kept for backwards compat)
)

# New: small helper module that builds the right-side HTML inside the card
# (keeps visual elements inside the card to avoid overflow/bleed issues)
try:
    from Backend.helper import build_right_side_html
except Exception:
    # fallback: use default builder from homefunc so imports don't break if helper missing
    build_right_side_html = default_build_right_side_html

# Try to import delete_mail (compat: top-level or Data_Storage_Vault package)
try:
    from delete_mail import delete_mail
except Exception:
    try:
        from Data_Storage_Vault.delete_mail import delete_mail
    except Exception:
        delete_mail = None  # safe fallback; deletion will be disabled if unavailable

# Try to import update_mail (for the edit flow). fallbacks: top-level, Data_Storage_Vault, or loader.update_mail
try:
    from update_mail import update_mail
except Exception:
    try:
        from Data_Storage_Vault.update_mail import update_mail
    except Exception:
        # will fall back to local_update_mail in the edit handler
        update_mail = None

# Try to import update_prompt for prompt_library.json updates
try:
    from update_prompt import update_prompt
except Exception:
    try:
        from Data_Storage_Vault.update_prompt import update_prompt
    except Exception:
        update_prompt = None

# Try to import backend mailbox reset helpers (for prompt-change behavior)
try:
    from Backend.load_mail import (
        drop_categories_on_categorizer_prompt_change,
        drop_action_items_on_action_prompt_change,
        reset_draftable_on_drafter_prompt_change,
        process_mails_sequentially,
    )
except Exception:
    # Safe no-op fallbacks so UI still runs even if backend helpers are missing
    def drop_categories_on_categorizer_prompt_change():
        pass

    def drop_action_items_on_action_prompt_change():
        pass

    def reset_draftable_on_drafter_prompt_change():
        pass

    def process_mails_sequentially():
        pass

# --------------------------------------------------------------------
# Helper to clear all "draftable" values when prompts change
# (kept for backward compatibility but no longer used; we now use
#  backend reset helpers instead for precise behavior)
# --------------------------------------------------------------------
def _clear_draftable_in_obj(obj):
    """Recursively set any 'draftable' field to empty string in nested dict/list."""
    if isinstance(obj, dict):
        if "draftable" in obj:
            obj["draftable"] = ""
        for v in obj.values():
            _clear_draftable_in_obj(v)
    elif isinstance(obj, list):
        for item in obj:
            _clear_draftable_in_obj(item)


def _clear_draftable_flags():
    """
    Locate mail_inbox.json in common locations and clear all 'draftable' values.
    Runs once right before reload after prompts are saved.
    """
    candidates = [
        "mail_inbox.json",
        os.path.join("Data_Storage_Vault", "mail_inbox.json"),
        os.path.join("Data_Storage_Vault", "Data_Storage_Vault", "mail_inbox.json"),
        os.path.join("Data_Storage_Vault", "vault", "mail_inbox.json"),
    ]
    inbox_path = None
    for p in candidates:
        if os.path.exists(p):
            inbox_path = p
            break
    if inbox_path is None:
        # nothing to clear if inbox file doesn't exist yet
        return False

    try:
        with open(inbox_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False

    _clear_draftable_in_obj(data)

    try:
        with open(inbox_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

# --------------------------------------------------------------------
# Auto-refresh / polling so the Streamlit script re-runs and picks up backend errors.
# Tries to use streamlit-autorefresh (clean). Falls back to a small client-side poll script.
# --------------------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh
    # Auto-refresh every 2 seconds (2000 ms). Causes Streamlit to re-run and re-check loader error status.
    st_autorefresh(interval=2000, key="autorefresh")
except Exception:
    # fallback: inject a small script that fetches the current page periodically to keep the server-client
    # in sync; this will make the app more responsive to changes in the backend's in-memory/file signal.
    try:
        st.markdown(
            """
            <script>
            // Poll the server every 2.5s (no full reload). This fetch helps server-side state refresh behavior.
            // If you prefer a full-page reload fallback, replace fetch(...) with location.reload().
            setInterval(function(){
                fetch(window.location.href, {cache: "no-store"}).then(()=>{/* no-op */}).catch(()=>{/* ignore */});
            }, 2500);
            </script>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        # if even injection fails, silently skip (UI still works but modal may not auto-appear)
        pass

# Keep a single set_page_config call (Streamlit requires only one)
st.set_page_config(page_title="OceanAI_Mail_Agent — Inbox", layout="wide")

# Apply global font and header CSS from homecss.py
st.markdown(font_css, unsafe_allow_html=True)

# Hide Streamlit's widget instruction hints (like Ctrl+Enter) globally
st.markdown(
    """
    <style>
    /* Hide any Streamlit widget instructions such as "Press Ctrl+Enter to apply" */
    div[data-testid="stWidgetInstructions"],
    [data-testid="stWidgetInstructions"],
    div[data-testid="stWidgetInstructions"] * {
        display: none !important;
        visibility: hidden !important;
        font-size: 0 !important;
        line-height: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Render custom header (white, thick, pretty)
st.markdown('<div class="oceanai-header">OceanAI_Mail_Agent</div>', unsafe_allow_html=True)

# session defaults
if "_reload_counter" not in st.session_state:
    st.session_state["_reload_counter"] = 0
# keep last-read backend error timestamp so modal can reappear on new errors
if "_backend_error_ts" not in st.session_state:
    st.session_state["_backend_error_ts"] = 0.0
if "llm_modal_dismissed" not in st.session_state:
    st.session_state["llm_modal_dismissed"] = False

# flag set when prompts are just saved (so we know to show a message)
if "prompts_just_saved" not in st.session_state:
    st.session_state["prompts_just_saved"] = False

# store last time a prompt-triggered reload finished (for visible confirmation)
if "last_prompt_reload_ts" not in st.session_state:
    st.session_state["last_prompt_reload_ts"] = ""

# Immediately attempt to show backend modal/banner if needed (will appear on load and on subsequent auto-refresh)
_show_backend_modal_if_needed()

# Support quick actions via query params for the embedded HTML icons.
# If user clicked an embedded anchor like ?edit_mail=123 or ?delete_mail=123, handle it.
# NOTE: use the stable st.query_params / st.set_query_params APIs (do not mix experimental_* versions).
qp = st.query_params
if "delete_mail" in qp:
    try:
        did_list = qp.get("delete_mail")
        did = int(did_list[0]) if isinstance(did_list, list) else int(did_list)
        # silent best-effort delete; no user-facing error/success to avoid residue
        try:
            if delete_mail is None:
                _ = local_delete_mail(did)
            else:
                _ = delete_mail(did)
        except Exception:
            pass
    except Exception:
        # ignore invalid param silently
        pass
    # clear query params and rerun, staying on same page
    try:
        st.set_query_params()
    except Exception:
        pass
    st.session_state["_reload_counter"] = st.session_state.get("_reload_counter", 0) + 1
    st.session_state.pop("selected_mail", None)
    st.rerun()

if "edit_mail" in qp:
    try:
        eid = int(qp.get("edit_mail")[0])
        # set session flags to open persistent modal and stash payload for edit
        st.session_state[f"open_edit_{eid}"] = True
        # attempt to load the mail and store copy as payload
        try:
            from Backend.load_mail import fast_return_mails
            allm = fast_return_mails()
            found = None
            for mm in allm:
                try:
                    if int(mm.get("id")) == eid:
                        found = mm
                        break
                except Exception:
                    if mm.get("id") == eid:
                        found = mm
                        break
            if found:
                st.session_state[f"edit_payload_{eid}"] = found.copy()
        except Exception:
            # best-effort: leave payload absent and rely on existing mails list later
            pass
    except Exception:
        st.error("Invalid edit_mail parameter.")
    # clear query params and rerun so UI shows modal in persistent render section
    try:
        st.set_query_params()
    except Exception:
        pass
    st.rerun()


def _load_prompt_library():
    """
    Load prompt_library.json from common locations.
    Returns (data, path_used).
    """
    default = {
        "prompts": [
            {"type": "categorization", "prompt": ""},
            {"type": "action_extraction", "prompt": ""},
            {"type": "auto_reply", "prompt": ""},
        ]
    }
    candidates = [
        os.path.join("Data_Storage_Vault", "prompt_library.json"),
        "prompt_library.json",
    ]
    data = None
    path_used = None
    for p in candidates:
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and "prompts" in loaded:
                    data = loaded
                else:
                    data = default
                path_used = p
                break
        except Exception:
            continue
    if data is None:
        data = default
        path_used = candidates[0]
    # ensure prompts list exists
    if "prompts" not in data or not isinstance(data["prompts"], list):
        data["prompts"] = default["prompts"]
    return data, path_used


def _save_prompt_library(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# Sidebar
with st.sidebar:
    st.header("Prompt Brain")
    st.caption("Edit prompts on Prompt page (or keep defaults).")

    # --- Prompt editor (three boxes bound to prompt_library.json) ---
    prompt_data, prompt_path = _load_prompt_library()
    existing = {p.get("type"): p.get("prompt", "") for p in prompt_data.get("prompts", [])}

    cat_prompt = st.text_area(
        "Categorization prompt",
        value=existing.get("categorization", ""),
        height=80,
        key="prompt_categorization",
    )
    action_prompt = st.text_area(
        "Action extraction prompt",
        value=existing.get("action_extraction", ""),
        height=80,
        key="prompt_action_extraction",
    )
    auto_prompt = st.text_area(
        "Auto-reply prompt",
        value=existing.get("auto_reply", ""),
        height=80,
        key="prompt_auto_reply",
    )

    if st.button("Save prompts", key="save_prompts"):
        # First try dedicated update_prompt helper if available
        success = False

        # Determine which prompt types actually changed (trim whitespace)
        cat_old = existing.get("categorization", "") or ""
        action_old = existing.get("action_extraction", "") or ""
        auto_old = existing.get("auto_reply", "") or ""
        category_changed = (cat_prompt or "").strip() != cat_old.strip()
        action_changed = (action_prompt or "").strip() != action_old.strip()
        auto_changed = (auto_prompt or "").strip() != auto_old.strip()

        if update_prompt is not None:
            try:
                update_prompt("categorization", cat_prompt)
                update_prompt("action_extraction", action_prompt)
                update_prompt("auto_reply", auto_prompt)
                success = True
            except Exception as e:
                st.error(f"update_prompt failed: {e}")

        # Fallback: write prompt_library.json directly
        if not success:
            try:
                data, path_used = _load_prompt_library()
                prompts_by_type = {p.get("type"): p for p in data.get("prompts", []) if isinstance(p, dict)}

                for t, text in [
                    ("categorization", cat_prompt),
                    ("action_extraction", action_prompt),
                    ("auto_reply", auto_prompt),
                ]:
                    if t in prompts_by_type:
                        prompts_by_type[t]["prompt"] = text
                    else:
                        data["prompts"].append({"type": t, "prompt": text})

                if _save_prompt_library(path_used, data):
                    success = True
                else:
                    st.error("Failed to save prompt_library.json.")
            except Exception as e:
                st.error(f"Error while saving prompts locally: {e}")

        if success:
            # Reset only the relevant mail fields according to which prompts changed
            try:
                if category_changed:
                    # Drop all categories except drafts
                    drop_categories_on_categorizer_prompt_change()
                if action_changed:
                    # Drop all action_items (including drafts)
                    drop_action_items_on_action_prompt_change()
                if auto_changed:
                    # Reset draftable for all mails
                    reset_draftable_on_drafter_prompt_change()

                # Kick off background re-processing so Agent_Brain uses updated prompts
                try:
                    process_mails_sequentially()
                except Exception:
                    pass
            except Exception as e:
                # Non-fatal: show error but still reload UI
                st.error(f"Failed to reset mail fields for changed prompts: {e}")

            st.success("Prompts saved. Reloading mails with updated prompts...")
            # mark that this rerun is because prompts were updated
            st.session_state["prompts_just_saved"] = True
            st.session_state["_reload_counter"] = st.session_state.get("_reload_counter", 0) + 1
            st.session_state.pop("selected_mail", None)
            st.rerun()

    # Persistent sign that a prompt-triggered reload happened
    if st.session_state.get("last_prompt_reload_ts"):
        st.caption(
            "Last prompt-triggered reload at "
            + fmt_ts(st.session_state["last_prompt_reload_ts"])
        )

    st.markdown("**Quick actions**")
    if st.button("Reload mails"):
        st.session_state["_reload_counter"] += 1
        st.session_state.pop("selected_mail", None)
    st.markdown("---")
    st.caption("Click a card to open the Chat page for that mail.")

# Page layout: single column of cards (no preview)
col1 = st.container()

# Visual CSS for clickable card + expand area (client-only)
# Small addition: .ocean-actions to align small emoji buttons inside the card visually.
st.markdown(card_css, unsafe_allow_html=True)

# Snapshot this early so we know if this run is from prompt save
_prompts_just_saved = st.session_state.get("prompts_just_saved", False)
if _prompts_just_saved:
    # We already reset fields on save; just show a hint that reprocessing is happening.
    st.caption("🔁 Reprocessing inbox with updated prompts...")

# Load mails (fast) and start background processing
try:
    from Backend.load_mail import load_and_process
    mails = load_and_process(start_background=True)
    # After load succeeds, if this was a prompt-triggered reload, show a clear confirmation
    if _prompts_just_saved:
        now_iso = datetime.now().isoformat()
        st.session_state["last_prompt_reload_ts"] = now_iso
        st.info(
            f"✅ Inbox reloaded with updated prompts at {datetime.now().strftime('%H:%M:%S')}."
        )
        # reset the flag so this only happens once per save
        st.session_state["prompts_just_saved"] = False
except Exception as e:
    st.error(f"Failed to load mails: {e}")
    mails = []

# Render cards
if not mails:
    st.info("No mails found.")
else:
    for m in mails:
        # Defensive fallbacks so explicit None doesn't break html.escape
        try:
            mail_id = int(m.get("id"))
        except Exception:
            # skip items with invalid id
            continue
        sender = m.get("sender") or "Unknown"
        subject = m.get("subject") or "(no subject)"
        ts = fmt_ts(m.get("timestamp") or "")
        category = m.get("category") or ""
        has_actions = bool(m.get("has_action_items", False))

        # Defensive body extraction: prefer canonical 'body' but fallback to 'full' if needed
        body_raw = m.get("body") or (m.get("full") and (m.get("full").get("body") or m.get("full").get("text"))) or ""

        # Expanded state for this mail (controls preview visibility)
        expanded_key = f"expanded_{mail_id}"
        expanded = st.session_state.get(expanded_key, False)

        # Use html.escape + preserve newlines for preview;
        # when expanded, show full body; when collapsed, show shortened version.
        if expanded:
            body_preview = html.escape(str(body_raw or "")).replace("\n", "<br>")
        else:
            body_preview = html.escape(shorten(str(body_raw or ""), width=600)).replace("\n", "<br>")

        # Small snippet shown on the card (top).
        snippet_text = html.escape(shorten(str(body_raw or ""), width=140)).replace("\n", " ")

        ais = m.get("action_items", []) or []
        if ais:
            ais_html = "<ul style='margin:6px 0 0 18px;'>"
            for it in ais:
                if isinstance(it, dict):
                    t_val = it.get("task") if it.get("task") is not None else it.get("title", "")
                    d_val = it.get("deadline") if it.get("deadline") is not None else it.get("due", "")
                    t = html.escape(str(t_val))
                    d = html.escape(str(d_val))
                    if d:
                        ais_html += f"<li>{t} <small style='color:rgba(255,255,255,0.6);'>— {d}</small></li>"
                    else:
                        ais_html += f"<li>{t}</li>"
                else:
                    # if item is plain string or other type
                    ais_html += f"<li>{html.escape(str(it))}</li>"
            ais_html += "</ul>"
        else:
            ais_html = "<div style='color:rgba(255,255,255,0.6); margin-top:6px;'>No action items</div>"

        # Only show category tag if present (UI requirement)
        category_html = f"<span class='ocean-category'>{html.escape(category)}</span>" if category else ""
        tasks_html = "<span class='ocean-has-tasks'>● has tasks</span>" if has_actions else ""

        # Keep navigation behavior unchanged
        href = f"?page=chat&mail_id={mail_id}"

        # Build action HTML only when appropriate (edit/delete inside card)
        # Edit should only appear for draft mails (user requested)
        try:
            is_draft = (category or "").lower() == "draft"
        except Exception:
            is_draft = False

        actions_html = ""
        if is_draft:
            # For drafts we no longer put delete here; we use Streamlit buttons below the card.
            actions_html = """
<div class="ocean-actions">
</div>
"""
        else:
            # Non-drafts: no edit, no delete icon (keeps UI clean)
            actions_html = ""

        # Expanded state for this mail (controls preview visibility)
        preview_class = "ocean-hover-reveal expanded" if expanded else "ocean-hover-reveal"
        expand_label = "▴ Hide" if expanded else "▾ Expand"

        # Build the right-side HTML (inside the card) using helper to ensure alignment
        right_side_html = build_right_side_html(ts, category_html, tasks_html)

        # Build the card HTML (without the expand control; that will be a Streamlit button)
        raw_card_html = f"""
<div class="ocean-card" id="mail_card_{mail_id}">
{actions_html}
<div class="ocean-row">
  <div class="ocean-left">
    <a href="{href}" style="color:inherit; text-decoration:none;">
      <div class="ocean-sender">{html.escape(sender)}</div>
      <div class="ocean-subject">{html.escape(subject)}</div>
      <div class="ocean-snippet">{snippet_text}</div>
    </a>
  </div>
</div>
{right_side_html}
<div class="{preview_class}">
  <div style="margin-top:8px;"><strong>Preview:</strong></div>
  <div style="margin-top:6px; white-space:pre-wrap;">{body_preview}</div>
  <div style="margin-top:8px;"><strong>Action Items:</strong>{ais_html}</div>
</div>
</div>
"""
        # Important fix:
        # Streamlit's markdown treats leading indentation in a multiline string as a code block.
        # To ensure the HTML is rendered (not escaped as a code block), strip leading indentation
        # from each line before passing to st.markdown. This preserves the HTML while not altering
        # the visual/html content.
        card_html = "\n".join(line.lstrip() for line in raw_card_html.splitlines())

        # Use a container so we can place the card HTML and then Streamlit controls if needed.
        card_container = col1.container()
        card_container.markdown(card_html, unsafe_allow_html=True)

        # Expand/Hide button directly under the card (same page toggle)
        # Make it full-width to visually match the card width
        if card_container.button(expand_label, key=f"expand_btn_{mail_id}", use_container_width=True):
            st.session_state[expanded_key] = not expanded
            st.rerun()

        # keep small placeholder height if not draft (keeps vertical rhythm)
        if not is_draft:
            card_container.markdown("<div style='height:34px'/>", unsafe_allow_html=True)
        else:
            # For drafts: show Streamlit delete + edit buttons on the same row, stretched to card width
            btn_cols = card_container.columns([1, 1])
            with btn_cols[0]:
                if st.button("🗑️ Delete draft", key=f"delete_btn_{mail_id}", use_container_width=True):
                    try:
                        if delete_mail is None:
                            _ = local_delete_mail(mail_id)
                        else:
                            _ = delete_mail(mail_id)
                    except Exception:
                        pass
                    st.session_state["_reload_counter"] = st.session_state.get("_reload_counter", 0) + 1
                    st.session_state.pop("selected_mail", None)
                    st.rerun()
            with btn_cols[1]:
                if st.button("✏️ Edit draft", key=f"edit_btn_{mail_id}", use_container_width=True):
                    # open inline editor for this mail
                    st.session_state[f"open_edit_{mail_id}"] = True
                    st.session_state[f"edit_payload_{mail_id}"] = m.copy()
                    st.rerun()

        # Inline editor panel shown directly below this mail if flag is set
        flag_key = f"open_edit_{mail_id}"
        payload_key = f"edit_payload_{mail_id}"
        if st.session_state.get(flag_key, False):
            payload = st.session_state.get(payload_key, m.copy())
            cur_sender = payload.get("sender") or ""
            cur_subject = payload.get("subject") or ""
            cur_body = payload.get("body") or (
                payload.get("full") and (payload.get("full").get("body") or payload.get("full").get("text"))
            ) or ""

            # Inject CSS + placeholder div for the inline editor right under this card
            bottom_css = bottom_editor_css(mail_id)
            card_container.markdown(bottom_css, unsafe_allow_html=True)

            # Functional Streamlit inputs rendered in a container that sits visually under the card
            with card_container.container():
                st.markdown(f"<div style='height:8px'></div>", unsafe_allow_html=True)
                st.markdown(
                    f"### Editing draft {mail_id} — category locked to `draft` (saved automatically on Save).",
                    unsafe_allow_html=True,
                )
                sender_in = st.text_input("Sender", value=cur_sender, key=f"bottom_sender_{mail_id}")
                subject_in = st.text_input("Subject", value=cur_subject, key=f"bottom_subject_{mail_id}")
                body_in = st.text_area("Body", value=cur_body, height=160, key=f"bottom_body_{mail_id}")
                st.text_input(
                    "Category (will remain 'draft')",
                    value="draft",
                    disabled=True,
                    key=f"bottom_cat_{mail_id}",
                )
                cols = st.columns([1, 1, 1])
                with cols[0]:
                    if st.button("Save changes", key=f"bottom_save_{mail_id}"):
                        updated = payload.copy()
                        updated["sender"] = sender_in
                        updated["subject"] = subject_in
                        updated["body"] = body_in
                        updated["action_items"] = []
                        updated_ts = datetime.now().isoformat()
                        updated["timestamp"] = updated_ts
                        updated["category"] = "draft"

                        if update_mail is None:
                            ok = local_update_mail(mail_id, updated)
                            if ok:
                                st.success("Mail updated (local fallback).")
                                st.session_state["_reload_counter"] = st.session_state.get(
                                    "_reload_counter", 0
                                ) + 1
                                st.session_state.pop("selected_mail", None)
                                st.session_state[flag_key] = False
                                st.session_state.pop(payload_key, None)
                                st.rerun()
                            else:
                                st.error(
                                    "Local update failed. Ensure mail_inbox.json is writable or provide update_mail implementation."
                                )
                        else:
                            try:
                                ok = update_mail(mail_id, updated)
                                if ok:
                                    st.success("Mail updated.")
                                    st.session_state["_reload_counter"] = st.session_state.get(
                                        "_reload_counter", 0
                                    ) + 1
                                    st.session_state.pop("selected_mail", None)
                                    st.session_state[flag_key] = False
                                    st.session_state.pop(payload_key, None)
                                    st.rerun()
                                else:
                                    st.error("Update failed (update_mail returned falsy).")
                            except Exception as e:
                                st.error(f"Update failed: {e}")
                with cols[1]:
                    if st.button("Cancel", key=f"bottom_cancel_{mail_id}"):
                        st.session_state[flag_key] = False
                        st.session_state.pop(payload_key, None)
                        st.rerun()
                with cols[2]:
                    st.markdown("**Preview**")
                    preview = html.escape(shorten(str(body_in or ""), width=300)).replace("\n", "<br>")
                    st.markdown(
                        f"<div style='white-space:pre-wrap; color: #fff;'>{preview}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        "<small>Category locked. Save sets timestamp to now and keeps category 'draft'.</small>",
                        unsafe_allow_html=True,
                    )
