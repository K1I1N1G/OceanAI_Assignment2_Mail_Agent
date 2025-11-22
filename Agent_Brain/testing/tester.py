# tester.py
# Run each Agent_Brain module, capture stdout/stderr, write to test_log.txt (overwrite)

import subprocess
import sys
from datetime import datetime
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
SCRIPTS = [
    "connection_gateway.py",
    "smart_categorizer.py",
    "action_item_extractor.py",
    "AI_mail_drafter.py"
]
LOG_PATH = ROOT / "test_log.txt"

def run_script(script_path):
    header = f"\n\n=== RUN: {script_path} ===\nStarted: {datetime.now().isoformat()}\n"
    start = time.perf_counter()
    try:
        res = subprocess.run([sys.executable, str(script_path)],
                             capture_output=True, text=True, timeout=120)
        out = res.stdout or ""
        err = res.stderr or ""
        footer = f"\nExit code: {res.returncode}\n"
    except Exception as e:
        out = ""
        err = f"Exception running script: {e}"
        footer = "\nExit code: (exception)\n"
    end = time.perf_counter()
    elapsed = end - start
    # append elapsed time info
    time_info = f"Time elapsed: {elapsed:.3f} seconds\n"
    return header + out + ("\n---STDERR---\n" + err if err else "") + footer + time_info

def main():
    # overwrite or create log
    with LOG_PATH.open("w", encoding="utf-8") as logf:
        logf.write(f"Test run at {datetime.now().isoformat()}\n")
    # run each script and append results
    with LOG_PATH.open("a", encoding="utf-8") as logf:
        for s in SCRIPTS:
            script_file = ROOT / s
            if not script_file.exists():
                logf.write(f"\n\n=== SKIPPED: {s} (not found) ===\n")
                continue
            result_text = run_script(script_file)
            logf.write(result_text)
    print(f"Tests complete. See {LOG_PATH} for details.")

if __name__ == "__main__":
    main()
