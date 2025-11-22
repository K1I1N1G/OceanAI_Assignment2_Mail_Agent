# Backend/prompter.py
"""
Generate a concise, LLM-ready prompt from a mail UI object.

Expected input: a mail UI object as produced by load_mail.fast_return_mails()/_make_ui_object(),
i.e. a dict with keys like: id, sender, subject, timestamp, category, action_items (list),
body (string), full (original mail dict). The function returns a string prompt suitable
for prepending to user queries in the chat pane.

Designed to be lightweight and importable from the Backend package.
"""

from typing import Dict, Any, List, Optional
import json
import textwrap
from datetime import datetime


def _format_action_items(ais: List[Dict[str, Any]]) -> str:
    if not ais:
        return "None."
    lines = []
    for i, a in enumerate(ais, start=1):
        task = a.get("task") if isinstance(a, dict) else str(a)
        deadline = a.get("deadline") if isinstance(a, dict) else None
        if deadline is None or deadline == "":
            lines.append(f"{i}. {task}")
        else:
            lines.append(f"{i}. {task} (deadline: {deadline})")
    return "\n".join(lines)


def _safe_str(x: Optional[Any]) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    try:
        return str(x)
    except Exception:
        return ""


def generate_prompt_from_mail(mail_ui: Dict[str, Any], include_instructions: bool = True) -> str:
    """
    Build a short but information-dense prompt describing the mail for use in chat.

    - mail_ui: UI mail object (see above).
    - include_instructions: if True, prepend a brief system-like instruction telling the model
      its role (editing/drafting). Set False if you only want the raw mail summary.

    Returns: multi-line string prompt.
    """

    # Defensive defaults
    if not isinstance(mail_ui, dict):
        raise ValueError("mail_ui must be a dict-like object representing the UI mail.")

    mail_id = _safe_str(mail_ui.get("id"))
    sender = _safe_str(mail_ui.get("sender") or mail_ui.get("from") or "")
    subject = _safe_str(mail_ui.get("subject") or "")
    timestamp = _safe_str(mail_ui.get("timestamp") or "")
    category = _safe_str(mail_ui.get("category") or "")
    body = _safe_str(mail_ui.get("body") or "")
    # action_items is normalized list of dicts or strings
    action_items = mail_ui.get("action_items") or mail_ui.get("full", {}).get("action_items") or []
    # draft metadata if present
    draft_for = mail_ui.get("full", {}).get("draft_for") or mail_ui.get("draft_for") or None
    draftable = mail_ui.get("full", {}).get("draftable") if isinstance(mail_ui.get("full", {}), dict) else None

    # Build header summary
    header_lines = [
        f"Mail ID: {mail_id}",
        f"From: {sender}",
        f"Subject: {subject}" if subject else "Subject: (none)",
        f"Timestamp: {timestamp}" if timestamp else "Timestamp: (unknown)",
        f"Category: {category}" if category else "Category: (unspecified)",
    ]

    # Action items
    ais_block = _format_action_items(action_items)

    # Draftable flag explanation
    draftable_status = "(unknown)"
    if draftable is None:
        draftable_status = "(empty)"
    elif draftable in (0, "0", False):
        draftable_status = "NO (0)"
    else:
        draftable_status = "YES (set)"

    # Compose the prompt body with whitespace-normalized mail body
    body_snippet = body.strip()
    if len(body_snippet) > 1000:
        # keep prompt compact: show first 1000 chars + note
        body_snippet = body_snippet[:1000].rstrip() + "\n\n[truncated]"

    # Human-friendly preamble/instructions (optional)
    instructions = ""
    if include_instructions:
        instructions = (
            "You are an assistant that helps draft or edit email replies. "
            "The original mail and extracted metadata follow. When the user adds a question "
            "you must answer or produce an edited draft. If the mail is NOT suitable for drafting, "
            "reply with the single word: INVALID\n\n"
        )

    # Final assembled prompt
    prompt_parts = [
        instructions,
        "=== MAIL SUMMARY BEGIN ===",
        *header_lines,
        "",
        "Body:",
        textwrap.indent(body_snippet, "  "),
        "",
        "Action items (extracted):",
        textwrap.indent(ais_block, "  "),
        "",
        f"Draftable flag: {draftable_status}",
    ]

    if draft_for is not None:
        prompt_parts.append(f"Draft for (link): {_safe_str(draft_for)}")

    prompt_parts.append("=== MAIL SUMMARY END ===")
    prompt_parts.append("")  # trailing newline for readability

    return "\n".join(prompt_parts)


# Convenience wrapper used by chat prompter to create a two-part payload:
def get_prompter_payload(mail_ui: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a payload dict with:
      - prompt: the generated prompt string (with instructions)
      - metadata: compact metadata dict (id, sender, subject, draftable)
    """
    metadata = {
        "id": mail_ui.get("id"),
        "sender": mail_ui.get("sender"),
        "subject": mail_ui.get("subject"),
        "draftable": (mail_ui.get("full") or {}).get("draftable"),
        "draft_for": (mail_ui.get("full") or {}).get("draft_for"),
    }
    return {"prompt": generate_prompt_from_mail(mail_ui, include_instructions=True), "metadata": metadata}


# Simple command-line test when run directly
if __name__ == "__main__":
    example = {
        "id": 42,
        "sender": "alice@example.com",
        "subject": "Project kickoff",
        "timestamp": "2025-11-24T10:00:00+05:30",
        "category": "important meeting mails",
        "body": "Hi team,\nCan we meet Monday at 10? Please confirm.\nThanks, Alice",
        "action_items": [{"task": "Confirm availability", "deadline": "Monday"}],
        "full": {"draftable": None},
    }
    payload = get_prompter_payload(example)
    print(payload["prompt"])
