# tester.py
# Runs basic tests for all Data_Storage_Vault functions and logs results.

import os
import sys
from datetime import datetime
from pathlib import Path

# Determine repository root in a robust way:
# - Start from this file's directory
# - If that directory doesn't contain Data_Storage_Vault, move one level up.
REPO_DIR = Path(__file__).resolve().parent
if not (REPO_DIR / "Data_Storage_Vault").exists():
    # fallback to parent (covers cases where tester.py is inside a subfolder)
    if (REPO_DIR.parent / "Data_Storage_Vault").exists():
        REPO_DIR = REPO_DIR.parent

# Ensure repo root is on sys.path so local modules import reliably
sys.path.insert(0, str(REPO_DIR))

# Import your functions
from add_mail import add_mail
from delete_mail import delete_mail
from update_mail import update_mail
from update_prompt import update_prompt

DATA_DIR = REPO_DIR / "Data_Storage_Vault"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = DATA_DIR / "test_log.txt"


def write_log(message):
    """Write a line to the log file."""
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def reset_log():
    """Create or clear the log file."""
    with LOG_PATH.open("w", encoding="utf-8") as f:
        f.write(f"TEST LOG — {datetime.now()}\n")
        f.write("======================================\n\n")


def test_add_mail():
    sample = {
        "sender": "tester@example.com",
        "subject": "Testing Add Function",
        "timestamp": "2025-11-20T12:00:00+05:30",
        "body": "This is a test email."
    }
    try:
        new_id = add_mail(sample)
        write_log(f"[ADD MAIL] Success — New ID: {new_id}")
    except Exception as e:
        write_log(f"[ADD MAIL] FAILED — {str(e)}")


def test_update_mail():
    try:
        ok = update_mail(1, {"subject": "Updated via tester.py"})
        write_log(f"[UPDATE MAIL] {'Success' if ok else 'FAILED — ID not found'}")
    except Exception as e:
        write_log(f"[UPDATE MAIL] FAILED — {str(e)}")


def test_delete_mail():
    try:
        ok = delete_mail(99999)  # likely does not exist
        write_log(f"[DELETE MAIL] {'Success (Deleted)' if ok else 'No Mail with ID 99999 — OK'}")
    except Exception as e:
        write_log(f"[DELETE MAIL] FAILED — {str(e)}")


def test_update_prompt():
    try:
        ok = update_prompt("categorization", "Updated categorization prompt for testing.")
        write_log(f"[UPDATE PROMPT] {'Success' if ok else 'FAILED'}")
    except Exception as e:
        write_log(f"[UPDATE PROMPT] FAILED — {str(e)}")


# MAIN EXECUTION
if __name__ == "__main__":
    reset_log()
    write_log("Starting tests...\n")

    test_add_mail()
    test_update_mail()
    test_delete_mail()
    test_update_prompt()

    write_log("\nAll tests completed.")
    print("Testing complete. Check test_log.txt.")
