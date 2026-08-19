"""Presentation-layer helpers only -- no simulation logic lives here.
Custom CSS + small HTML-card builders so the dashboard reads as a
professional analytics product instead of default Streamlit widgets. All
values rendered by these helpers are still passed in from the real
pipeline; this module only changes how they look."""
from __future__ import annotations

import streamlit as st

STATUS_COLORS = {
    "RECOMMENDED": "#0f9d58", "ECONOMICALLY_VIABLE": "#2d9cdb", "TECHNICALLY_PLAUSIBLE": "#f2a900",
    "DISCOVERED": "#8a94a6", "REJECTED": "#d93025", "OK": "#0f9d58", "WARN": "#f2a900", "BAD": "#d93025",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }

.block-container { padding-top: 1.6rem; max-width: 1300px; }

/* ---- hero header ---- */
.ag-hero {
    background: linear-gradient(120deg, #0b1e3d 0%, #123a6b 55%, #1c5fa8 100%);
    border-radius: 20px; padding: 28px 32px; color: #fff; margin-bottom: 22px;
    box-shadow: 0 8px 24px rgba(16,24,64,.18);
}
.ag-hero h1 { font-size: 30px; font-weight: 800; margin: 0 0 4px 0; letter-spacing: -0.01em; }
.ag-hero p { font-size: 14.5px; color: #cfe0f7; margin: 0; max-width: 780px; line-height: 1.5; }
.ag-badges { margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
.ag-badge {
    display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,.12);
    border: 1px solid rgba(255,255,255,.22); color: #eaf2ff; font-size: 11.5px; font-weight: 600;
    padding: 5px 11px; border-radius: 999px; letter-spacing: .02em;
}
.ag-badge.dot::before { content:""; width:6px; height:6px; border-radius:50%; background:#34d399; display:inline-block; }

/* ---- KPI cards ---- */
.ag-kpi-row { display: flex; gap: 14px; margin: 4px 0 20px 0; flex-wrap: wrap; }
.ag-kpi-card {
    flex: 1; min-width: 155px; background: #fff; border-radius: 14px; padding: 16px 18px;
    border: 1px solid #eaecf2; box-shadow: 0 1px 2px rgba(16,24,40,.05);
}
.ag-kpi-label { font-size: 11px; font-weight: 700; color: #667085; letter-spacing: .08em; text-transform: uppercase; }
.ag-kpi-value { font-size: 25px; font-weight: 800; color: #101828; margin-top: 4px; }
.ag-kpi-sub { font-size: 11.5px; color: #8a94a6; margin-top: 3px; }

/* ---- section headers ---- */
.ag-section-title { font-size: 17px; font-weight: 750; color: #101828; margin: 6px 0 2px 0; }
.ag-section-sub { font-size: 12.5px; color: #667085; margin-bottom: 10px; }

/* ---- status pill ---- */
.ag-pill {
    display: inline-block; font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
    color: #fff; letter-spacing: .03em;
}

/* ---- tutorial / concept cards ---- */
.ag-card {
    background: #fff; border: 1px solid #eaecf2; border-radius: 14px; padding: 16px 18px;
    box-shadow: 0 1px 2px rgba(16,24,40,.05); height: 100%;
}
.ag-card h4 { margin: 0 0 6px 0; font-size: 15px; font-weight: 700; color: #101828; }
.ag-card p { margin: 0; font-size: 12.5px; color: #667085; line-height: 1.5; }
.ag-card .ag-tag {
    display:inline-block; font-size: 10.5px; font-weight: 700; color:#2563eb; background:#eaf1ff;
    padding: 2px 8px; border-radius: 6px; margin-bottom: 8px; letter-spacing:.02em;
}

/* ---- glossary ---- */
.ag-term { font-weight: 700; color: #101828; }

hr { margin: 1.3rem 0 !important; }
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, badges: list[str]) -> None:
    badge_html = "".join(f'<span class="ag-badge dot">{b}</span>' for b in badges)
    st.markdown(
        f"""<div class="ag-hero"><h1>{title}</h1><p>{subtitle}</p>
        <div class="ag-badges">{badge_html}</div></div>""",
        unsafe_allow_html=True,
    )


def kpi_row(items: list[tuple[str, str, str]]) -> None:
    """items: list of (label, value, subtext)"""
    cards = "".join(
        f'<div class="ag-kpi-card"><div class="ag-kpi-label">{label}</div>'
        f'<div class="ag-kpi-value">{value}</div><div class="ag-kpi-sub">{sub}</div></div>'
        for label, value, sub in items
    )
    st.markdown(f'<div class="ag-kpi-row">{cards}</div>', unsafe_allow_html=True)


def section(title: str, subtitle: str = "") -> None:
    sub_html = f'<div class="ag-section-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="ag-section-title">{title}</div>{sub_html}', unsafe_allow_html=True)


def status_pill(text: str, kind: str = "OK") -> str:
    color = STATUS_COLORS.get(kind, "#667085")
    return f'<span class="ag-pill" style="background:{color}">{text}</span>'
