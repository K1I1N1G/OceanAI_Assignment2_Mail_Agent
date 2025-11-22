# Backend/mail_func.py
"""
All function definitions and globals for mailbox loading & background processing.
This file contains the full implementation previously in load_mail.py.
"""

import json
import threading
import time
import traceback
from pathlib import Path
import sys
import os

# ensure project root is importable (same behavior as before)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Use a canonical inbox path relative to this module (prevents multiple copies across different CWDs)
MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "Data_Storage_Vault"
DATA_DIR.mkdir(parents=True, exist_ok=True)
INBOX_PATH = DATA_DIR / "mail_inbox.json"

# --- New: on-disk error signal path (safe, lightweight) ---
ERROR_SIGNAL_PATH = DATA_DIR / "_last_error.json"

# Ensure DATA_DIR is on the same drive as MODULE_ROOT; remap if necessary to avoid Streamlit watcher cross-drive errors.
try:
    if MODULE_ROOT.drive and (DATA_DIR.drive != MODULE_ROOT.drive):
        DATA_DIR = MODULE_ROOT / "Data_Storage_Vault"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        INBOX_PATH = DATA_DIR / "mail_inbox.json"
        ERROR_SIGNAL_PATH = DATA_DIR / "_last_error.json"
        print("[Loader] Remapped Data_Storage_Vault to project root to avoid cross-drive watcher issues.", flush=True)
except Exception:
    # best-effort; do not crash import
    pass

# Agent_Brain functions (they internally call Data_Storage_Vault update/add)
try:
    from Agent_Brain.smart_categorizer import smart_categorizer
    from Agent_Brain.action_item_extractor import action_item_extractor
    from Agent_Brain.AI_mail_drafter import AI_mail_drafter
except Exception:
    # If imports fail, background processing will be disabled; loader will still return mailbox.
    smart_categorizer = None
    action_item_extractor = None
    AI_mail_drafter = None

# Optional throttle config (env override)
MIN_SECONDS_BETWEEN_LLM_CALLS = float(os.environ.get("MIN_SECONDS_BETWEEN_LLM_CALLS", "0.5"))
_last_llm_call = 0.0

# Backoff for quota/token errors (when detected, pause processing for this many seconds)
RETRY_BACKOFF_SECONDS = float(os.environ.get("LLM_QUOTA_BACKOFF_SECONDS", "60"))

# Internal quota backoff state (thread-safe)
_quota_backoff_until = 0.0
_quota_lock = threading.Lock()
_last_quota_log = 0.0  # timestamp for last printed quota log to avoid spam

# In-memory error reporting (UI can import and read)
_last_error = None
_error_lock = threading.Lock()

# Processing thread singletons to avoid spawning many threads on repeated UI reloads
_processing_thread = None
_processing_thread_lock = threading.Lock()

# Lock to ensure draft creation is atomic per process and avoid duplicate drafts
_draft_lock = threading.Lock()


def set_last_error(message: str):
    """Set the latest backend error (thread-safe). UI will read this via get_last_error()."""
    global _last_error
    with _error_lock:
        _last_error = {"message": str(message), "timestamp": time.time()}
    # write a simple on-disk signal so the UI can poll it if needed
    try:
        with ERROR_SIGNAL_PATH.open("w", encoding="utf-8") as _f:
            json.dump(_last_error, _f)
    except Exception:
        # never crash background thread just because signal write failed
        print("[Loader] warning: failed to write error signal file", flush=True)


def get_last_error():
    """Return last error dict or None. Caller should not modify returned dict."""
    with _error_lock:
        return None if _last_error is None else dict(_last_error)


def clear_last_error():
    """Clear the last error (thread-safe)."""
    global _last_error
    with _error_lock:
        _last_error = None
    # remove on-disk signal if present
    try:
        if ERROR_SIGNAL_PATH.exists():
            ERROR_SIGNAL_PATH.unlink()
    except Exception:
        print("[Loader] warning: failed to remove error signal file", flush=True)


def _throttle():
    global _last_llm_call
    now = time.time()
    elapsed = now - _last_llm_call
    if elapsed < MIN_SECONDS_BETWEEN_LLM_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_LLM_CALLS - elapsed)
    _last_llm_call = time.time()


def _read_inbox():
    """
    Read the inbox with coordination using a small ".lockdir" next to the inbox file.
    This makes reads and writes mutually exclusive on Windows (where os.replace() fails
    if the target file is opened by another process). The lock is attempted for a short
    timeout; if unavailable we still try a best-effort read once and report errors.
    """
    if not INBOX_PATH.exists():
        return {"counter": 0, "emails": []}

    lockdir = Path(str(INBOX_PATH) + ".lockdir")
    start = time.time()
    timeout = 5.0
    poll = 0.05
    got_lock = False

    # Try to acquire the lockdir (writers use the same pattern). If we succeed, we own the lock.
    while True:
        try:
            os.mkdir(lockdir)
            got_lock = True
            break
        except FileExistsError:
            if (time.time() - start) >= timeout:
                # couldn't acquire quickly; fall back to a single read attempt (best-effort)
                break
            time.sleep(poll)
        except Exception as e:
            # unexpected error creating lockdir: log and fall back to direct read
            print(f"[Loader] warning: unexpected error acquiring read lock: {e}", flush=True)
            traceback.print_exc()
            break

    try:
        with INBOX_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        # If the file is transiently unreadable (e.g., writer holds it), report and return empty inbox
        print(f"[Loader] warning: failed to read inbox: {e}", flush=True)
        traceback.print_exc()
        set_last_error(f"Failed to read inbox file: {e}")
        return {"counter": 0, "emails": []}
    finally:
        # release the lockdir if we created it
        if got_lock:
            try:
                os.rmdir(lockdir)
            except Exception:
                # best-effort cleanup
                try:
                    if lockdir.exists():
                        os.rmdir(lockdir)
                except Exception:
                    pass


def _normalize_action_items(raw):
    """
    Normalize action_items into a list of dicts or empty list.
    Accepts:
      - list (of dicts or strings)
      - JSON string
      - None -> []
    """
    if not raw:
        return []
    # If it's already a list, return sanitized list
    if isinstance(raw, list):
        normalized = []
        for it in raw:
            if isinstance(it, dict):
                normalized.append(it)
            else:
                # convert plain string items to dict with task key
                normalized.append({"task": str(it)})
        return normalized
    # If it's a JSON string, try to parse
    if isinstance(raw, str):
        raw = raw.strip()
        if (raw.startswith("[") and raw.endswith("]")) or (raw.startswith("{") and raw.endswith("}")):
            try:
                parsed = json.loads(raw)
                return _normalize_action_items(parsed)
            except Exception:
                # Fall through and return a single-item list with the string
                return [{"task": raw}]
        # Plain string (non-JSON): treat as single task
        return [{"task": raw}]
    # Unknown type: stringify and return as single task
    try:
        return [{"task": str(raw)}]
    except Exception:
        return []


def _extract_body(mail):
    """
    Tolerant extraction of mail body text. Accepts several common keys.
    Returns a string (never None).
    """
    candidates = [
        "body",
        "text",
        "content",
        "message",
        "mail_body",
    ]
    for k in candidates:
        v = mail.get(k)
        if v is not None:
            # If body is JSON structure, try to turn into readable string
            if isinstance(v, (dict, list)):
                try:
                    return json.dumps(v, ensure_ascii=False)
                except Exception:
                    return str(v)
            return str(v)
    # Fallback to any field that looks promising
    for k, v in mail.items():
        if isinstance(v, str) and len(v) > 20:
            return v
    return ""


def _make_ui_object(mail):
    """Convert full mail object to UI display object (keeps full mail under 'full')."""
    # Defensive copy/safe access
    if mail is None:
        mail = {}
    try:
        # id normalization
        _id = mail.get("id")
        try:
            _id = int(_id)
        except Exception:
            # if id missing or cannot convert, keep as-is (UI may handle)
            pass

        # canonical sender/subject/timestamp/category extraction
        sender = mail.get("sender") or mail.get("from") or mail.get("email_from") or ""
        subject = mail.get("subject") or mail.get("title") or ""
        timestamp = mail.get("timestamp") or mail.get("ts") or mail.get("date") or ""

        # category/tag aliasing (keep empty string if not present)
        category = mail.get("category") or mail.get("tag") or ""

        # body normalization: always provide a string for UI
        body_text = _extract_body(mail)

        # action items normalization: always provide a list
        raw_ais = mail.get("action_items") or mail.get("actionItems") or mail.get("tasks") or []
        action_items = _normalize_action_items(raw_ais)

        has_actions = bool(action_items) or bool(mail.get("has_action_items"))

        # Prepare UI-friendly object but retain the full original mail under "full"
        ui_obj = {
            "id": _id,
            "sender": sender,
            "subject": subject,
            "timestamp": timestamp,
            "category": category,
            "has_action_items": bool(has_actions),
            "action_items": action_items,
            "body": body_text,
            "full": mail,
        }
        return ui_obj
    except Exception as e:
        # If normalization fails for any reason, return a minimal safe object
        print(f"[Loader] _make_ui_object normalization error: {e}")
        traceback.print_exc()
        return {
            "id": mail.get("id"),
            "sender": mail.get("sender", ""),
            "subject": mail.get("subject", ""),
            "timestamp": mail.get("timestamp", ""),
            "category": mail.get("category", ""),
            "has_action_items": bool(mail.get("action_items")),
            "action_items": mail.get("action_items") or [],
            "body": str(mail.get("body") or ""),
            "full": mail,
        }


def fast_return_mails():
    """
    Read the inbox file and convert to UI objects.
    Returns: list of UI objects (not blocking).
    """
    data = _read_inbox()
    emails = data.get("emails", [])
    ui_list = [_make_ui_object(m) for m in emails]
    return ui_list


# Helper to decide if an exception looks like an API-token/quota error
def _is_quota_or_token_error(exc: Exception):
    txt = str(exc).lower()
    keywords = [
        "quota",
        "quota exceeded",
        "429",
        "rate limit",
        "token",
        "billing",
        "quota_exceeded",
        "resource_exhausted",
        "exceeded",
    ]
    return any(k in txt for k in keywords)


def _set_quota_backoff(message: str):
    """Set global quota backoff until now + RETRY_BACKOFF_SECONDS and set in-memory error."""
    global _quota_backoff_until, _last_quota_log
    with _quota_lock:
        now = time.time()
        _quota_backoff_until = max(_quota_backoff_until, now + RETRY_BACKOFF_SECONDS)
        # set in-memory error for UI
        set_last_error(message)
        if now - _last_quota_log > 1.0:
            print(f"[Loader] LLM quota/token error detected; backing off for {RETRY_BACKOFF_SECONDS}s. Message: {message}")
            _last_quota_log = now


def _clear_quota_backoff():
    """Clear backoff and in-memory error when successful calls happen."""
    global _quota_backoff_until
    with _quota_lock:
        _quota_backoff_until = 0.0
    clear_last_error()


def _quota_backoff_active():
    """Return seconds left of backoff (0 if none)."""
    with _quota_lock:
        now = time.time()
        return max(0.0, _quota_backoff_until - now)


def _draft_exists_for(mail_id):
    """
    Heuristic: check if a draft mail already exists that references this mail.
    This looks for mails with category 'draft' and a field that references the source:
    'draft_for', 'in_reply_to', or 'source_id'. If none found, returns False.
    """
    try:
        data = _read_inbox()
        for m in data.get("emails", []):
            try:
                if (m.get("category") or "").lower() == "draft":
                    if m.get("draft_for") == mail_id or m.get("in_reply_to") == mail_id or m.get("source_id") == mail_id:
                        return True
            except Exception:
                # ignore malformed entries
                continue
    except Exception:
        pass
    return False


def _process_one_mail(mail):
    """
    Runs the Agent_Brain steps for a single mail (if not draft).
    Each Agent_Brain function will write back to mail_inbox.json using Data_Storage_Vault.
    This function catches and logs exceptions so processing continues.
    """
    # If backoff active, skip processing this invocation (caller handles sleeping).
    if _quota_backoff_active() > 0:
        return

    cat = (mail.get("category") or "").lower()
    if cat == "draft":
        # For drafts: optionally run action extraction only (if desired).
        try:
            _throttle()
            if action_item_extractor:
                action_item_extractor(mail)
        except Exception as e:
            print(f"[Processor] action_item_extractor (draft) failed for id {mail.get('id')}: {e}")
            traceback.print_exc()
            # if quota-like error on draft extraction, set backoff as well
            if _is_quota_or_token_error(e):
                _set_quota_backoff(str(e))
        return

    mail_id = mail.get("id")
    try:
        # 1) Categorize - only if category is missing/empty
        if smart_categorizer and not (mail.get("category")):
            try:
                _throttle()
                smart_categorizer(mail)
            except Exception as e:
                print(f"[Processor] smart_categorizer failed for id {mail_id}: {e}")
                traceback.print_exc()
                if _is_quota_or_token_error(e):
                    # set backoff and stop further immediate processing
                    _set_quota_backoff(str(e))
                    return

        # small wait
        time.sleep(0.2)

        # 2) Extract action items - only if action_items absent or empty
        if action_item_extractor:
            try:
                current_ais = mail.get("action_items") or []
                if not _normalize_action_items(current_ais):
                    _throttle()
                    action_item_extractor(mail)
            except Exception as e:
                print(f"[Processor] action_item_extractor failed for id {mail_id}: {e}")
                traceback.print_exc()
                if _is_quota_or_token_error(e):
                    _set_quota_backoff(str(e))
                    return

        time.sleep(0.2)

        # 3) Draft reply (AI_mail_drafter will create a new mail with category 'draft')
        if AI_mail_drafter:
            try:
                current_cat = (mail.get("category") or "").lower()
                if current_cat != "draft":
                    # Guard draft creation with a lock so that "check + create" is atomic.
                    # This prevents two threads from both seeing "no draft" and both creating one.
                    with _draft_lock:
                        # Use a fresh inbox snapshot inside the lock
                        if not _draft_exists_for(mail_id):
                            _throttle()
                            AI_mail_drafter(mail)
                            # on success, clear any previous quota flag
                            _clear_quota_backoff()
            except Exception as e:
                print(f"[Processor] AI_mail_drafter failed for id {mail_id}: {e}")
                traceback.print_exc()
                if _is_quota_or_token_error(e):
                    _set_quota_backoff(str(e))
                # continue processing other mails; do not re-raise
    except Exception as e:
        print(f"[Processor] Unexpected error processing mail id {mail_id}: {e}")
        traceback.print_exc()


def process_mails_sequentially(stop_if_none=False, delay_between=0.2):
    """
    Sequentially process all mails currently in inbox.
    Behavior:
      - reads inbox snapshot
      - for each mail (in the order present) calls _process_one_mail(mail)
      - reloads mailbox for each mail to pick up any concurrent changes

    This function respects a global quota backoff: when a quota/token error is detected,
    processing pauses for RETRY_BACKOFF_SECONDS to avoid log spam and repeated immediate retries.
    """
    try:
        data = _read_inbox()
        emails = data.get("emails", [])
        if not emails:
            return

        idx = 0
        while idx < len(emails):
            # If a quota backoff is active, sleep until it's over (but wake periodically)
            backoff_left = _quota_backoff_active()
            if backoff_left > 0:
                # sleep a small slice so thread remains responsive to backoff clear
                sleep_for = min(backoff_left, 2.0)
                time.sleep(sleep_for)
                # after waiting, re-read inbox (in case something changed) and continue
                data = _read_inbox()
                emails = data.get("emails", [])
                # restart from the beginning to pick up any changes
                idx = 0
                continue

            try:
                mail = emails[idx]
                # reload the single mail object from file to get latest state
                fresh = None
                current = _read_inbox()
                for m in current.get("emails", []):
                    try:
                        if int(m.get("id", -1)) == int(mail.get("id")):
                            fresh = m
                            break
                    except Exception:
                        # safe fallback if id cannot be int() cast
                        if m.get("id") == mail.get("id"):
                            fresh = m
                            break
                idx += 1
                if fresh is None:
                    # mail was deleted meanwhile; skip
                    continue
                _process_one_mail(fresh)
                # optional small delay between mails to avoid rapid-fire requests
                time.sleep(delay_between)
            except Exception as e:
                print(f"[Processor] Error while processing mailbox at index {idx}: {e}")
                traceback.print_exc()
                # continue to next mail
    except Exception as e:
        # Catch-all to ensure the background thread doesn't silently die
        print(f"[Processor] Fatal error in processing loop: {e}")
        traceback.print_exc()
        set_last_error(f"Background processor failed: {e}")


def _start_processing_thread_once(delay_between=0.2):
    """
    Start the background processing thread only once per process.
    Subsequent calls are no-ops while the thread is alive.
    """
    global _processing_thread
    with _processing_thread_lock:
        if _processing_thread is not None and _processing_thread.is_alive():
            # already running
            return
        # create and start a single daemon thread
        t = threading.Thread(target=process_mails_sequentially, kwargs={"delay_between": delay_between}, daemon=True)
        t.start()
        _processing_thread = t


def load_and_process(start_background=True):
    """
    Public API:
      - returns UI-ready list of mails immediately
      - if start_background True and Agent_Brain functions are importable, starts a daemon thread
        that will process mails sequentially and update the inbox via Agent_Brain functions.

    NOTE: This function now guards against spawning multiple background threads on repeated calls
    (Streamlit reloads). It preserves all original behavior but ensures only a single processor thread
    runs in this process at a time.

    Also: runs cleanup_temp_files() just before returning the ui_list so temporary files
    created in DATA_DIR starting with "tmp" are removed.
    """
    ui_list = fast_return_mails()

    if start_background and (smart_categorizer or action_item_extractor or AI_mail_drafter):
        try:
            _start_processing_thread_once(delay_between=0.2)
        except Exception as e:
            print(f"[Loader] Failed to start processing thread: {e}", flush=True)
            traceback.print_exc()
            set_last_error(f"Failed to start background processor: {e}")

    # === Run cleanup of temporary files just before returning ===
    try:
        def cleanup_temp_files():
            """
            Safely delete temporary files created by the loader/agent.
            - Targets files in DATA_DIR whose names start with "tmp" (covers tmpmuk_fa40).
            - Skips directories and never touches files outside DATA_DIR.
            - Returns list of deleted file paths (strings). Logs warnings on failure but never raises.
            """
            deleted = []
            try:
                base = Path(DATA_DIR)
            except Exception:
                return deleted

            try:
                if not base.exists() or not base.is_dir():
                    return deleted

                # iterate only top-level entries in DATA_DIR
                for p in base.iterdir():
                    try:
                        # only consider files that start with tmp (covers tmp_ and tmpx..)
                        if not p.name.startswith("tmp"):
                            continue
                        # skip directories (do not recurse)
                        if not p.is_file():
                            continue
                        # extra safety: avoid touching the main inbox or error files
                        try:
                            if p.resolve() == INBOX_PATH.resolve() or p.resolve() == ERROR_SIGNAL_PATH.resolve():
                                continue
                        except Exception:
                            # if resolve fails, skip the extra-safety check but still attempt removal below
                            pass
                        # attempt removal
                        try:
                            p.unlink()
                            deleted.append(str(p))
                        except Exception as e:
                            # best-effort: log and continue
                            print(f"[Loader] warning: failed to remove temp file {p}: {e}", flush=True)
                    except Exception:
                        # protect against weird filenames / permission errors per-file
                        try:
                            print(f"[Loader] warning: unexpected error while inspecting {p}", flush=True)
                        except Exception:
                            pass
            except Exception as e:
                try:
                    print(f"[Loader] warning: cleanup_temp_files failed: {e}", flush=True)
                except Exception:
                    pass
            return deleted

        # call the cleanup function; ignore result but print debug if any files removed
        try:
            removed = cleanup_temp_files()
            if removed:
                print(f"[Loader] cleanup_temp_files removed {len(removed)} files.", flush=True)
        except Exception:
            # protect caller from any unexpected cleanup error
            pass
    except Exception:
        # top-level protection: do not allow cleanup machinery to raise
        pass

    return ui_list


# If called directly as script, print quick info
if __name__ == "__main__":
    lst = load_and_process(start_background=False)
    print(f"Loaded {len(lst)} UI mail objects.")
