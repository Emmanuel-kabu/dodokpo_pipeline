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

/* Full-width content with comfortable gutters so the page fills wide monitors,
   consistent with the Executive page (no centered max-width cap). */
.block-container {{ max-width: 100%; padding: 2rem 3rem 3rem; }}

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


def _candidate_profile_data(peer_df: pd.DataFrame, email: str) -> dict | None:
    """Pure (Streamlit-free, testable) computation of everything the candidate
    profile renders. Returns None if there is no history for `email`.

    Retake order is reconstructed from start_time per test_id — the source's
    `attempt_number` is unreliable (always 1), so it must NOT be used for ordering.
    """
    if peer_df is None or peer_df.empty or "email" not in peer_df.columns:
        return None
    peer = peer_df.copy()
    for c in ["score_pct", "duration_min", "violation_count", "violation_duration_sec", "is_pass"]:
        if c in peer.columns:
            peer[c] = pd.to_numeric(peer[c], errors="coerce")
    peer["_start_dt"] = pd.to_datetime(peer.get("start_time"), errors="coerce")

    hist = peer[peer["email"] == email].copy()
    if hist.empty:
        return None
    hist = hist.sort_values("_start_dt", kind="stable")
    hist["_seq"] = (hist.groupby("test_id").cumcount() + 1) if "test_id" in hist.columns else 1

    name = (hist["candidatename"].dropna().iloc[0]
            if "candidatename" in hist.columns and hist["candidatename"].notna().any() else email)
    if not (isinstance(name, str) and name.strip()):
        name = email
    scores = hist["score_pct"].dropna()

    # Peer baseline (one avg per person)
    peer_means = peer.dropna(subset=["score_pct"]).groupby("email")["score_pct"].mean()
    peer_avg = float(peer_means.mean()) if not peer_means.empty else None
    rank = int(peer_means.rank(ascending=False, method="min").get(email)) if email in peer_means.index else None
    percentile = float(peer_means.rank(pct=True).get(email) * 100) if email in peer_means.index else None

    # Integrity vs peers
    integrity = peer_integrity_med = None
    if {"violation_count", "violation_duration_sec"}.issubset(peer.columns):
        peer_integ = peer.groupby("email").apply(
            lambda g: g["violation_count"].fillna(0).sum() * 2.0 + g["violation_duration_sec"].fillna(0).sum() / 60.0)
        integrity = float(peer_integ.get(email)) if email in peer_integ.index else None
        peer_integrity_med = float(peer_integ.median()) if not peer_integ.empty else None

    # Retake gap (days) — reconstructed from start_time, NOT attempt_number
    delays = []
    if "test_id" in hist.columns:
        for _t, g in hist.dropna(subset=["_start_dt"]).groupby("test_id"):
            if len(g) > 1:
                d = g.sort_values("_start_dt")["_start_dt"].diff().dropna().dt.total_seconds() / 86400.0
                delays.extend(d.tolist())
    avg_retake = (sum(delays) / len(delays)) if delays else None

    # Per-specialization (candidate vs peer)
    df_spec = None
    if "specialization" in hist.columns:
        cand_spec = hist.groupby("specialization").agg(
            attempts=("score_pct", "size"), avg=("score_pct", "mean"),
            pass_rate=("is_pass", lambda s: s.mean() * 100))
        peer_spec = peer.groupby("specialization")["score_pct"].mean().rename("peer_avg")
        df_spec = cand_spec.join(peer_spec).reset_index()

    # Per-difficulty
    df_diff = None
    if "test_difficulty" in hist.columns:
        df_diff = hist.groupby("test_difficulty").agg(
            attempts=("score_pct", "size"), avg=("score_pct", "mean"),
            pass_rate=("is_pass", lambda s: s.mean() * 100)).reset_index()

    # Retake effectiveness (re-sat tests only): first vs latest sitting
    df_retake = None
    if "test_id" in hist.columns:
        rows = []
        for _t, g in hist.groupby("test_id"):
            if len(g) > 1:
                g2 = g.sort_values("_seq")
                lbl = g2["test_title"].iloc[0] if "test_title" in g2.columns else str(_t)
                rows.append({"test": lbl, "sittings": len(g2),
                             "first": g2["score_pct"].iloc[0], "latest": g2["score_pct"].iloc[-1],
                             "lift": g2["score_pct"].iloc[-1] - g2["score_pct"].iloc[0]})
        df_retake = pd.DataFrame(rows)

    # Latest proficiency
    latest_prof = None
    if "proficiency_level" in hist.columns and hist["proficiency_level"].notna().any():
        latest_prof = hist.sort_values("_seq")["proficiency_level"].dropna().iloc[-1]

    # Flagged (violation) sittings
    df_viol = None
    if "violation_count" in hist.columns:
        v = hist[hist["violation_count"].fillna(0) > 0]
        if not v.empty:
            cols = [c for c in ["test_title", "_start_dt", "violation_count",
                                "violation_duration_sec", "score_pct", "pass_status"] if c in v.columns]
            df_viol = v[cols].sort_values("violation_count", ascending=False)

    cand_avg = float(scores.mean()) if not scores.empty else None

    # Narrative headline
    parts = []
    if cand_avg is not None and peer_avg is not None:
        parts.append("above peer avg" if cand_avg >= peer_avg else "below peer avg")
    if df_spec is not None and not df_spec.empty:
        parts.append(f"strongest in {df_spec.sort_values('avg', ascending=False).iloc[0]['specialization']}")
    if df_retake is not None and not df_retake.empty:
        up, down = int((df_retake["lift"] > 0).sum()), int((df_retake["lift"] < 0).sum())
        parts.append("retakes help" if up > down else ("retakes don't help" if down > up else "retakes mixed"))
    n_flag = int((hist["violation_count"].fillna(0) > 0).sum()) if "violation_count" in hist.columns else 0
    if n_flag:
        parts.append(f"{n_flag} flagged sitting(s)")

    return {
        "name": name, "hist": hist, "n_attempts": len(hist),
        "n_tests": int(hist["test_id"].nunique()) if "test_id" in hist.columns else None,
        "cand_avg": cand_avg,
        "cand_max": float(scores.max()) if not scores.empty else None,
        "cand_min": float(scores.min()) if not scores.empty else None,
        "peer_avg": peer_avg, "rank": rank, "total_peers": int(peer_means.shape[0]),
        "percentile": percentile, "peer_means": peer_means,
        "avg_time": float(hist["duration_min"].mean()) if "duration_min" in hist.columns and hist["duration_min"].notna().any() else None,
        "pass_rate": float((hist["pass_status"] == "passed").mean() * 100) if "pass_status" in hist.columns else None,
        "viol_total": float(hist["violation_count"].fillna(0).sum()) if "violation_count" in hist.columns else 0,
        "n_flagged": n_flag, "integrity": integrity, "peer_integrity_med": peer_integrity_med,
        "avg_retake": avg_retake, "latest_prof": latest_prof, "last_active": hist["_start_dt"].max(),
        "df_spec": df_spec, "df_diff": df_diff, "df_retake": df_retake, "df_viol": df_viol,
        "headline": " · ".join(parts),
    }


@st.dialog("Candidate Profile", width="large")
def candidate_profile(peer_df: pd.DataFrame, email: str, group_label: str, nonce_key: str) -> None:
    """Shared candidate profile (tabbed: Overview · Skills · Retakes · Integrity).
    `peer_df` is the pre-filtered peer set; `group_label` names it. All computation
    is in `_candidate_profile_data` (pure/testable); this only renders.
    """
    TPL = active_theme()["template"]
    d = _candidate_profile_data(peer_df, email)
    if d is None:
        st.warning("No attempts found for this candidate.")
        if st.button("Close"):
            st.session_state[nonce_key] = st.session_state.get(nonce_key, 0) + 1
            st.rerun()
        return

    hist = d["hist"]
    st.markdown(f"### {d['name']}")
    sub = f"{email}  ·  vs **{group_label}**  ·  {d['n_attempts']} sitting(s)"
    if d["n_tests"]:
        sub += f" across {d['n_tests']} test(s)"
    if d["last_active"] is not None and pd.notna(d["last_active"]):
        sub += f"  ·  last active {d['last_active'].date()}"
    st.caption(sub)
    if d["headline"]:
        st.markdown(
            f"<div style='border-left:3px solid {ORANGE};padding:4px 10px;margin:2px 0 10px;"
            f"opacity:0.85;font-size:13px'>{d['headline']}</div>", unsafe_allow_html=True)

    t_over, t_skill, t_retake, t_integ = st.tabs(
        ["Overview", "Skills", "Retakes", "🛡 Integrity"])

    # ───────────────────────── Overview ─────────────────────────
    with t_over:
        r1 = st.columns(5)
        if d["cand_avg"] is not None and d["peer_avg"] is not None:
            diff = d["cand_avg"] - d["peer_avg"]
            r1[0].metric("Avg Score", f"{d['cand_avg']:.1f}%",
                         delta=f"{diff:+.1f} pts vs peer {d['peer_avg']:.1f}%")
        else:
            r1[0].metric("Avg Score", f"{d['cand_avg']:.1f}%" if d["cand_avg"] is not None else "—")
        r1[1].metric("Percentile", f"{d['percentile']:.0f}th" if d["percentile"] is not None else "—",
                     delta=(f"rank {d['rank']}/{d['total_peers']}" if d["rank"] else None), delta_color="off")
        r1[2].metric("Pass Rate", f"{d['pass_rate']:.0f}%" if d["pass_rate"] is not None else "—")
        r1[3].metric("Latest Proficiency", d["latest_prof"] or "—")
        r1[4].metric("Avg Time", f"{d['avg_time']:.1f} min" if d["avg_time"] is not None else "—")

        r2 = st.columns(5)
        r2[0].metric("Best", f"{d['cand_max']:.1f}%" if d["cand_max"] is not None else "—")
        r2[1].metric("Worst", f"{d['cand_min']:.1f}%" if d["cand_min"] is not None else "—")
        r2[2].metric("Avg Retake Gap", f"{d['avg_retake']:.1f} days" if d["avg_retake"] is not None else "—")
        r2[3].metric("Flagged Sittings", fmt_int(d["n_flagged"]))
        r2[4].metric("Integrity Risk", f"{d['integrity']:.0f}" if d["integrity"] is not None else "—",
                     delta=(f"peer median {d['peer_integrity_med']:.0f}" if d["peer_integrity_med"] is not None else None),
                     delta_color="off")

        # Where they sit in the peer score distribution
        pm = d["peer_means"]
        if pm is not None and len(pm) > 1 and d["cand_avg"] is not None:
            st.markdown("<div class='card-title'>Position vs Peers (avg-score distribution)</div>", unsafe_allow_html=True)
            fig_h = px.histogram(pm.to_frame("avg"), x="avg", nbins=25, template=TPL,
                                 color_discrete_sequence=[NAVY], labels={"avg": "Peer avg score %"})
            fig_h.add_vline(x=d["cand_avg"], line_color=ORANGE, line_width=3,
                            annotation_text=f"{d['name'].split()[0]} {d['cand_avg']:.0f}%")
            fig_h.update_layout(height=240, margin=dict(t=10, b=10, l=0, r=0), showlegend=False, bargap=0.05)
            st.plotly_chart(fig_h, use_container_width=True)

        # Score trend, segmented by specialization where available
        st.markdown("<div class='card-title'>Score Trend Over Time</div>", unsafe_allow_html=True)
        tl = hist.dropna(subset=["_start_dt"]).sort_values("_start_dt")
        if not tl.empty:
            color = "specialization" if ("specialization" in tl.columns and tl["specialization"].nunique() > 1) else None
            figt = px.line(tl, x="_start_dt", y="score_pct", markers=True, color=color, template=TPL,
                           labels={"_start_dt": "", "score_pct": "Score %", "specialization": ""})
            if color is None:
                figt.update_traces(line_color=ORANGE)
            figt.add_hline(y=80, line_dash="dot", line_color=GREEN, annotation_text="Advanced")
            figt.add_hline(y=50, line_dash="dot", line_color=AMBER, annotation_text="Intermediate")
            figt.update_layout(height=260, margin=dict(t=10, b=10, l=0, r=0), yaxis=dict(range=[0, 105]),
                               legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(figt, use_container_width=True)
            if color:
                st.caption("Each line is one specialization — separates real learning from test-to-test mix.")
        else:
            st.caption("No timestamped attempts.")

    # ───────────────────────── Skills ───────────────────────────
    with t_skill:
        if d["df_spec"] is not None and not d["df_spec"].empty:
            st.markdown("<div class='card-title'>By Specialization — Candidate vs Peer Avg</div>", unsafe_allow_html=True)
            sp = d["df_spec"].sort_values("avg", ascending=False)
            mlt = sp.melt(id_vars="specialization", value_vars=["avg", "peer_avg"],
                          var_name="who", value_name="score")
            mlt["who"] = mlt["who"].map({"avg": d["name"].split()[0], "peer_avg": "Peer avg"})
            fig_sp = px.bar(mlt, x="specialization", y="score", color="who", barmode="group", template=TPL,
                            color_discrete_sequence=[ORANGE, SLATE], labels={"specialization": "", "score": "Avg %", "who": ""})
            fig_sp.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0), yaxis=dict(range=[0, 105]),
                                 legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_sp, use_container_width=True)
            st.caption("Specialization is ~half genuine on current data (rest force-mapped) — read directionally.")
        if d["df_diff"] is not None and not d["df_diff"].empty:
            st.markdown("<div class='card-title'>By Assessment Level</div>", unsafe_allow_html=True)
            _do = ["Beginner", "Intermediate", "Advanced"]
            dd = d["df_diff"].set_index("test_difficulty").reindex(_do).dropna(how="all").reset_index()
            fig_dd = px.bar(dd, x="test_difficulty", y="avg", template=TPL, text=dd["pass_rate"].round(0).astype("Int64").astype(str) + "% pass",
                            color="avg", color_continuous_scale=[[0, RED], [0.5, AMBER], [1, GREEN]], range_color=[0, 100],
                            labels={"test_difficulty": "", "avg": "Avg Score %"})
            fig_dd.update_traces(textposition="outside")
            fig_dd.update_layout(height=280, margin=dict(t=10, b=10, l=0, r=0), coloraxis_showscale=False, yaxis=dict(range=[0, 115]))
            st.plotly_chart(fig_dd, use_container_width=True)
        if (d["df_spec"] is None or d["df_spec"].empty) and (d["df_diff"] is None or d["df_diff"].empty):
            st.info("No specialization / difficulty breakdown available.")

    # ───────────────────────── Retakes ──────────────────────────
    with t_retake:
        dr = d["df_retake"]
        if dr is None or dr.empty:
            st.info("This candidate never re-sat a test in the current selection.")
        else:
            up, down = int((dr["lift"] > 0).sum()), int((dr["lift"] < 0).sum())
            st.caption(f"{len(dr)} re-sat test(s): {up} improved, {down} got worse, "
                       f"{len(dr) - up - down} unchanged. Avg gap "
                       f"{d['avg_retake']:.1f} days." if d["avg_retake"] is not None else
                       f"{len(dr)} re-sat test(s): {up} improved, {down} got worse.")
            dr2 = (dr.assign(_abs=dr["lift"].abs())
                   .sort_values("_abs", ascending=False).head(20).sort_values("lift"))
            dr2["dir"] = dr2["lift"].apply(lambda x: "Improved" if x > 0 else ("Declined" if x < 0 else "Same"))
            fig_r = px.bar(dr2, x="lift", y="test", orientation="h", color="dir", template=TPL,
                           color_discrete_map={"Improved": GREEN, "Declined": RED, "Same": SLATE},
                           labels={"lift": "Score change (latest − first), pts", "test": "", "dir": ""})
            fig_r.update_layout(height=max(220, 30 * len(dr2)), margin=dict(t=10, b=10, l=0, r=0),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_r, use_container_width=True)
            if len(dr) > 20:
                st.caption(f"Chart shows the 20 largest changes of {len(dr)} re-sat tests; full list below.")
            st.dataframe(
                dr.sort_values("lift")[["test", "sittings", "first", "latest", "lift"]].rename(columns={
                    "test": "Test", "sittings": "Sittings", "first": "First %", "latest": "Latest %", "lift": "Lift (pts)"}),
                use_container_width=True, hide_index=True,
                column_config={
                    "First %": st.column_config.NumberColumn(format="%.1f%%"),
                    "Latest %": st.column_config.NumberColumn(format="%.1f%%"),
                    "Lift (pts)": st.column_config.NumberColumn(format="%+.1f"),
                })

    # ───────────────────────── Integrity ────────────────────────
    with t_integ:
        cols = st.columns(3)
        cols[0].metric("Integrity Risk", f"{d['integrity']:.0f}" if d["integrity"] is not None else "—",
                       delta=(f"peer median {d['peer_integrity_med']:.0f}" if d["peer_integrity_med"] is not None else None),
                       delta_color="off")
        cols[1].metric("Flagged Sittings", fmt_int(d["n_flagged"]))
        cols[2].metric("Total Violations", fmt_int(d["viol_total"]))
        dv = d["df_viol"]
        if dv is None or dv.empty:
            st.success("No test-window violations on record — clean integrity profile.", icon="✅")
        else:
            st.markdown("<div class='card-title'>Flagged Sittings</div>", unsafe_allow_html=True)
            ren = {"test_title": "Test", "_start_dt": "When", "violation_count": "Violations",
                   "violation_duration_sec": "Viol. secs", "score_pct": "Score %", "pass_status": "Outcome"}
            st.dataframe(
                dv.rename(columns=ren), use_container_width=True, hide_index=True,
                column_config={
                    "When": st.column_config.DatetimeColumn("When", format="YYYY-MM-DD HH:mm"),
                    "Score %": st.column_config.NumberColumn(format="%.1f%%"),
                })
            st.caption("Risk score = 2×violations + violation-minutes. Review queue, not a verdict.")

    # ───────────────────────── Footer ───────────────────────────
    st.divider()
    fcols = st.columns([1, 1])
    fcols[0].download_button(
        "⬇ Export this candidate's sittings (CSV)",
        hist.drop(columns=[c for c in ["_start_dt"] if c in hist.columns]).to_csv(index=False).encode(),
        file_name=f"candidate_{email.split('@')[0]}.csv", mime="text/csv", use_container_width=True)
    if fcols[1].button("Close", type="primary", use_container_width=True):
        st.session_state[nonce_key] = st.session_state.get(nonce_key, 0) + 1
        st.rerun()
