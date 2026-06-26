"""Training Center dashboard — performance by Year → Specialization (+ optional Cohort).

Sourced from the attempt-level view so specialization analysis spans ALL real-
specialization attempts (the same specialization set as the Service Center), not just
program-tagged cohorts. Cohort (NSP/Graduate/…) is an optional extra filter.
The candidate roster is one row per person; click to open their profile.
"""
from __future__ import annotations

import html
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import shared as sh

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html_tc(value) -> str:
    """Render authoring-tool question HTML as clean plain text for tables."""
    if not isinstance(value, str) or not value:
        return ""
    s = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    s = re.sub(r"</(p|div|li)>", " ", s, flags=re.IGNORECASE)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

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
    qperf, e3 = sh.query_view("question_performance", limit=50_000)

errors = [e for e in (e1, e2, e3) if e]
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
    # `attempt_number` is unreliable in this source (always 1). Reconstruct the real
    # sitting order per (email, test_id) from start_time, so first-attempt /
    # attempts-to-pass / retake metrics reflect ACTUAL retakes (which exist as
    # repeated rows, not as attempt_number 2,3,…).
    base["_start_dt"] = pd.to_datetime(base.get("start_time"), errors="coerce")
    base = base.sort_values("_start_dt", kind="stable")
    base["_seq"] = base.groupby(["email", "test_id"]).cumcount() + 1

# ---------------------------------------------------------------------------
# Data-trust ribbon — be explicit about which dimensions are real vs synthetic
# so consumers calibrate. Specialization is ~half genuine (rest force-mapped);
# cohort/program tags are entirely synthetic until real dispatch tags arrive.
# ---------------------------------------------------------------------------
if not coverage.empty:
    _cov = coverage.iloc[0]

    def _civ(x):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return 0

    _ct, _cr = _civ(_cov.get("total_attempts")), _civ(_cov.get("real_specialization_attempts"))
    _cpct = (_cr / _ct * 100) if _ct else 0
    st.info(
        f"**Data trust** — {_cr:,} of {_ct:,} attempts ({_cpct:.0f}%) map to a *genuine* "
        f"specialization; the remainder are force-mapped. **Cohort / program tags are "
        f"synthetic (preview)** until real dispatch tags arrive — read cohort splits as "
        f"illustrative, not actual.",
        icon="🧭",
    )

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
# KPI scorecard — two rows: Outcomes (row 1) + Effort & Integrity (row 2).
# Surfaces metrics the gold views already compute but the page never showed:
# first-attempt pass, attempts-to-pass, median score, question accuracy.
# ---------------------------------------------------------------------------
def _safe_mean(series) -> float | None:
    s = pd.to_numeric(series, errors="coerce")
    return float(s.mean()) if s.notna().any() else None


n_cand = f["email"].nunique() if not f.empty else 0
n_attempts = len(f)
n_spec = f["specialization"].nunique() if ("specialization" in f.columns and not f.empty) else 0

# First sitting of each (email, test_id) — the real "first attempt" (see _seq).
first_sit = f[f["_seq"] == 1] if ("_seq" in f.columns and not f.empty) else f.iloc[0:0]
first_pass = (_safe_mean(first_sit["is_pass"]) or 0) * 100 if not first_sit.empty else None
overall_pass = (_safe_mean(f["is_pass"]) or 0) * 100 if not f.empty else None
lift = (overall_pass - first_pass) if (first_pass is not None and overall_pass is not None) else None

median_score = float(pd.to_numeric(f["score_pct"], errors="coerce").median()) if not f.empty else None
avg_score = _safe_mean(f["score_pct"]) if not f.empty else None

# Avg attempts-to-pass: for each (email, test_id) eventually passed, the sitting
# number it first passed at; averaged over those test-sittings.
if "_seq" in f.columns and not f.empty and (f["is_pass"] == 1).any():
    _first_pass_seq = f[f["is_pass"] == 1].groupby(["email", "test_id"])["_seq"].min()
    avg_to_pass = float(_first_pass_seq.mean()) if not _first_pass_seq.empty else None
else:
    avg_to_pass = None
avg_dur = _safe_mean(f["duration_min"]) if not f.empty else None

# Question accuracy = share of questions not failed, averaged over attempts (a
# proxy for in-test correctness; honest label — NOT a true completion rate).
_qt = pd.to_numeric(f.get("questions_total"), errors="coerce") if not f.empty else pd.Series(dtype=float)
_qf = pd.to_numeric(f.get("questions_failed"), errors="coerce") if not f.empty else pd.Series(dtype=float)
_qmask = _qt.notna() & (_qt > 0)
q_accuracy = float(((_qt - _qf) / _qt)[_qmask].mean() * 100) if _qmask.any() else None

_vc = pd.to_numeric(f.get("violation_count"), errors="coerce").fillna(0) if not f.empty else pd.Series(dtype=float)
integrity_rate = float((_vc > 0).mean() * 100) if not f.empty else None

st.markdown("<div class='card-title'>Outcomes</div>", unsafe_allow_html=True)
r1 = st.columns(5)
r1[0].metric("Candidates", sh.fmt_int(n_cand))
r1[1].metric("Attempts", sh.fmt_int(n_attempts))
r1[2].metric("First-Attempt Pass", sh.fmt_float(first_pass, 1, "%") if first_pass is not None else "—")
r1[3].metric("Overall Pass", sh.fmt_float(overall_pass, 1, "%") if overall_pass is not None else "—",
             delta=(f"{lift:+.1f} pts vs 1st-attempt" if lift is not None else None))
r1[4].metric("Median Score",
             sh.fmt_float(median_score, 1, "%") if median_score is not None and pd.notna(median_score) else "—",
             delta=(f"avg {avg_score:.1f}%" if avg_score is not None else None), delta_color="off")

st.markdown("<div class='card-title'>Effort &amp; Integrity</div>", unsafe_allow_html=True)
r2 = st.columns(5)
r2[0].metric("Specializations", sh.fmt_int(n_spec))
r2[1].metric("Avg Attempts → Pass", sh.fmt_float(avg_to_pass, 2) if avg_to_pass is not None else "—")
r2[2].metric("Question Accuracy", sh.fmt_float(q_accuracy, 1, "%") if q_accuracy is not None else "—")
r2[3].metric("Avg Duration", sh.fmt_float(avg_dur, 1, " min") if avg_dur is not None else "—")
r2[4].metric("Integrity Rate", sh.fmt_float(integrity_rate, 1, "%") if integrity_rate is not None else "—")

st.caption(
    "First-attempt = first sitting of each test per candidate, reconstructed from timestamps "
    "(the source's attempt counter is unreliable). Integrity Rate = share of attempts with ≥1 "
    "violation. Question Accuracy = share of questions not failed."
)

st.divider()

if f.empty:
    st.info("No attempts for the current selection.")
else:
    tab_out, tab_prog, tab_integ, tab_coh, tab_cmp, tab_cnt, tab_cand = st.tabs(
        ["📊 Outcomes", "📈 Progression", "🛡 Integrity", "🎓 Cohorts", "⇄ Compare", "📝 Content", "👤 Candidates"]
    )

    # ═════════════════════════════ OUTCOMES ═════════════════════════════
    with tab_out:
        # ── Readiness funnel — Candidate → Pass → Advanced ────────────
        st.markdown("<div class='card-title'>Readiness Funnel — Candidates → Pass → Advanced</div>", unsafe_allow_html=True)
        _fs0 = f.sort_values("_seq")
        _ever_pass = int(f.groupby("email")["is_pass"].max().fillna(0).sum())
        _first_pass_cand = f[(f["_seq"] == 1) & (f["is_pass"] == 1)]["email"].nunique()
        _latest_prof = _fs0.groupby("email")["proficiency_level"].last()
        _adv_cand = int((_latest_prof == "Advanced").sum())
        _fn = pd.DataFrame({
            "stage": ["Candidates", "Passed (ever)", "Passed 1st sitting", "Reached Advanced"],
            "n": [n_cand, _ever_pass, _first_pass_cand, _adv_cand],
        })
        fig_fn = go.Figure(go.Funnel(
            y=_fn["stage"], x=_fn["n"], textinfo="value+percent initial",
            marker=dict(color=[sh.DARK_BLUE, sh.NAVY, sh.ORANGE, sh.GREEN]),
            connector=dict(line=dict(color=T["border"])),
        ))
        fig_fn.update_layout(template=TPL, height=260, margin=dict(t=10, b=10, l=0, r=0))
        st.plotly_chart(fig_fn, use_container_width=True)
        st.caption("Candidate-level: of all candidates in the selection, how many ever passed, "
                   "passed on their first sitting, and reached Advanced proficiency.")

        st.divider()

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

        # ── Score distribution by specialization (spread, not just avg) ─
        st.markdown("<div class='card-title'>Score Distribution by Specialization</div>", unsafe_allow_html=True)
        _order = f.groupby("specialization")["score_pct"].median().sort_values(ascending=False).index.tolist()
        fig_box = px.box(f, x="specialization", y="score_pct", template=TPL,
                         category_orders={"specialization": _order},
                         color_discrete_sequence=[sh.NAVY], points="outliers",
                         labels={"specialization": "", "score_pct": "Score %"})
        fig_box.update_layout(height=320, margin=dict(t=10, b=10, l=0, r=0), yaxis=dict(range=[0, 105]))
        st.plotly_chart(fig_box, use_container_width=True)
        st.caption("Box = median & IQR per specialization; whiskers/points show spread & outliers — "
                   "a fairer read than averages alone.")

        # ── Assessment level + Pass-by-sitting (retake dynamics) ───────
        c_diff, c_seq = st.columns(2)
        with c_diff:
            st.markdown("<div class='card-title'>Attempts by Assessment Level + Pass Rate</div>", unsafe_allow_html=True)
            if "test_difficulty" in f.columns and f["test_difficulty"].notna().any():
                _dorder = ["Beginner", "Intermediate", "Advanced"]
                dd = (f.groupby("test_difficulty")
                      .agg(attempts=("is_pass", "size"),
                           pass_rate_pct=("is_pass", lambda s: s.mean() * 100))
                      .reindex(_dorder).dropna(how="all").reset_index())
                fig_d = go.Figure()
                fig_d.add_trace(go.Bar(x=dd["test_difficulty"], y=dd["attempts"], name="Attempts",
                                       marker_color=sh.ORANGE_LIGHT, yaxis="y2"))
                fig_d.add_trace(go.Scatter(x=dd["test_difficulty"], y=dd["pass_rate_pct"], name="Pass Rate %",
                                           mode="lines+markers", line=dict(color=sh.ORANGE, width=3), marker=dict(size=9)))
                fig_d.update_layout(template=TPL, height=300, margin=dict(t=10, b=10, l=0, r=0),
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                    yaxis=dict(title="Pass Rate (%)", range=[0, 105]),
                                    yaxis2=dict(title="Attempts", overlaying="y", side="right", showgrid=False))
                st.plotly_chart(fig_d, use_container_width=True)
            else:
                st.caption("No assessment-level metadata in this selection.")

        with c_seq:
            st.markdown("<div class='card-title'>Pass Rate by Sitting — do retakes help?</div>", unsafe_allow_html=True)
            pbs = (f.groupby("_seq")
                   .agg(attempts=("is_pass", "size"),
                        pass_rate_pct=("is_pass", lambda s: s.mean() * 100))
                   .reset_index())
            pbs = pbs[pbs["attempts"] >= 5]
            if not pbs.empty:
                fig_pb = go.Figure()
                fig_pb.add_trace(go.Bar(x=pbs["_seq"], y=pbs["attempts"], name="Attempts",
                                        marker_color=sh.ORANGE_LIGHT, yaxis="y2"))
                fig_pb.add_trace(go.Scatter(x=pbs["_seq"], y=pbs["pass_rate_pct"], name="Pass Rate %",
                                            mode="lines+markers", line=dict(color=sh.DARK_BLUE, width=3), marker=dict(size=9)))
                fig_pb.update_layout(template=TPL, height=300, margin=dict(t=10, b=10, l=0, r=0),
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                     xaxis=dict(title="Sitting #", dtick=1),
                                     yaxis=dict(title="Pass Rate (%)", range=[0, 105]),
                                     yaxis2=dict(title="Attempts", overlaying="y", side="right", showgrid=False))
                st.plotly_chart(fig_pb, use_container_width=True)
                st.caption("Sitting # reconstructed from timestamps; sittings with <5 attempts hidden.")
            else:
                st.caption("Not enough repeat sittings to chart.")

        # ── Proficiency mix by specialization (full width) ────────────
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

    # ═══════════════════════════ PROGRESSION ════════════════════════════
    with tab_prog:
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
            else:
                st.info("Not enough timestamped attempts for a trend.")
        else:
            st.info("No monthly timestamps available for a trend.")

        st.divider()

        # ── Proficiency migration — first vs latest sitting per candidate ─
        st.markdown("<div class='card-title'>Proficiency Migration — First → Latest sitting</div>", unsafe_allow_html=True)
        _po = ["Beginner", "Intermediate", "Advanced"]
        _pf = f.sort_values("_seq")
        _firstp = _pf.groupby("email")["proficiency_level"].first()
        _lastp = _pf.groupby("email")["proficiency_level"].last()
        _mig = pd.crosstab(_firstp, _lastp).reindex(index=_po, columns=_po).fillna(0).astype(int)
        fig_mig = px.imshow(_mig.values, x=_po, y=_po, text_auto=True, template=TPL,
                            color_continuous_scale="Oranges",
                            labels=dict(x="Latest proficiency", y="First proficiency", color="Candidates"))
        fig_mig.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0), coloraxis_showscale=False)
        st.plotly_chart(fig_mig, use_container_width=True)
        st.caption("Candidate counts moving from their first sitting's proficiency (rows) to their latest "
                   "(columns). On the diagonal = unchanged; above it = improved tier.")

        # ── Retake score-change + interval (candidates who re-sat) ─────
        _rt = f.sort_values(["email", "test_id", "_seq"])
        _grp_size = _rt.groupby(["email", "test_id"])["_seq"].transform("size")
        _retaken = _rt[_grp_size > 1]
        c_imp, c_int = st.columns(2)
        with c_imp:
            st.markdown("<div class='card-title'>Retake Score Change (re-sat tests)</div>", unsafe_allow_html=True)
            if not _retaken.empty:
                _g = _retaken.groupby(["email", "test_id"])["score_pct"]
                _delta = (_g.last() - _g.first()).dropna().reset_index(name="delta")
                _delta["direction"] = pd.cut(_delta["delta"], bins=[-1e9, -0.001, 0.001, 1e9],
                                             labels=["Declined", "Same", "Improved"])
                fig_imp = px.histogram(_delta, x="delta", color="direction", nbins=30, template=TPL,
                                       color_discrete_map={"Improved": sh.GREEN, "Same": sh.SLATE, "Declined": sh.RED},
                                       labels={"delta": "Score change (last − first sitting), pts", "direction": ""})
                fig_imp.add_vline(x=0, line_dash="dot", line_color=T["border"])
                fig_imp.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0), bargap=0.05,
                                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig_imp, use_container_width=True)
                st.caption(f"Score change when a test is re-sat (median {_delta['delta'].median():+.1f} pts). "
                           "Left of 0 = scored worse on the retake.")
            else:
                st.caption("No re-sat tests in this selection.")
        with c_int:
            st.markdown("<div class='card-title'>Retake Interval (days between sittings)</div>", unsafe_allow_html=True)
            if not _retaken.empty:
                _rt2 = _retaken.copy()
                _rt2["_gap"] = _rt2.groupby(["email", "test_id"])["_start_dt"].diff().dt.total_seconds() / 86400
                _gaps = _rt2["_gap"].dropna()
                _gaps = _gaps[(_gaps >= 0) & (_gaps <= 120)]
                if not _gaps.empty:
                    fig_gap = px.histogram(_gaps.to_frame("gap"), x="gap", nbins=30, template=TPL,
                                           color_discrete_sequence=[sh.NAVY],
                                           labels={"gap": "Days between sittings"})
                    fig_gap.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0), bargap=0.05, showlegend=False)
                    st.plotly_chart(fig_gap, use_container_width=True)
                    st.caption(f"Reconstructed from timestamps (the gold retake view is empty). "
                               f"Median gap {_gaps.median():.0f} days; 0–120-day window shown.")
                else:
                    st.caption("No valid retake intervals (0–120 days) in this selection.")
            else:
                st.caption("No re-sat tests in this selection.")

    # ════════════════════════════ INTEGRITY ═════════════════════════════
    with tab_integ:
        st.markdown("<div class='card-title'>Violation Rate by Specialization</div>", unsafe_allow_html=True)
        iv = f.copy()
        iv["_vc"] = pd.to_numeric(iv.get("violation_count"), errors="coerce").fillna(0)
        ig = iv.groupby("specialization").agg(
            attempts=("email", "size"),
            violation_rate_pct=("_vc", lambda s: (s > 0).mean() * 100),
            total_violations=("_vc", "sum"),
        ).reset_index().sort_values("violation_rate_pct", ascending=False)
        fig_iv = px.bar(ig, x="specialization", y="violation_rate_pct", template=TPL,
                        color="violation_rate_pct",
                        color_continuous_scale=[[0, sh.GREEN], [0.5, sh.AMBER], [1, sh.RED]],
                        range_color=[0, 100],
                        labels={"specialization": "", "violation_rate_pct": "% attempts with a violation"})
        fig_iv.update_layout(height=320, margin=dict(t=10, b=10, l=0, r=0), coloraxis_showscale=False)
        st.plotly_chart(fig_iv, use_container_width=True)
        st.caption("Share of attempts with at least one test-window violation, by specialization.")

        st.divider()

        # ── Integrity vs performance (per candidate) ──────────────────
        st.markdown("<div class='card-title'>Integrity vs Performance — do violators score differently?</div>", unsafe_allow_html=True)
        _ci = f.groupby("email").agg(
            name=("candidatename", "first"),
            attempts=("is_pass", "size"),
            avg_score=("score_pct", "mean"),
            total_viol=("violation_count", "sum"),
            viol_dur=("violation_duration_sec", "sum"),
        ).reset_index()
        _ci["viol_per_attempt"] = _ci["total_viol"] / _ci["attempts"].replace(0, pd.NA)
        fig_sc = px.scatter(_ci, x="viol_per_attempt", y="avg_score", size="attempts",
                            template=TPL, hover_name="name",
                            color="avg_score", color_continuous_scale=[[0, sh.RED], [0.5, sh.AMBER], [1, sh.GREEN]],
                            range_color=[0, 100],
                            labels={"viol_per_attempt": "Avg violations per attempt", "avg_score": "Avg score %"})
        fig_sc.update_layout(height=340, margin=dict(t=10, b=10, l=0, r=0), coloraxis_showscale=False,
                             yaxis=dict(range=[0, 105]))
        st.plotly_chart(fig_sc, use_container_width=True)
        st.caption("Each dot = a candidate (size = attempts). Look for whether high-violation candidates "
                   "cluster at lower (or higher) scores.")

        st.divider()

        # ── High integrity-risk watchlist ─────────────────────────────
        st.markdown("<div class='card-title'>High Integrity-Risk Watchlist (top 20)</div>", unsafe_allow_html=True)
        _wl = _ci.copy()
        _wl["integrity_risk"] = _wl["total_viol"] * 2 + _wl["viol_dur"] / 60
        _wl = _wl[_wl["integrity_risk"] > 0].sort_values("integrity_risk", ascending=False).head(20)
        if not _wl.empty:
            _wl_disp = _wl.assign(viol_min=(_wl["viol_dur"] / 60)).rename(columns={
                "name": "Candidate", "email": "Email", "attempts": "Attempts",
                "total_viol": "Violations", "viol_min": "Viol. mins",
                "integrity_risk": "Risk Score", "avg_score": "Avg Score (%)",
            })[["Candidate", "Email", "Attempts", "Violations", "Viol. mins", "Risk Score", "Avg Score (%)"]]
            st.dataframe(
                _wl_disp, use_container_width=True, hide_index=True,
                column_config={
                    "Risk Score": st.column_config.ProgressColumn(
                        "Risk Score", format="%.0f", min_value=0,
                        max_value=float(_wl["integrity_risk"].max())),
                    "Avg Score (%)": st.column_config.NumberColumn("Avg Score", format="%.1f%%"),
                    "Viol. mins": st.column_config.NumberColumn("Viol. mins", format="%.1f"),
                },
            )
            st.caption("Risk score = 2×violations + violation-minutes. A review queue, not a verdict.")
        else:
            st.caption("No candidates with violations in this selection.")

    # ═══════════════════════════ COHORTS (preview) ══════════════════════
    with tab_coh:
        st.caption("⚠️ Cohort / program tags are **synthetic** on the current data — this is a structural "
                   "preview that will populate correctly once real dispatch tags arrive.")
        st.markdown("<div class='card-title'>Cohort Scorecard</div>", unsafe_allow_html=True)
        gb = f.groupby("cohort")
        sc = pd.DataFrame({
            "Candidates": gb["email"].nunique(),
            "Attempts": gb.size(),
            "Overall Pass %": gb["is_pass"].mean() * 100,
            "Avg Score %": gb["score_pct"].mean(),
            "Median %": gb["score_pct"].median(),
            "% Advanced": gb["proficiency_level"].apply(lambda s: (s == "Advanced").mean() * 100),
            "Integrity %": gb["violation_count"].apply(
                lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) > 0).mean() * 100),
        })
        _fs1 = f[f["_seq"] == 1].groupby("cohort")["is_pass"].mean() * 100
        sc.insert(2, "1st-Sit Pass %", _fs1)
        sc = sc.reset_index().rename(columns={"cohort": "Cohort"}).sort_values("Attempts", ascending=False)
        st.dataframe(
            sc, use_container_width=True, hide_index=True,
            column_config={
                "Overall Pass %": st.column_config.ProgressColumn("Overall Pass %", format="%.0f%%", min_value=0, max_value=100),
                "1st-Sit Pass %": st.column_config.NumberColumn(format="%.0f%%"),
                "Avg Score %": st.column_config.NumberColumn(format="%.1f%%"),
                "Median %": st.column_config.NumberColumn(format="%.1f%%"),
                "% Advanced": st.column_config.NumberColumn(format="%.0f%%"),
                "Integrity %": st.column_config.NumberColumn(format="%.0f%%"),
            },
        )

        st.markdown("<div class='card-title'>Cohort Avg Score</div>", unsafe_allow_html=True)
        fc2 = f[f.get("cohort") != "Unassigned"] if "cohort" in f.columns else f.iloc[0:0]
        if not fc2.empty:
            cpv = fc2.groupby("cohort").agg(avg_score_pct=("score_pct", "mean")).reset_index()
            fig_c = px.bar(cpv, x="cohort", y="avg_score_pct", template=TPL,
                           color="avg_score_pct", color_continuous_scale=[[0, sh.RED], [0.5, sh.AMBER], [1, sh.GREEN]],
                           range_color=[0, 100], labels={"cohort": "", "avg_score_pct": "Avg Score %"})
            fig_c.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0), coloraxis_showscale=False,
                                yaxis=dict(range=[0, 105]))
            st.plotly_chart(fig_c, use_container_width=True)
        else:
            st.caption("No program-tagged cohorts in this selection.")

    # ════════════════════════════ COMPARE ═══════════════════════════════
    with tab_cmp:
        st.caption("Compare any two groups side by side. Specialization & Year are real; "
                   "Cohort/program comparisons are preview (synthetic tags).")
        _dim_map = {"Cohort": "cohort", "Specialization": "specialization", "Year": "_year"}
        _dim = st.selectbox("Compare by", list(_dim_map.keys()), index=0, key="cmp_dim")
        _col = _dim_map[_dim]
        _opts = sorted([x for x in f.get(_col, pd.Series(dtype=str)).dropna().unique().tolist() if x])
        if len(_opts) < 2:
            st.info("Need at least two groups in the current selection to compare.")
        else:
            _cc = st.columns(2)
            _a = _cc[0].selectbox("Group A", _opts, index=0, key=f"cmp_a_{_col}")
            _b = _cc[1].selectbox("Group B", _opts, index=1, key=f"cmp_b_{_col}")
            if _a == _b:
                st.info("Pick two different groups to compare.")
            else:
                def _grp_kpis(val):
                    sub = f[f[_col] == val]
                    fs1 = sub[sub["_seq"] == 1]
                    vc = pd.to_numeric(sub.get("violation_count"), errors="coerce").fillna(0)
                    return {
                        "Attempts": float(len(sub)),
                        "Candidates": float(sub["email"].nunique()),
                        "1st-Sit Pass %": (fs1["is_pass"].mean() * 100) if len(fs1) else float("nan"),
                        "Overall Pass %": (sub["is_pass"].mean() * 100) if len(sub) else float("nan"),
                        "Avg Score %": sub["score_pct"].mean() if len(sub) else float("nan"),
                        "Integrity %": ((vc > 0).mean() * 100) if len(sub) else float("nan"),
                    }

                _ka, _kb = _grp_kpis(_a), _grp_kpis(_b)
                _mlt = pd.DataFrame([{"group": _a, **_ka}, {"group": _b, **_kb}]).melt(
                    id_vars="group", value_vars=["1st-Sit Pass %", "Overall Pass %", "Avg Score %"],
                    var_name="metric", value_name="val")
                fig_cmp = px.bar(_mlt, x="metric", y="val", color="group", barmode="group", template=TPL,
                                 color_discrete_sequence=[sh.ORANGE, sh.DARK_BLUE],
                                 labels={"metric": "", "val": "%", "group": ""})
                fig_cmp.update_layout(height=320, margin=dict(t=10, b=10, l=0, r=0),
                                      legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                      yaxis=dict(range=[0, 105]))
                st.plotly_chart(fig_cmp, use_container_width=True)

                _dtab = pd.DataFrame({"Metric": list(_ka.keys()),
                                      _a: list(_ka.values()), _b: list(_kb.values())})
                _dtab["Δ (A − B)"] = _dtab[_a] - _dtab[_b]
                st.dataframe(_dtab, use_container_width=True, hide_index=True,
                             column_config={
                                 _a: st.column_config.NumberColumn(format="%.1f"),
                                 _b: st.column_config.NumberColumn(format="%.1f"),
                                 "Δ (A − B)": st.column_config.NumberColumn(format="%+.1f"),
                             })

    # ════════════════════════════ CONTENT ═══════════════════════════════
    with tab_cnt:
        st.caption("Catalogue-wide question efficacy across **all recorded attempts** "
                   "(not affected by the slicers above) — from the per-question result JSON.")
        if qperf is None or qperf.empty:
            st.info("No question-level data available.")
        else:
            qp = qperf.copy()
            for _c in ["times_served", "times_answered", "times_correct", "answer_rate_pct",
                       "correct_rate_pct", "avg_idle_sec", "avg_score_ratio_pct"]:
                if _c in qp.columns:
                    qp[_c] = pd.to_numeric(qp[_c], errors="coerce")
            qp["question"] = qp.get("question_text", pd.Series(dtype=str)).fillna("").map(_strip_html_tc)
            _blank = qp["question"].str.len() == 0
            qp.loc[_blank, "question"] = qp.loc[_blank, "question_title"].fillna("").map(_strip_html_tc)
            qp.loc[qp["question"].str.len() == 0, "question"] = "(no text)"

            _min = st.slider("Minimum times served", 1, 100, 20, key="tc_minserved",
                             help="Hide rarely-served questions so a single bad attempt doesn't dominate.")
            qpf = qp[qp["times_served"] >= _min]
            st.caption(f"{len(qpf):,} of {len(qp):,} questions meet the ≥{_min}-served threshold.")

            def _q_section(by, asc, title, cap):
                st.markdown(f"<div class='card-title'>{title}</div>", unsafe_allow_html=True)
                cols = ["question", "question_type", "question_difficulty", "specialization",
                        "times_served", "answer_rate_pct", "correct_rate_pct", "avg_idle_sec"]
                show = qpf.sort_values(by, ascending=asc).head(15)[cols].rename(columns={
                    "question": "Question", "question_type": "Type", "question_difficulty": "Difficulty",
                    "specialization": "Specialization", "times_served": "Served",
                    "answer_rate_pct": "Answer %", "correct_rate_pct": "Correct %", "avg_idle_sec": "Avg Idle (s)",
                })
                st.dataframe(show, use_container_width=True, hide_index=True, column_config={
                    "Question": st.column_config.TextColumn("Question", width="large",
                                                            help="Full question text — hover to read."),
                    "Answer %": st.column_config.NumberColumn(format="%.0f%%"),
                    "Correct %": st.column_config.NumberColumn(format="%.0f%%"),
                    "Avg Idle (s)": st.column_config.NumberColumn(format="%.1f"),
                })
                st.caption(cap)

            if qpf.empty:
                st.info("No questions meet the threshold — lower it.")
            else:
                _q_section("correct_rate_pct", True, "Hardest Questions (lowest correct rate)",
                           "Lowest share of sittings scoring any points. 0% over many sittings often flags a broken or mis-keyed item.")
                _q_section("answer_rate_pct", True, "Most-Skipped Questions (lowest answer rate)",
                           "Most often left unanswered — candidates run out of time or skip them.")
                _q_section("avg_idle_sec", False, "Idle-Time Hotspots (longest think time)",
                           "Highest average idle time before answering — the questions that make candidates pause.")

    # ════════════════════════════ CANDIDATES ════════════════════════════
    with tab_cand:
        st.caption(f"One row per candidate in the current selection (**{group_label}**) — "
                   f"**click a candidate** to open their profile.")
        fs = f.sort_values(["email", "_seq"])
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
