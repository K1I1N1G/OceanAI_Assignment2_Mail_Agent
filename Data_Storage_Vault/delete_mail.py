# delete_mail.py
# Deletes an email by id from Data_Storage_Vault/mail_inbox.json

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
# Matches the locking approach used elsewhere to avoid race conditions and stray tmp files.
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
            # os.mkdir is atomic; if directory exists, this will raise
            os.mkdir(lockdir)
            # acquired
            return lockdir
        except FileExistsError:
            if (time.time() - start) >= timeout:
                raise TimeoutError(f"Failed to acquire lock for {path} within {timeout}s")
            time.sleep(poll)


def _release_lock(lockdir: Path):
    try:
        os.rmdir(lockdir)
    except Exception:
        # best-effort; do not crash caller
        try:
            if lockdir.exists():
                os.rmdir(lockdir)
        except Exception:
            pass


def delete_mail(mail_id, inbox_path=INBOX):
    """Delete email with integer id. Returns True if deleted, False if not found."""
    p = Path(inbox_path)
    if not p.exists():
        return False

    lock = None
    try:
        lock = _acquire_lock(p, timeout=5.0)

        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)

        emails = data.get("emails", [])
        # Filter out the target mail, preserving original order
        new_emails = []
        for e in emails:
            try:
                if int(e.get("id", -1)) != int(mail_id):
                    new_emails.append(e)
            except Exception:
                # fallback comparison if int() fails
                if e.get("id") != mail_id:
                    new_emails.append(e)

        if len(new_emails) == len(emails):
            return False  # not found

        # Reassign sequential IDs starting from 1 to preserve contiguous IDs
        for idx, email in enumerate(new_emails, start=1):
            email["id"] = idx

        # Update counter to reflect new number of emails
        data["emails"] = new_emails
        data["counter"] = len(new_emails)

        _atomic_write(p, data)
        return True
    finally:
        if lock is not None:
            _release_lock(lock)


# Example
if __name__ == "__main__":
    ok = delete_mail(2)
    print("Deleted" if ok else "Mail id not found")
