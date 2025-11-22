# Backend/ui_helper.py
import html

def build_right_side_html(ts: str, category_html: str, tasks_html: str) -> str:
    """
    Return HTML snippet used inside the .ocean-card to render timestamp, category and tasks.
    Matches the previous inline fallback markup used in UI/home.py.
    """
    ts_safe = html.escape(ts or "")
    return f"<div class='ocean-right'><div class='ocean-ts'>{ts_safe}</div>{category_html}{tasks_html}</div>"
