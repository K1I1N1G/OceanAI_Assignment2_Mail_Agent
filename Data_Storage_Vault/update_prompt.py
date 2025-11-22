# update_prompt.py
# Update or add a prompt in Data_Storage_Vault/prompt_library.json

import json, os, tempfile
from pathlib import Path
import time

# Ensure path is repository-relative (prevents cross-drive issues)
MODULE_ROOT = Path(__file__).resolve().parents[1]
PROMPT_LIB = MODULE_ROOT / "Data_Storage_Vault" / "prompt_library.json"


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
            os.mkdir(lockdir)  # atomic
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


def update_prompt(prompt_type, new_prompt, prompt_path=PROMPT_LIB):
    """Replace prompt text for a given type or append new entry. Returns True."""
    p = Path(prompt_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    lock = None
    try:
        lock = _acquire_lock(p, timeout=5.0)

        if not p.exists():
            data = {"prompts": []}
        else:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)

        prompts = data.setdefault("prompts", [])
        for entry in prompts:
            if entry.get("type") == prompt_type:
                entry["prompt"] = new_prompt
                _atomic_write(p, data)
                return True

        # add new
        prompts.append({"type": prompt_type, "prompt": new_prompt})
        _atomic_write(p, data)
        return True
    finally:
        if lock is not None:
            _release_lock(lock)


# Example
if __name__ == "__main__":
    ok = update_prompt("categorization", "Categorize emails into: Important, Newsletter, Spam, To-Do.")
    print("Prompt updated/added" if ok else "Failed")
