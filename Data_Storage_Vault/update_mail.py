# update_mail.py
# Update fields of an existing mail entry by id.

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
        # remove the lockdir (only works if empty — we never put files into it)
        os.rmdir(lockdir)
    except Exception:
        # best-effort; do not crash caller
        try:
            if lockdir.exists():
                os.rmdir(lockdir)
        except Exception:
            pass


def update_mail(mail_id, updates: dict, inbox_path=INBOX):
    """Update allowed fields of email. Returns True if updated, False if not found."""
    # NOTE: changed to preserve/allow arbitrary fields so new/unknown fields are not dropped.
    p = Path(inbox_path)
    if not p.exists():
        return False

    lock = None
    try:
        # acquire lock to serialize read-modify-write
        lock = _acquire_lock(p, timeout=5.0)

        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)

        updated = False
        for i, e in enumerate(data.get("emails", [])):
            try:
                if int(e.get("id", -1)) == int(mail_id):
                    # Allow updating any field except 'id' to avoid identity change.
                    for k, v in updates.items():
                        if k == "id":
                            continue
                        data["emails"][i][k] = v
                    updated = True
                    break
            except Exception:
                # fallback to non-int comparison if int() fails
                if e.get("id") == mail_id:
                    for k, v in updates.items():
                        if k == "id":
                            continue
                        data["emails"][i][k] = v
                    updated = True
                    break

        if not updated:
            return False

        _atomic_write(p, data)
        return True
    finally:
        if lock is not None:
            _release_lock(lock)


# Example
if __name__ == "__main__":
    ok = update_mail(1, {"subject": "Updated subject from script"})
    print("Updated" if ok else "Mail id not found")
