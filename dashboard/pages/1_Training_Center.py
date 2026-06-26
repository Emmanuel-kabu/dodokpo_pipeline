"""Training Center dashboard — performance by Year → Specialization (+ optional Cohort).

Sourced from the attempt-level view so specialization analysis spans ALL real-
specialization attempts (the same specialization set as the Service Center), not just
program-tagged cohorts. Cohort (NSP/Graduate/…) is an optional extra filter.
The candidate roster is one row per person; click to open their profile.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import shared as sh

st.set_page_config(page_title="Dodokpo · Training Center", page_icon="🎓", layout="wide",
                   initial_sidebar_state="collapsed")
sh.inject_css()
T = sh.active_theme()
TPL = T["template"]

sh.render_nav("training")
sh.page_header("🎓 Training Center", "Performance by Year → Specialization (+ optional Cohort) · Gold Layer")

# ---------------------------------------------------------------------------
# Load attempt-level data (single source) + coverage gauge
# ---------------------------------------------------------------------------
with st.spinner("Loading analytics from Athena…"):
    attempts_all, e1 = sh.query_view("cohort_specialization_attempt", limit=50_000)
    coverage, e2 = sh.query_view("additional_analytics_coverage", limit=1)

errors = [e for e in (e1, e2) if e]
if errors:
    st.error("**Some views failed to load:**\n\n" + "\n\n".join(errors))

# Working set = every attempt. Aptitude / Internal-Test domains are now force-mapped
# into the 8 real specializations upstream (is_excluded is always false), so this
# filter is a defensive no-op that keeps all attempts and matches the Service Center.
base = attempts_all.copy()
if not base.empty:
    base["_excluded"] = base.get("is_excluded").astype(str).str.lower() == "true"
    base = base[(~base["_excluded"]) & (base.get("specialization") != "Unmapped")].copy()
    for nc in ["score_pct", "duration_min", "attempt_number", "violation_count",
               "violation_duration_sec", "is_pass"]:
        if nc in base.columns:
            base[nc] = pd.to_numeric(base[nc], errors="coerce")
    base["_year"] = base.get("attempt_year").astype(str).str.slice(0, 4)

# ---------------------------------------------------------------------------
# Top slicer bar — Year → Specialization → Cohort (optional)
# ---------------------------------------------------------------------------
with st.container(border=True):
    fc = st.columns(3)
    years = sorted([y for y in base.get("_year", pd.Series(dtype=str)).dropna().unique().tolist()
                    if y and y.lower() != "nan"]) if not base.empty else []
    sel_year = fc[0].multiselect("Year", years, default=[], placeholder="All years")

    spec_pool = base[base["_year"].isin(sel_year)] if (sel_year and not base.empty) else base
    specs = sorted(spec_pool.get("specialization", pd.Series(dtype=str)).dropna().unique().tolist())
    sel_spec = fc[1].multiselect("Specialization", specs, default=[], placeholder="All specializations")

    prog_pool = base
    if sel_year and not base.empty:
        prog_pool = prog_pool[prog_pool["_year"].isin(sel_year)]
    if sel_spec:
        prog_pool = prog_pool[prog_pool["specialization"].isin(sel_spec)]
    programs = sorted(prog_pool.get("program_type", pd.Series(dtype=str)).dropna().unique().tolist())
    sel_cohort = fc[2].multiselect("Cohort (program)", programs, default=[], placeholder="All cohorts")

# Apply filters
f = base
if not f.empty:
    if sel_year:
        f = f[f["_year"].isin(sel_year)]
    if sel_spec:
        f = f[f["specialization"].isin(sel_spec)]
    if sel_cohort:
        f = f[f["program_type"].isin(sel_cohort)]

# Label describing the current selection (used by the profile's "vs …")
_lbl = []
if sel_year:
    _lbl.append(", ".join(map(str, sel_year)))
if sel_cohort:
    _lbl.append(", ".join(sel_cohort))
if sel_spec:
    _lbl.append(", ".join(sel_spec))
group_label = " · ".join(_lbl) if _lbl else "All Specializations"

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
attempts = len(f)
candidates = f["email"].nunique() if "email" in f.columns and not f.empty else 0
n_spec = f["specialization"].nunique() if "specialization" in f.columns and not f.empty else 0
pass_rate = (f["is_pass"].mean() * 100) if "is_pass" in f.columns and not f.empty else None
avg_score = f["score_pct"].mean() if "score_pct" in f.columns and not f.empty else None

k = st.columns(5)
k[0].metric("Specializations", sh.fmt_int(n_spec))
k[1].metric("Candidates", sh.fmt_int(candidates))
k[2].metric("Attempts", sh.fmt_int(attempts))
k[3].metric("Pass Rate", sh.fmt_float(pass_rate, 1, "%") if pass_rate is not None else "—")
k[4].metric("Avg Score", sh.fmt_float(avg_score, 1, "%") if avg_score is not None else "—")

st.divider()

if f.empty:
    st.info("No attempts for the current selection.")
else:
    # ── Specialization performance ────────────────────────────────
    st.markdown("<div class='card-title'>Specialization Performance — Pass Rate & Avg Score</div>", unsafe_allow_html=True)
    sp = f.groupby("specialization").agg(
        attempts=("email", "size"),
        pass_rate_pct=("is_pass", lambda s: s.mean() * 100),
        avg_score_pct=("score_pct", "mean"),
    ).reset_index().sort_values("attempts", ascending=False)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=sp["specialization"], y=sp["pass_rate_pct"], name="Pass Rate %", marker_color=sh.ORANGE))
    fig.add_trace(go.Scatter(x=sp["specialization"], y=sp["avg_score_pct"], name="Avg Score %",
                             mode="lines+markers", line=dict(color=sh.DARK_BLUE, width=2.5, dash="dot"),
                             marker=dict(size=9)))
    fig.update_layout(template=TPL, height=300, margin=dict(t=20, b=10, l=0, r=0), bargap=0.45,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02), yaxis=dict(title="%", range=[0, 105]))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    # ── Proficiency mix by specialization ─────────────────────────
    with c1:
        st.markdown("<div class='card-title'>Proficiency Mix by Specialization</div>", unsafe_allow_html=True)
        if "proficiency_level" in f.columns:
            pm = (f.groupby(["specialization", "proficiency_level"]).size()
                  .reset_index(name="n"))
            fig_p = px.bar(pm, x="specialization", y="n", color="proficiency_level", barmode="stack",
                           template=TPL, color_discrete_map={"Advanced": sh.GREEN, "Intermediate": sh.AMBER, "Beginner": sh.RED},
                           labels={"specialization": "", "n": "Attempts", "proficiency_level": ""})
            fig_p.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_p, use_container_width=True)

    # ── Cohort performance (only the program-tagged slice) ────────
    with c2:
        st.markdown("<div class='card-title'>Cohort Performance (program-tagged)</div>", unsafe_allow_html=True)
        fc2 = f[f.get("cohort") != "Unassigned"] if "cohort" in f.columns else f.iloc[0:0]
        if not fc2.empty:
            cp = fc2.groupby("cohort").agg(
                pass_rate_pct=("is_pass", lambda s: s.mean() * 100),
                avg_score_pct=("score_pct", "mean"),
            ).reset_index()
            fig_c = px.bar(cp, x="cohort", y="avg_score_pct", template=TPL,
                           color="avg_score_pct", color_continuous_scale=[[0, sh.RED], [0.5, sh.AMBER], [1, sh.GREEN]],
                           range_color=[0, 100], labels={"cohort": "", "avg_score_pct": "Avg Score %"})
            fig_c.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0), coloraxis_showscale=False,
                                yaxis=dict(range=[0, 105]))
            st.plotly_chart(fig_c, use_container_width=True)
        else:
            st.caption("No program-tagged cohorts in this selection (cohort tags are sparse upstream).")

    # ── Trend over time ───────────────────────────────────────────
    if "attempt_month" in f.columns and f["attempt_month"].notna().any():
        st.markdown("<div class='card-title'>Avg Score over Time</div>", unsafe_allow_html=True)
        tr = (f[f["attempt_month"].astype(str).str.len() >= 7]
              .groupby("attempt_month").agg(avg_score_pct=("score_pct", "mean"),
                                            attempts=("email", "size")).reset_index().sort_values("attempt_month"))
        if not tr.empty:
            fig_t = px.line(tr, x="attempt_month", y="avg_score_pct", markers=True, template=TPL,
                            labels={"attempt_month": "", "avg_score_pct": "Avg Score %"})
            fig_t.update_traces(line_color=sh.ORANGE)
            fig_t.update_layout(height=240, margin=dict(t=10, b=10, l=0, r=0), yaxis=dict(range=[0, 105]))
            st.plotly_chart(fig_t, use_container_width=True)

# ---------------------------------------------------------------------------
# Candidate roster (one row per person) — click a row for the profile
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### Candidates")
st.caption(f"One row per candidate in the current selection (**{group_label}**) — "
           f"**click a candidate** to open their profile.")
if f.empty:
    st.info("No candidates for the current selection.")
else:
    fs = f.sort_values(["email", "attempt_number"])
    g = f.groupby("email")
    roster = pd.DataFrame({
        "candidatename": g["candidatename"].first(),
        "attempts": g.size(),
        "tests_taken": g["test_id"].nunique(),
        "pass_rate_pct": g["is_pass"].mean() * 100,
        "avg_score_pct": g["score_pct"].mean(),
        "best_score_pct": g["score_pct"].max(),
        "integrity_risk": g["violation_count"].sum() * 2 + g["violation_duration_sec"].sum() / 60,
    })
    roster["latest_proficiency"] = fs.groupby("email")["proficiency_level"].last()
    roster["improvement"] = fs.groupby("email")["score_pct"].last() - fs.groupby("email")["score_pct"].first()
    roster = roster.reset_index()
    roster["rank"] = roster["avg_score_pct"].rank(ascending=False, method="min").astype("Int64")
    roster["percentile"] = roster["avg_score_pct"].rank(pct=True)
    roster = roster.sort_values("rank").reset_index(drop=True)

    roster_key = f"tc_roster_{st.session_state.get('tc_roster_nonce', 0)}"
    event = st.dataframe(
        roster.rename(columns={
            "rank": "Rank", "candidatename": "Candidate", "email": "Email",
            "attempts": "Attempts", "tests_taken": "Tests", "pass_rate_pct": "Pass Rate (%)",
            "avg_score_pct": "Avg Score (%)", "best_score_pct": "Best (%)",
            "latest_proficiency": "Latest Proficiency", "improvement": "Improvement",
            "integrity_risk": "Integrity Risk", "percentile": "Percentile",
        })[["Rank", "Candidate", "Email", "Attempts", "Tests", "Pass Rate (%)", "Avg Score (%)",
            "Best (%)", "Latest Proficiency", "Improvement", "Integrity Risk", "Percentile"]],
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key=roster_key,
        column_config={
            "Pass Rate (%)": st.column_config.ProgressColumn("Pass Rate", format="%.1f%%", min_value=0, max_value=100),
            "Avg Score (%)": st.column_config.NumberColumn("Avg Score", format="%.1f%%"),
            "Best (%)": st.column_config.NumberColumn("Best", format="%.1f%%"),
            "Percentile": st.column_config.NumberColumn("Percentile", format="%.2f"),
        },
    )
    st.download_button("⬇ Export candidates (CSV)", roster.to_csv(index=False).encode(),
                       file_name="training_center_candidates.csv", mime="text/csv")
    if event and event.get("selection", {}).get("rows"):
        idx = event["selection"]["rows"][0]
        sel = roster.iloc[idx]
        sh.candidate_profile(f, sel.get("email"), group_label, "tc_roster_nonce")
