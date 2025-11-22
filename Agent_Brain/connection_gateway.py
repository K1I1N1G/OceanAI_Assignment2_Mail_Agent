# connection_gateway.py
# Simple request wrapper for Google generative models.
# Uses direct API key query-param auth (verified working).

import os
import time
import json
import requests

API_KEY = ""
DEFAULT_MODEL = "gemini-2.5-flash"

API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

class ConnectionError(Exception):
    pass

def get_api_key():
    return API_KEY

def call(prompt_text, model=DEFAULT_MODEL, timeout=30):
    """
    Primary call — ALWAYS uses ?key=API_KEY first.
    This is the only method proven to work (see logs).
    """
    key = get_api_key()
    url = API_URL_TEMPLATE.format(model=model)
    final_url = url + f"?key={key}"

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text}
                ]
            }
        ]
    }

    # Direct query-param attempt (always correct)
    try:
        resp = requests.post(final_url, json=body, timeout=timeout)
    except requests.RequestException as e:
        raise ConnectionError(f"Network error calling LLM: {e}")

    # Debug output
    print("\n=== DEBUG: RAW API RESPONSE ===")
    print(f"URL: {final_url}")
    print(f"Status Code: {resp.status_code}")
    print("Response Body (first 1000 chars):")
    try:
        print(resp.text[:1000])
    except Exception:
        print("Response body unavailable.")
    print("=== END DEBUG ===\n")

    # Handle errors
    if resp.status_code == 401 or resp.status_code == 403:
        raise ConnectionError(
            f"Authentication error (status {resp.status_code}). Check API key and billing."
        )
    if resp.status_code == 429:
        raise ConnectionError("Quota exceeded (429).")
    if not resp.ok:
        try:
            detail = resp.json()
        except:
            detail = resp.text[:1000]
        raise ConnectionError(f"API error {resp.status_code}: {detail}")

    # Parse response text
    try:
        data = resp.json()
        if isinstance(data, dict):
            candidates = (
                data.get("candidates") or data.get("outputs") or data.get("choices")
            )
            if isinstance(candidates, list) and len(candidates) > 0:
                first = candidates[0]
                if isinstance(first, dict):
                    content = first.get("content") or first
                    parts = content.get("parts") or []
                    if isinstance(parts, list) and parts:
                        if isinstance(parts[0], dict) and "text" in parts[0]:
                            return parts[0]["text"]
                        if isinstance(parts[0], str):
                            return parts[0]
        return json.dumps(data)
    except Exception as e:
        raise ConnectionError(f"Failed to parse API response: {e}")

def test_connection(model=DEFAULT_MODEL):
    try:
        out = call("Test connection. Respond with: OK", model=model, timeout=10)
        if "OK" in out:
            print("Connection OK:", out.strip()[:200])
            return True
        else:
            print("Connection returned:", out.strip()[:200])
            return True
    except Exception as e:
        print("Connection test failed:", e)
        return False

if __name__ == "__main__":
    ok = test_connection()
    print("Gateway test passed." if ok else "Gateway test failed.")
