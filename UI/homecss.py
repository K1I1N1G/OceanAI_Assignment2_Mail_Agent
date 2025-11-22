# UI/homecss.py

# Global font + header styling
font_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800;900&display=swap');

html, body, [class*="css"]  {
    font-family: 'Montserrat', system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    color: #ffffff;
}

/* Header styling */
.oceanai-header {
  font-family: 'Montserrat', system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
  font-weight: 900;
  font-size: 34px;
  color: #ffffff;
  margin: 8px 0 18px 0;
  letter-spacing: 0.6px;
}

/* Slightly tone down Streamlit default background cards if needed */
.stApp {
  background-color: transparent;
}
</style>
"""

# Visual CSS for clickable cards + hover/expand area
card_css = """
<style>
/* Dark card background with white text to satisfy "turn text white" request.
   Keep subtle borders and hover lift for affordance. */
.ocean-card {
  border:1px solid rgba(255,255,255,0.06);
  border-radius:10px;
  padding:16px 18px;
  margin-bottom:12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  text-decoration: none;
  color: #ffffff;
  display:block;
  transition: transform 0.08s ease, box-shadow 0.08s ease, border-color 0.08s ease, border-width 0.08s ease;
  overflow: visible;
  background: linear-gradient(180deg, rgba(10,20,30,0.95), rgba(6,12,20,0.95));
  position: relative;        /* so absolute children are anchored inside */
  padding-right: 180px;      /* reserve enough space for right-side elements */
  min-height: 72px;
}

/* Hover lift + thick green border so we know which mail we're on */
.ocean-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 26px rgba(0,0,0,0.35);
  border-color: #00ff88;
  border-width: 2px;
}

/* Row layout */
.ocean-row { display:flex; justify-content:space-between; align-items:center; gap:12px; }
.ocean-left { flex:1; min-width:0; }

/* Top-line text (white) */
.ocean-sender { font-weight:600; font-size:15px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#fff; }
.ocean-subject { color:#ffffff; font-size:14px; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ocean-snippet { color:rgba(255,255,255,0.85); font-size:12px; margin-top:6px; max-height:40px; overflow:hidden; text-overflow:ellipsis; }

/* Right column (inside card) */
.ocean-right {
  position: absolute;
  right: 16px;
  top: 12px;
  width: 150px;
  text-align: right;
  z-index: 4;
  color: #fff;
}
.ocean-ts { font-size:12px; color:rgba(255,255,255,0.8); margin-bottom:8px; }
.ocean-category { margin-top:8px; display:inline-block; padding:4px 8px;border-radius:8px;font-size:12px; background:#08324a;color:#E6F7FF; }
.ocean-has-tasks { font-size:12px;color:#9be79b; margin-top:6px; display:block; }

/* Expandable preview area: closed by default, opened via explicit expand button (no hover dependency). */
.ocean-hover-reveal {
  position: relative;       /* allow z-index stacking */
  z-index: 2;               /* sit under the action icons */
  margin-top:10px;
  max-height:0;
  transition: max-height 0.45s ease, opacity 0.45s ease;
  opacity:0;
  overflow:hidden;
  font-size:13px;
  color:#ffffff; /* white text inside expanded preview */
}

/* When expanded (class added from Python), show the full preview content and let card grow fully */
.ocean-hover-reveal.expanded {
  max-height:none;
  opacity:1;
  overflow:visible;
}

/* Make the preview body preserve whitespace and be readable on dark bg */
.ocean-hover-reveal pre, .ocean-hover-reveal div {
  white-space: pre-wrap;
  line-height:1.35;
  color: #ffffff;
}

/* Ensure links/buttons inside the card remain visible */
.ocean-card a { color: inherit; text-decoration: none; }

/* Small actions area inside the card (moved to bottom-right to avoid overlapping text) */
.ocean-actions {
  position: absolute;
  right: 14px;
  bottom: 12px;       /* moved from top to bottom to avoid overlapping the main text */
  top: auto;          /* ensure top doesn't interfere */
  display:flex;
  gap:6px;
  align-items:center;
  z-index: 10050;  /* increased so buttons remain clickable/visible above the bottom editor */
}
/* --- FIX: reduce the visible button size but keep center position intact --- */
.ocean-actions a {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:28px;        /* reduced width */
  height:28px;       /* reduced height */
  padding:0;         /* remove extra padding so size is stable */
  border-radius:6px;
  background: rgba(255,255,255,0.03);
  color: #fff;
  text-decoration:none;
  border:1px solid rgba(255,255,255,0.04);
  font-size:14px;
  line-height:1;     /* keep icon centered */
  position: relative; /* ensure anchors stack above surrounding elements */
  z-index: 10051;     /* slightly above .ocean-actions to be safe */
}

/* Full-width expand bar to visually match the card width */
.ocean-expand-btn {
  display: block;
  width: 100%;
  margin-top: 10px;
  padding: 8px 10px;
  text-align: center;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.18);
  background: rgba(255,255,255,0.04);
  font-size: 13px;
  line-height: 1.2;
  cursor: pointer;
  user-select: none;
  color: #ffffff;
  transition: background 0.15s ease;
}
.ocean-expand-btn:hover {
  background: rgba(255,255,255,0.12);
}
</style>
"""

# Bottom editor panel CSS — depends on mail id
def bottom_editor_css(mid: int) -> str:
    return f"""
            <style>
            /* inline editor panel shown directly below the selected mail */
            .bottom-editor {{
              position: relative;
              margin-top: 10px;
              background: linear-gradient(180deg, rgba(8,12,16,0.98), rgba(4,6,10,0.98));
              border: 1px solid rgba(255,255,255,0.06);
              border-radius: 10px;
              padding: 14px;
              z-index: 40;
              box-shadow: 0 8px 40px rgba(0,0,0,0.6);
              width: 100%;
            }}
            /* ensure inputs inside panel use full width */
            .bottom-editor .stTextInput, .bottom-editor .stTextArea {{
              width: 100% !important;
            }}
            </style>
            <div class="bottom-editor" id="bottom_edit_{mid}"></div>
            """
