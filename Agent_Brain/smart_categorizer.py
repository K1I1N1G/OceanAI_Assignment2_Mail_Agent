# smart_categorizer.py
# Loads categorization prompt, calls connection_gateway, validates category, updates mail.

import json
import re
import time
from pathlib import Path
import sys, os

# make imports relative to project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Agent_Brain.connection_gateway import call, ConnectionError
from Data_Storage_Vault.update_mail import update_mail  # expects update_mail(id, fields)

PROMPT_LIB = Path(__file__).resolve().parents[1] / "Data_Storage_Vault" / "prompt_library.json"
INBOX = Path(__file__).resolve().parents[1] / "Data_Storage_Vault" / "mail_inbox.json"

CATEGORY_RE = re.compile(r"^[A-Za-z0-9 _\-\&]{1,100}$")  # allowed characters for category

def _load_categorization_prompt():
    with PROMPT_LIB.open("r", encoding="utf-8") as f:
        d = json.load(f)
    for p in d.get("prompts", []):
        if p.get("type") == "categorization":
            return p.get("prompt", "")
    return ""

def smart_categorizer(mail_obj):
    """
    mail_obj: dict representing full mail (must include 'id' and 'body' etc.)
    Returns: category string on success, or raises/returns error message on failure.
    Retry up to 5 times on connector errors.
    Updates mail via Data_Storage_Vault.update_mail(mail_id, fields).
    """
    mail_id = int(mail_obj.get("id"))
    prompt_template = _load_categorization_prompt()
    if not prompt_template:
        raise ValueError("No categorization prompt found in prompt_library.json")

    prompt = prompt_template + "\n\nEMAIL:\n" + mail_obj.get("body", "") + "\n\nReturn a single short category label."

    attempts = 0
    last_err = None
    while attempts < 5:
        attempts += 1
        try:
            out = call(prompt)
            # sanitize output
            cat = out.strip().splitlines()[0].strip().strip('"').strip("'")
            if not CATEGORY_RE.match(cat):
                raise ValueError(f"Invalid category format: '{cat}'")
            # update mail
            update_mail(mail_id, {"category": cat})
            return cat
        except ConnectionError as ce:
            last_err = ce
            time.sleep(1 * attempts)
            continue
        except Exception as e:
            # validation or update error: do not retry connector errors but return
            raise e
    # exhausted retries
    raise ConnectionError(f"Failed to categorize after {attempts} attempts. Last error: {last_err}")

# small test harness
if __name__ == "__main__":
    # quick-load first mail to test
    if INBOX.exists():
        with INBOX.open("r", encoding="utf-8") as f:
            inbox = json.load(f)
        if inbox.get("emails"):
            mail = inbox["emails"][0]
            try:
                cat = smart_categorizer(mail)
                print("Categorized:", cat)
            except Exception as e:
                print("Categorizer error:", e)
        else:
            print("No emails in inbox for test.")
    else:
        print("mail_inbox.json not found; place it under Data_Storage_Vault/ and retry.")
