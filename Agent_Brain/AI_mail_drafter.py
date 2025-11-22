# AI_mail_drafter.py
# Uses auto_reply prompt to draft replies and inserts them into mailbox as category 'draft'

import json
import time
from pathlib import Path
import sys
import re
import traceback

# Ensure project root is importable
MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

# Try to import add_mail (compat: top-level or Data_Storage_Vault package)
try:
    from add_mail import add_mail
except Exception:
    try:
        from Data_Storage_Vault.add_mail import add_mail
    except Exception:
        raise

# Import connection gateway and update_mail for backlinking created drafts
from Agent_Brain.connection_gateway import call, ConnectionError
try:
    from update_mail import update_mail
except Exception:
    try:
        from Data_Storage_Vault.update_mail import update_mail
    except Exception:
        update_mail = None  # best-effort; backlinking will be skipped if unavailable

PROMPT_LIB = MODULE_ROOT / "Data_Storage_Vault" / "prompt_library.json"
INBOX = MODULE_ROOT / "Data_Storage_Vault" / "mail_inbox.json"


def _load_auto_prompt():
    try:
        with PROMPT_LIB.open("r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return ""
    for p in d.get("prompts", []):
        if p.get("type") == "auto_reply":
            return p.get("prompt", "")
    return ""


def _clean_draft(text):
    """Clean and normalize model-generated draft text without altering meaning."""

    # Remove Markdown fences ```...```
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    # Remove standalone markdown separators like --- or ***
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Remove bold markers **text**
    text = text.replace("**", "")

    # Remove duplicated Subject: lines inside body
    # Example: "Subject: Re: ..." appearing again inside the body
    text = re.sub(r"^Subject:.*$", "", text, flags=re.MULTILINE)

    # Remove leading/trailing empty lines
    text = text.strip()

    # Normalize blank lines (max 1 blank line)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def _select_best_option(raw_text):
    """
    If model produced multiple options, pick the first (best) human-readable option.
    Heuristics:
      - If 'Option 1' or 'Option 1:' exists, extract from that point to before 'Option 2'
      - Else split on visible separators '---' and take the first meaningful block
      - Else, if numbered list (1., 2.), take the first item + following paragraph(s)
      - Otherwise return the whole text
    """
    if not raw_text:
        return raw_text

    # Normalize CRLF
    t = raw_text.replace("\r\n", "\n")

    # 1) Option headings: find all "Option <number>" occurrences
    opt_matches = list(re.finditer(r"\bOption\s*(?:#?\s*)?(\d+)\b", t, flags=re.IGNORECASE))
    if opt_matches:
        # take text from first option to just before second (if exists) or to end
        start = opt_matches[0].start()
        end = opt_matches[1].start() if len(opt_matches) > 1 else len(t)
        candidate = t[start:end].strip()
        # remove the leading "Option X" label if present
        candidate = re.sub(r"^\s*Option\s*(?:#?\s*)?\d+[:\-\)]?\s*", "", candidate, flags=re.IGNORECASE)
        return candidate.strip()

    # 2) Separator '---' or '***' blocks
    sep_parts = re.split(r"\n\s*[-*_]{3,}\s*\n", t)
    if len(sep_parts) > 1:
        # find the first non-empty meaningful block
        for part in sep_parts:
            part_clean = part.strip()
            if len(part_clean) >= 30:  # heuristic minimal length
                return part_clean
        # fallback to first block
        return sep_parts[0].strip()

    # 3) Numbered list like "1." or "1)"
    num_match = re.search(r"(?m)^\s*(?:1[\.\)])\s+", t)
    if num_match:
        # extract from match to before "2."
        start = num_match.start()
        m2 = re.search(r"(?m)^\s*(?:2[\.\)])\s+", t)
        end = m2.start() if m2 else len(t)
        candidate = t[start:end].strip()
        # remove leading numbering
        candidate = re.sub(r"^\s*(?:1[\.\)])\s*", "", candidate)
        return candidate.strip()

    # 4) No clear multiple options — return entire text
    return t.strip()


def _extract_text_from_call_output(out):
    """
    Handle different possible shapes of connection gateway outputs.
    Return a best-effort string representation of the model reply.
    """
    try:
        if out is None:
            return ""
        # If it's a dict with 'candidates' like the Gemini debug, extract the first candidate text
        if isinstance(out, dict):
            # common GL shape: {'candidates':[{'content':{'parts':[{'text': '...'}]}}]}
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
                # fallback: try top-level 'text' fields
                if isinstance(first, dict):
                    # try common keys
                    for k in ("text", "output", "message"):
                        v = first.get(k)
                        if isinstance(v, str):
                            return v
            # further fallback to stringifying a likely 'content' or 'response' field
            for k in ("response", "content", "output"):
                v = out.get(k)
                if isinstance(v, str):
                    return v
            # lastly, stringify
            return json.dumps(out)
        # If it's already a string
        if isinstance(out, str):
            return out
        # Anything else: string convert
        return str(out)
    except Exception:
        return str(out)


def AI_mail_drafter(mail_obj, sender_override=None):
    """
    mail_obj: dict of the original mail.
    If draft generated, add it to inbox as a new mail with category 'draft' using add_mail().
    Retries up to 5 times on connector errors and transient file-access errors.
    Returns the draft text (string) or empty string if no draft created.
    NOTE: This version uses the 'draftable' field:
      - If mail_obj.get('draftable') == 0 -> no drafting (returns "").
      - The model is prompted to reply exactly "INVALID" (single word) when it decides not to draft.
      - If model returns "INVALID", this function will set draftable=0 on the source mail (if update_mail available).
    """
    # Respect explicit non-draftable marker
    try:
        if mail_obj.get("draftable") == 0:
            return ""
    except Exception:
        # if mail_obj not a dict or missing, continue as usual
        pass

    prompt_template = _load_auto_prompt()
    if not prompt_template:
        raise ValueError("No auto_reply prompt found in prompt_library.json")

    # Instruct model to return exactly the single word "INVALID" if it decides NOT to produce a draft.
    # This small appended instruction is required for the 'draftable' workflow.
    prompt = (
        prompt_template
        + "\n\nORIGINAL EMAIL:\n"
        + mail_obj.get("body", "")
        + "\n\nProduce a polite reply."
        + "\n\nIMPORTANT: If this email is NOT suitable for drafting based on the prompt, respond with exactly the single word:\nINVALID"
    )

    attempts = 0
    last_err = None
    while attempts < 5:
        attempts += 1
        try:
            out = call(prompt)
            raw = _extract_text_from_call_output(out)
            raw_draft = raw.strip()
            if not raw_draft:
                raise ValueError("Empty draft from model.")

            # If model declares the mail invalid for drafting, mark source as non-draftable (best-effort)
            if raw_draft == "INVALID":
                try:
                    src_id = mail_obj.get("id")
                    if update_mail is not None and src_id is not None:
                        try:
                            update_mail(src_id, {"draftable": 0})
                        except Exception:
                            # ignore backlink/update errors
                            traceback.print_exc()
                except Exception:
                    pass
                return ""

            # If model returned multiple options, pick the best (first) option to save/print
            best_block = _select_best_option(raw_draft)

            # Clean/format draft text
            draft_text = _clean_draft(best_block)

            # create draft mail structure (include backlink 'draft_for' so loader can detect duplicates)
            draft_mail = {
                "sender": sender_override or "ai.drafter@oceanai.local",
                "subject": f"Draft reply: {mail_obj.get('subject','(no subject)')}",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "body": draft_text,
                "category": "draft",
                "action_items": [],
                # backlink field used by loader's _draft_exists_for heuristic
                "draft_for": mail_obj.get("id"),
            }

            # add_mail should handle id assignment and counter
            # Retry add_mail on transient file-access/permission errors (e.g., Windows replace race)
            add_attempts = 0
            new_id = None
            while add_attempts < 5:
                add_attempts += 1
                try:
                    new_id = add_mail(draft_mail)
                    break
                except PermissionError as pe:
                    # transient Windows file lock — back off and retry
                    last_err = pe
                    time.sleep(0.2 * add_attempts)
                    continue
                except OSError as oe:
                    # also handle generic OSErrors that may indicate file busy
                    last_err = oe
                    time.sleep(0.2 * add_attempts)
                    continue
                except Exception:
                    # non-transient - re-raise
                    raise

            if new_id is None:
                # failed to write draft after retries
                raise IOError(f"Failed to write draft mail after retries. Last error: {last_err}")

            # After successful draft creation, mark source mail as non-draftable (so we don't redraft)
            try:
                src_id = mail_obj.get("id")
                if update_mail is not None and src_id is not None:
                    try:
                        update_mail(src_id, {"draftable": 0})
                    except Exception:
                        # ignore update errors
                        traceback.print_exc()
            except Exception:
                pass

            # Backlinking via update_mail is best-effort (some update_mail implementations restrict allowed fields)
            try:
                if update_mail is not None:
                    # Ensure the created draft entry is categorized 'draft' (safe write)
                    try:
                        update_mail(new_id, {"category": "draft"})
                    except Exception:
                        # ignore failures setting category on draft
                        traceback.print_exc()
            except Exception:
                # best-effort: don't fail draft creation if backlinking fails
                traceback.print_exc()

            return draft_text

        except ConnectionError as ce:
            last_err = ce
            # small backoff
            time.sleep(1 * attempts)
            continue
        except Exception as e:
            # non-connection errors should bubble up (useful for debugging)
            raise e

    raise ConnectionError(f"Failed to generate draft after {attempts} attempts. Last error: {last_err}")


# quick test harness
if __name__ == "__main__":
    if INBOX.exists():
        with INBOX.open("r", encoding="utf-8") as f:
            inbox = json.load(f)
        if inbox.get("emails"):
            mail = inbox["emails"][0]
            try:
                draft = AI_mail_drafter(mail)
                print("Draft created (preview):", draft[:300])
            except Exception as e:
                print("Drafter error:", e)
        else:
            print("No emails in inbox.")
    else:
        print("mail_inbox.json not found.")
