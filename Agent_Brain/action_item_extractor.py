# action_item_extractor.py
# Uses action_extraction prompt to extract structured action items, validates, updates mail.action_items

import json
import re
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Agent_Brain.connection_gateway import call, ConnectionError
from Data_Storage_Vault.update_mail import update_mail

PROMPT_LIB = Path(__file__).resolve().parents[1] / "Data_Storage_Vault" / "prompt_library.json"
INBOX = Path(__file__).resolve().parents[1] / "Data_Storage_Vault" / "mail_inbox.json"

JSON_LIKE_RE = re.compile(r"[\{\[][\s\S]*[\}\]]", re.MULTILINE)  # crude JSON substring matcher

def _load_action_prompt():
    with PROMPT_LIB.open("r", encoding="utf-8") as f:
        d = json.load(f)
    for p in d.get("prompts", []):
        if p.get("type") == "action_extraction":
            return p.get("prompt", "")
    return ""

def _parse_json_from_text(text):
    """
    Attempt to extract JSON substring and parse it.
    Returns Python object or raises ValueError.
    """
    text = text.strip()
    # try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass
    # try to find first JSON-like substring
    m = JSON_LIKE_RE.search(text)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate)
        except Exception as e:
            raise ValueError(f"Found JSON-like text but failed to parse: {e}")
    raise ValueError("No JSON found in model output")

def action_item_extractor(mail_obj):
    """
    mail_obj: dict with 'id' and 'body'
    Returns list of action items (list of dicts).
    On success, updates mail.action_items via update_mail.
    Retries up to 5 times on connector errors.
    """
    mail_id = int(mail_obj.get("id"))
    prompt_template = _load_action_prompt()
    if not prompt_template:
        raise ValueError("No action_extraction prompt found in prompt_library.json")

    prompt = prompt_template + "\n\nEMAIL:\n" + mail_obj.get("body", "") + "\n\nRespond with JSON."

    attempts = 0
    last_err = None
    while attempts < 5:
        attempts += 1
        try:
            out = call(prompt)
            parsed = _parse_json_from_text(out)
            # normalize to list of items
            if isinstance(parsed, dict):
                # single item or dict of fields -> attempt to convert to list of dicts
                items = [parsed]
            elif isinstance(parsed, list):
                items = parsed
            else:
                raise ValueError("Parsed JSON is neither object nor list.")
            # basic validation: each item must have 'task' key
            for it in items:
                if not isinstance(it, dict) or "task" not in it:
                    raise ValueError(f"Invalid action item format: {it}")
            # update mail
            update_mail(mail_id, {"action_items": items})
            return items
        except ConnectionError as ce:
            last_err = ce
            time.sleep(1 * attempts)
            continue
        except Exception as e:
            # parsing/validation errors: surface immediately
            raise e
    raise ConnectionError(f"Failed after {attempts} attempts. Last error: {last_err}")

# quick test harness
if __name__ == "__main__":
    if INBOX.exists():
        with INBOX.open("r", encoding="utf-8") as f:
            inbox = json.load(f)
        if inbox.get("emails"):
            mail = inbox["emails"][0]
            try:
                items = action_item_extractor(mail)
                print("Action items:", items)
            except Exception as e:
                print("Extractor error:", e)
        else:
            print("No emails to test.")
    else:
        print("mail_inbox.json not found.")
