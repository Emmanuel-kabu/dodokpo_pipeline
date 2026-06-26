"""Shared UI + data helpers for the Dodokpo multi-dashboard app.

Used by the Training Center page (and the nav bar on the Executive page). Keeps
branding, theming, Athena access and formatters in one place so the cohort/
specialization page stays consistent with the original Executive dashboard
(app.py, which now carries the specialization slicer) without duplicating its
internals.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from data_access import AthenaViewReader

# ---------------------------------------------------------------------------
# Brand palette (matches app.py)
# ---------------------------------------------------------------------------
ORANGE = "#F97316"
ORANGE_DARK = "#C2410C"
ORANGE_LIGHT = "#FED7AA"
DARK_BLUE = "#0F172A"
NAVY = "#1E3A8A"
SLATE = "#334155"
GREEN = "#10B981"
AMBER = "#F59E0B"
RED = "#EF4444"

# Athena connection (same gold database the org views live in)
ATHENA_DATABASE = "dodokpo_dev_gold"
ATHENA_WORKGROUP = "dodokpo-dev-workgroup"
ATHENA_RESULTS_BUCKET = "dodokpo-dev-athena-results"
ATHENA_REGION = "eu-west-1"

# Transparent-background Plotly templates so charts blend into either theme.
pio.templates["dodokpo_dark"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#E2E8F0"),
    xaxis=dict(gridcolor="#334155", zerolinecolor="#334155"),
    yaxis=dict(gridcolor="#334155", zerolinecolor="#334155"),
))
pio.templates["dodokpo_light"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#0F172A"),
    xaxis=dict(gridcolor="#E2E8F0", zerolinecolor="#E2E8F0"),
    yaxis=dict(gridcolor="#E2E8F0", zerolinecolor="#E2E8F0"),
))

_THEME = {
    "dark":  {"text": "#E2E8F0", "muted": "#94A3B8", "border": "#334155",
              "template": "plotly_dark+dodokpo_dark"},
    "light": {"text": "#0F172A", "muted": "#475569", "border": "#CBD5E1",
              "template": "plotly_white+dodokpo_light"},
}


def active_theme() -> dict:
    """Return theme tokens (text/muted/border/template) for the live theme."""
    try:
        kind = (st.context.theme.type or "light").lower()
    except Exception:
        kind = "light"
    return _THEME.get(kind, _THEME["light"])


def inject_css() -> None:
    """Inject the shared brand CSS (mirrors app.py — theme-agnostic accents)."""
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}

/* Compact, centered report column — keeps charts from stretching edge-to-edge
   on wide monitors (bars stay readable, the trend line stays short). */
.block-container {{ max-width: 1080px; padding-top: 2rem; padding-bottom: 3rem; }}

section[data-testid="stSidebar"] {{ background-color: {DARK_BLUE} !important; }}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: #E2E8F0 !important; }}
section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {{
    color: {ORANGE} !important; text-transform: uppercase; letter-spacing: 0.6px;
    font-size: 13px !important; font-weight: 700 !important;
}}
section[data-testid="stSidebar"] label {{
    font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.6px;
    font-weight: 600 !important; opacity: 0.9;
}}

[data-testid="stMetricValue"] {{ font-size: 26px !important; font-weight: 800 !important; }}
[data-testid="stMetricLabel"] {{
    font-size: 11px !important; text-transform: uppercase !important;
    letter-spacing: 0.7px !important; font-weight: 700 !important; opacity: 0.75;
}}
div[data-testid="stMetric"] {{
    background: rgba(148,163,184,0.10); border: 1px solid rgba(148,163,184,0.18);
    border-left: 4px solid {ORANGE}; border-radius: 6px; padding: 14px 18px;
}}

.page-header {{ font-size: 28px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 2px; }}
.page-sub {{ font-size: 13px; opacity: 0.65; margin-bottom: 16px; }}
.card-title {{
    font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.7px;
    margin: 6px 0 10px; border-left: 3px solid {ORANGE}; padding-left: 8px; opacity: 0.8;
}}
</style>
""", unsafe_allow_html=True)


def render_nav(active: str) -> None:
    """Top-of-page navigation buttons shared by all three dashboards."""
    pages = [
        ("app.py",                        "Executive",       "🟧", "executive"),
        ("pages/1_Training_Center.py",    "Training Center", "🎓", "training"),
    ]
    cols = st.columns(len(pages))
    for col, (path, label, icon, key) in zip(cols, pages):
        col.page_link(path, label=label, icon=icon,
                      use_container_width=True, disabled=(key == active))


def page_header(title: str, subtitle: str) -> None:
    st.markdown(f"<div class='page-header'>{title}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='page-sub'>{subtitle}</div>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False, ttl=300)
def query_view(view: str, limit: int | None = 50_000,
               order_by: str | None = None) -> tuple[pd.DataFrame, str | None]:
    """Query one gold view. Returns (df, error_message|None)."""
    try:
        reader = AthenaViewReader(
            database=ATHENA_DATABASE, workgroup=ATHENA_WORKGROUP,
            results_bucket=ATHENA_RESULTS_BUCKET, region=ATHENA_REGION,
        )
        return reader.query_view(view, limit=limit, order_by=order_by), None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


def fmt_int(n) -> str:
    try:
        return f"{int(float(n)):,}"
    except (TypeError, ValueError):
        return "—"


def fmt_float(n, decimals: int = 1, suffix: str = "") -> str:
    try:
        return f"{float(n):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def weighted(df: pd.DataFrame, value_col: str, weight_col: str = "attempts") -> float | None:
    """Attempt-weighted average of value_col (so cohort/spec rates roll up right)."""
    if df.empty or value_col not in df.columns or weight_col not in df.columns:
        return None
    v = pd.to_numeric(df[value_col], errors="coerce")
    w = pd.to_numeric(df[weight_col], errors="coerce")
    mask = v.notna() & w.notna() & (w > 0)
    if not mask.any() or w[mask].sum() == 0:
        return None
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


@st.dialog("Candidate Profile", width="large")
def candidate_profile(peer_df: pd.DataFrame, email: str, group_label: str, nonce_key: str) -> None:
    """Shared candidate profile. `peer_df` is the pre-filtered peer set (a cohort,
    a specialization, or the current dashboard selection); `group_label` names it.
    Shows summary cards (incl. avg score vs the peer average), every assessment
    score, a score trend, and retake progression.
    """
    TPL = active_theme()["template"]
    if peer_df is None or peer_df.empty or "email" not in peer_df.columns:
        st.warning("Attempt-level data is unavailable.")
        return
    hist = peer_df[peer_df["email"] == email].copy()
    if hist.empty:
        st.warning("No attempts found for this candidate.")
        if st.button("Close"):
            st.rerun()
        return

    for c in ["score_pct", "duration_min", "attempt_number", "violation_count", "violation_duration_sec"]:
        if c in hist.columns:
            hist[c] = pd.to_numeric(hist[c], errors="coerce")
    hist["start_dt"] = pd.to_datetime(hist.get("start_time"), errors="coerce")
    name = (hist["candidatename"].dropna().iloc[0]
            if "candidatename" in hist.columns and hist["candidatename"].notna().any() else email)

    # Peer baseline = everyone in the passed-in peer set (the current selection)
    peer = peer_df.copy()
    peer["score_pct"] = pd.to_numeric(peer.get("score_pct"), errors="coerce")
    peer_avg = peer["score_pct"].mean()

    cand_avg, cand_max, cand_min = hist["score_pct"].mean(), hist["score_pct"].max(), hist["score_pct"].min()
    avg_time = hist["duration_min"].mean() if "duration_min" in hist.columns else None
    pass_rate = (hist["pass_status"] == "passed").mean() * 100 if "pass_status" in hist.columns else None
    viol_total = hist["violation_count"].sum() if "violation_count" in hist.columns else 0
    integrity = (hist["violation_count"].sum() * 2.0 + hist["violation_duration_sec"].sum() / 60.0
                 ) if {"violation_count", "violation_duration_sec"}.issubset(hist.columns) else None

    peer_means = peer.dropna(subset=["score_pct"]).groupby("email")["score_pct"].mean()
    total_peers = int(peer_means.shape[0])
    rank = int(peer_means.rank(ascending=False, method="min").get(email)) if email in peer_means.index else None

    delays = []
    if "test_id" in hist.columns:
        for _t, g in hist.dropna(subset=["start_dt"]).groupby("test_id"):
            if len(g) > 1:
                d = g.sort_values("attempt_number")["start_dt"].diff().dropna().dt.total_seconds() / 86400.0
                delays.extend(d.tolist())
    avg_retake = (sum(delays) / len(delays)) if delays else None

    st.markdown(f"### {name}")
    st.caption(f"{email}  ·  vs **{group_label}**  ·  {len(hist)} attempt(s)")

    r1 = st.columns(5)
    if pd.notna(cand_avg) and pd.notna(peer_avg):
        diff = cand_avg - peer_avg
        rel = (diff / peer_avg * 100) if peer_avg else 0
        r1[0].metric(f"Avg Score vs {group_label}", f"{cand_avg:.1f}%",
                     delta=f"{diff:+.1f} pts ({rel:+.0f}%) vs {peer_avg:.1f}%")
    else:
        r1[0].metric(f"Avg Score vs {group_label}", f"{cand_avg:.1f}%" if pd.notna(cand_avg) else "—")
    r1[1].metric("Max Score", f"{cand_max:.1f}%" if pd.notna(cand_max) else "—")
    r1[2].metric("Min Score", f"{cand_min:.1f}%" if pd.notna(cand_min) else "—")
    r1[3].metric("Avg Time Spent", f"{avg_time:.1f} min" if avg_time is not None and pd.notna(avg_time) else "—")
    r1[4].metric("Avg Retake Delay", f"{avg_retake:.1f} days" if avg_retake is not None else "—")

    r2 = st.columns(4)
    r2[0].metric("Pass Rate", f"{pass_rate:.0f}%" if pass_rate is not None and pd.notna(pass_rate) else "—")
    r2[1].metric(f"Rank in {group_label}", f"{rank} / {total_peers}" if rank else "—")
    r2[2].metric("Total Violations", fmt_int(viol_total))
    r2[3].metric("Integrity Risk", f"{integrity:.1f}" if integrity is not None and pd.notna(integrity) else "—")

    st.divider()

    # Every assessment score
    st.markdown("<div class='card-title'>Assessment Scores</div>", unsafe_allow_html=True)
    bar = hist.sort_values("start_dt").copy()
    bar["label"] = (bar["test_title"] if "test_title" in bar.columns else "Test")
    bar["label"] = bar["label"].fillna("Test").astype(str)
    if "attempt_number" in bar.columns:
        dup = bar["label"].duplicated(keep=False)
        bar.loc[dup, "label"] = bar.loc[dup].apply(
            lambda r: f"{r['label']} (#{int(r['attempt_number'])})" if pd.notna(r["attempt_number"]) else r["label"],
            axis=1)
    color_arg = "pass_status" if "pass_status" in bar.columns else None
    fig = px.bar(bar, x="label", y="score_pct", color=color_arg,
                 color_discrete_map={"passed": GREEN, "failed": RED}, template=TPL,
                 labels={"label": "", "score_pct": "Score %", "pass_status": "Outcome"})
    fig.update_layout(height=250, bargap=0.55, margin=dict(t=10, b=10, l=0, r=0),
                      yaxis=dict(range=[0, 105]), legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div class='card-title'>Score Trend Over Time</div>", unsafe_allow_html=True)
    tl = hist.dropna(subset=["start_dt"]).sort_values("start_dt")
    if not tl.empty:
        figt = px.line(tl, x="start_dt", y="score_pct", markers=True, template=TPL,
                       labels={"start_dt": "", "score_pct": "Score %"})
        figt.update_traces(line_color=ORANGE)
        figt.add_hline(y=80, line_dash="dot", line_color=GREEN, annotation_text="Advanced")
        figt.add_hline(y=50, line_dash="dot", line_color=AMBER, annotation_text="Intermediate")
        figt.update_layout(height=230, margin=dict(t=10, b=10, l=0, r=0), yaxis=dict(range=[0, 105]))
        st.plotly_chart(figt, use_container_width=True)
    else:
        st.caption("No timestamped attempts.")

    if st.button("Close", type="primary"):
        st.session_state[nonce_key] = st.session_state.get(nonce_key, 0) + 1
        st.rerun()
