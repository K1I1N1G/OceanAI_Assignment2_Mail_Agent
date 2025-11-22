# Backend/helper.py
import html

def build_right_side_html(ts: str, category_html: str, tasks_html: str) -> str:
    """
    Return a small HTML snippet that represents the right-side block
    (timestamp, category tag, tasks indicator) and is intended to be
    injected inside the .ocean-card so it is visually contained.

    Parameters:
      - ts: formatted timestamp string (already safe for display)
      - category_html: pre-built HTML for category (may be empty)
      - tasks_html: pre-built HTML for tasks indicator (may be empty)

    Returns:
      HTML string.
    """
    # ensure timestamp is escaped; category_html and tasks_html are expected
    # to already contain safe escaped content (as they are created in home.py),
    # but escape ts here for safety.
    safe_ts = html.escape(ts)
    right = f"<div class='ocean-right'><div class='ocean-ts'>{safe_ts}</div>{category_html}{tasks_html}</div>"
    return right
