# Backend/load_mail.py
"""
Thin shim that re-exports the loader functions which are implemented in mail_func.py.

This file intentionally contains minimal logic so your UI can continue importing
from Backend.load_mail as before while the real implementation lives in mail_func.py.
"""

# Import public API from mail_func (must be in same directory)
from .mail_func import (  # relative import; if run as script adjust as needed
    load_and_process,
    fast_return_mails,
    get_last_error,
    set_last_error,
    clear_last_error,
    process_mails_sequentially,
)

# --------------------- NEW LOGIC FOR ITERATION 2 ---------------------
# (Only added; no previous logic touched)

import json
import os
from pathlib import Path

# Try multiple locations for mail_inbox.json, just like _clear_draftable_flags in home.py
_CANDIDATE_MAILBOX_PATHS = [
    Path("mail_inbox.json"),
    Path("Data_Storage_Vault") / "mail_inbox.json",
    Path("Data_Storage_Vault") / "Data_Storage_Vault" / "mail_inbox.json",
    Path("Data_Storage_Vault") / "vault" / "mail_inbox.json",
]


def _find_mailbox_path() -> Path | None:
    """
    Find the first existing mailbox file among known candidate paths.
    Returns a Path or None if none exist.
    """
    for p in _CANDIDATE_MAILBOX_PATHS:
        if p.exists():
            return p
    return None


def _load_mailbox():
    mailbox_path = _find_mailbox_path()
    if mailbox_path is None:
        return None
    try:
        with mailbox_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_mailbox(data):
    """
    Save back to the same location we would normally read from.
    If no mailbox exists yet, default to the first candidate (mail_inbox.json).
    """
    mailbox_path = _find_mailbox_path()
    if mailbox_path is None:
        mailbox_path = _CANDIDATE_MAILBOX_PATHS[0]

    try:
        mailbox_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    try:
        with mailbox_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def drop_categories_on_categorizer_prompt_change():
    """
    Rule:
    - If categorization prompt is modified → drop ALL category values from all mails
    - EXCEPT where category == 'draft'
    """
    data = _load_mailbox()
    if not data:
        return

    changed = False
    for mail in data.get("emails", []):
        if mail.get("category") == "draft":
            continue

        if mail.get("category") not in (None, ""):
            mail["category"] = ""
            changed = True

    if changed:
        _save_mailbox(data)


def drop_action_items_on_action_prompt_change():
    """
    Rule:
    - If action-item prompt is modified → drop action_items for ALL mails (including drafts)
    """
    data = _load_mailbox()
    if not data:
        return

    changed = False
    for mail in data.get("emails", []):
        if mail.get("action_items"):
            mail["action_items"] = []
            changed = True

    if changed:
        _save_mailbox(data)


def reset_draftable_on_drafter_prompt_change():
    """
    Rule:
    - If mail drafter prompt is modified → set draftable="" for ALL mails.
      (Draft categories remain unchanged.)
    """
    data = _load_mailbox()
    if not data:
        return

    changed = False
    for mail in data.get("emails", []):
        if "draftable" in mail and mail["draftable"] != "":
            mail["draftable"] = ""
            changed = True

    if changed:
        _save_mailbox(data)


# ---------------------------------------------------------------------

# Re-export names for convenience if other modules import Backend.load_mail
__all__ = [
    "load_and_process",
    "fast_return_mails",
    "get_last_error",
    "set_last_error",
    "clear_last_error",
    "process_mails_sequentially",

    # NEW exports so UI can call them
    "drop_categories_on_categorizer_prompt_change",
    "drop_action_items_on_action_prompt_change",
    "reset_draftable_on_drafter_prompt_change",
]
