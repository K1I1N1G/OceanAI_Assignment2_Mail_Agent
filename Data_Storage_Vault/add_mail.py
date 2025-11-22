# add_mail.py
# Adds a mail to Data_Storage_Vault/mail_inbox.json and updates counter.

import json, os, tempfile
from pathlib import Path
import time

# Ensure inbox path is repository-relative (prevents cross-drive / CWD surprises).
MODULE_ROOT = Path(__file__).resolve().parents[1]
INBOX = MODULE_ROOT / "Data_Storage_Vault" / "mail_inbox.json"


def _atomic_write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# Simple cross-platform directory lock (uses mkdir as an atomic operation).
# Keeps changes minimal and avoids extra dependencies.
def _acquire_lock(path: Path, timeout: float = 5.0, poll: float = 0.05):
    """
    Acquire a lock for the given path by creating a lock directory next to it.
    Returns the Path to the lockdir when acquired.
    Raises TimeoutError if lock not acquired within timeout.
    """
    lockdir = Path(str(path) + ".lockdir")
    start = time.time()
    while True:
        try:
            os.mkdir(lockdir)
            return lockdir
        except FileExistsError:
            if (time.time() - start) >= timeout:
                raise TimeoutError(f"Failed to acquire lock for {path} within {timeout}s")
            time.sleep(poll)


def _release_lock(lockdir: Path):
    try:
        os.rmdir(lockdir)
    except Exception:
        try:
            if lockdir.exists():
                os.rmdir(lockdir)
        except Exception:
            pass


def add_mail(mail_obj, inbox_path=INBOX):
    """Add mail dict with keys sender, subject, timestamp, body.
    Returns assigned integer id."""
    p = Path(inbox_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # validate required fields early
    for k in ("sender", "subject", "timestamp", "body"):
        if k not in mail_obj:
            raise ValueError(f"Missing required field: {k}")

    lock = None
    try:
        lock = _acquire_lock(p, timeout=5.0)

        if not p.exists():
            data = {"counter": 0, "emails": []}
        else:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)

        new_id = int(data.get("counter", 0)) + 1

        # Build entry preserving all fields from mail_obj
        entry = dict(mail_obj)
        entry["id"] = new_id

        # default fields
        entry.setdefault("category", "")
        entry.setdefault("action_items", [])

        # NEW FIELD: draftable
        # If AI_mail_drafter created the mail it will set draftable itself.
        # For normal mails added by user/system, set to empty string = "needs drafting".
        entry.setdefault("draftable", "")

        data.setdefault("emails", []).append(entry)
        data["counter"] = new_id

        _atomic_write(p, data)
        return new_id

    finally:
        if lock is not None:
            _release_lock(lock)


# Example run when file executed directly
if __name__ == "__main__":
    sample = {
        "sender": "tester@example.com",
        "subject": "Test Add Mail",
        "timestamp": "2025-11-20T12:00:00+05:30",
        "body": "This is a test email body.",
    }
    new_id = add_mail(sample)
    print(f"Added mail id: {new_id}")
