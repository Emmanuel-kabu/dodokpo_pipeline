"""Streamlit executive BI dashboard for the Dodokpo gold assessment layer.

Branding: orange primary (#F97316) + dark blue (#0F172A).
Slicers: Year / Quarter / Month / Difficulty.
"""

from __future__ import annotations

import concurrent.futures
import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_access import AthenaViewReader

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Dodokpo Executive Intelligence",
    page_icon="🟧",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Brand palette
# ---------------------------------------------------------------------------
ORANGE       = "#F97316"   # primary
ORANGE_DARK  = "#C2410C"
ORANGE_LIGHT = "#FED7AA"
DARK_BLUE    = "#0F172A"   # secondary
NAVY         = "#1E3A8A"
SLATE        = "#334155"
GRAY_BG      = "#F8FAFC"
GREEN        = "#10B981"
AMBER        = "#F59E0B"
RED          = "#EF4444"

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
.main {{ background-color: {GRAY_BG}; }}

/* Sidebar (dark blue) */
section[data-testid="stSidebar"] {{ background-color: {DARK_BLUE} !important; }}
section[data-testid="stSidebar"] * {{ color: #E2E8F0 !important; }}
section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {{
    color: {ORANGE} !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    font-size: 13px !important;
    font-weight: 700 !important;
}}
section[data-testid="stSidebar"] label {{
    color: #94A3B8 !important;
    font-size: 11px !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    font-weight: 600 !important;
}}

/* KPI cards */
[data-testid="stMetricValue"] {{
    font-size: 26px !important;
    color: {DARK_BLUE} !important;
    font-weight: 800 !important;
}}
[data-testid="stMetricLabel"] {{
    font-size: 11px !important;
    color: {SLATE} !important;
    text-transform: uppercase !important;
    letter-spacing: 0.7px !important;
    font-weight: 700 !important;
}}
[data-testid="stMetricDelta"] {{ font-size: 12px !important; }}

/* Card container around metric blocks */
div[data-testid="stMetric"] {{
    background: #FFFFFF;
    border-left: 4px solid {ORANGE};
    border-radius: 6px;
    padding: 14px 18px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.06);
}}

/* Page headings */
.page-header {{
    font-size: 28px;
    font-weight: 800;
    color: {DARK_BLUE};
    letter-spacing: -0.5px;
    margin-bottom: 2px;
}}
.page-sub {{
    font-size: 13px;
    color: {SLATE};
    margin-bottom: 20px;
}}

/* Tabs */
.stTabs [data-baseweb="tab-list"] button[data-baseweb="tab"] {{
    color: {SLATE};
    font-weight: 600;
}}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
    color: {ORANGE} !important;
    border-bottom: 3px solid {ORANGE} !important;
}}

/* Card */
.card {{
    background: #FFFFFF;
    border-radius: 8px;
    padding: 18px 22px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.06);
    margin-bottom: 14px;
}}
.card-title {{
    font-size: 12px;
    font-weight: 700;
    color: {SLATE};
    text-transform: uppercase;
    letter-spacing: 0.7px;
    margin-bottom: 12px;
    border-left: 3px solid {ORANGE};
    padding-left: 8px;
}}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data loading (Athena via parallel futures)
# ---------------------------------------------------------------------------

ATHENA_DATABASE = "dodokpo_dev_gold"
ATHENA_WORKGROUP = "dodokpo-dev-workgroup"
ATHENA_RESULTS_BUCKET = "dodokpo-dev-athena-results"
ATHENA_REGION = "eu-west-1"


@st.cache_data(show_spinner=False, ttl=300)
def _query_athena_view(
    view_name: str,
    limit: int | None = 50_000,
    order_by: str | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """Returns (DataFrame, error_message). error_message is None on success."""
    try:
        reader = AthenaViewReader(
            database=ATHENA_DATABASE,
            workgroup=ATHENA_WORKGROUP,
            results_bucket=ATHENA_RESULTS_BUCKET,
            region=ATHENA_REGION,
        )
        return reader.query_view(view_name, limit=limit, order_by=order_by), None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


@st.cache_data(show_spinner=False, ttl=300)
def _query_attempt_questions(
    taker_id: str, test_id: str, attempt_number: str
) -> tuple[pd.DataFrame, str | None]:
    """Per-question detail for one test attempt — parses testresult.result JSON
    and joins with the question table for type/difficulty/title."""
    # attemptnumber is a bigint in silver — interpolate as a number, not a string
    try:
        attempt_num_int = int(float(str(attempt_number).strip() or "1"))
    except (TypeError, ValueError):
        attempt_num_int = 1
    sql = f"""
    WITH attempt AS (
        SELECT result, testwindowviolationcount, testwindowviolationduration,
               numberofquestions, numberofquestionsanswered,
               numberofquestionspassed, numberofquestionsfailed,
               passmark, testpercentage, totalscore, totalpassedscore,
               passstatus, duration, starttime, finishtime
        FROM dodokpo_dev_silver.test_execution_testresult
        WHERE assessmenttakerid = '{taker_id}'
          AND testid             = '{test_id}'
          AND attemptnumber      = {attempt_num_int}
          AND result IS NOT NULL AND result <> '' AND result LIKE '[{{%'
        LIMIT 1
    ),
    question_dedup AS (
        SELECT id, questiontype, difficultylevel, questiontitle
        FROM (
            SELECT id, questiontype, difficultylevel, questiontitle, load_date,
                   ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
            FROM dodokpo_dev_silver.test_creation_question
        )
        WHERE _rn = 1
    ),
    parsed AS (
        SELECT
            json_extract_scalar(q, '$.questionId')                       AS question_id,
            TRY(CAST(json_extract_scalar(q, '$.score')           AS DOUBLE)) AS max_score,
            TRY(CAST(json_extract_scalar(q, '$.scored')          AS DOUBLE)) AS achieved_score,
            TRY(CAST(json_extract_scalar(q, '$.idleTime')        AS DOUBLE)) AS idle_time_sec,
            TRY(CAST(json_extract_scalar(q, '$.isAnswered')      AS BOOLEAN)) AS is_answered,
            TRY(CAST(json_extract_scalar(q, '$.isAnswerCorrect') AS BOOLEAN)) AS is_correct,
            a.testwindowviolationcount   AS violation_count,
            a.testwindowviolationduration AS violation_duration_sec,
            a.numberofquestions, a.numberofquestionsanswered,
            a.numberofquestionspassed,   a.numberofquestionsfailed,
            a.passmark, a.testpercentage, a.totalscore, a.totalpassedscore,
            a.passstatus, a.duration AS attempt_duration_sec,
            a.starttime, a.finishtime
        FROM attempt a
        CROSS JOIN UNNEST(CAST(json_parse(a.result) AS ARRAY(JSON))) AS t(q)
    )
    SELECT
        p.question_id, p.max_score, p.achieved_score, p.idle_time_sec,
        p.is_answered, p.is_correct,
        p.violation_count, p.violation_duration_sec,
        p.numberofquestions       AS attempt_questions_total,
        p.numberofquestionsanswered AS attempt_questions_answered,
        p.numberofquestionspassed   AS attempt_questions_passed,
        p.numberofquestionsfailed   AS attempt_questions_failed,
        p.passmark, p.testpercentage, p.totalscore, p.totalpassedscore,
        p.passstatus, p.attempt_duration_sec,
        p.starttime, p.finishtime,
        qd.questiontitle, qd.questiontype,
        qd.difficultylevel AS question_difficulty
    FROM parsed p
    LEFT JOIN question_dedup qd ON p.question_id = qd.id
    """
    try:
        reader = AthenaViewReader(
            database=ATHENA_DATABASE,
            workgroup=ATHENA_WORKGROUP,
            results_bucket=ATHENA_RESULTS_BUCKET,
            region=ATHENA_REGION,
        )
        return reader.run_sql(sql, output_subdir="attempt_questions"), None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


def load_all_data() -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Run all Athena queries concurrently. Returns (data dict, error list)."""
    view_specs = [
        ("trainer_candidate_performance", 50_000, "start_time DESC"),
        ("monthly_assessment_trend",      None,   None),
        ("candidate_retake_intervals",    50_000, "start_time DESC"),
        ("trainer_quality_violations",    50_000, "load_date DESC"),
        ("executive_overview_kpis",       None,   None),
        ("organization_catalog_kpis",     None,   None),
        ("gold_data_freshness",           None,   None),
    ]

    results: dict[str, pd.DataFrame] = {}
    errors: list[str] = []

    def _fetch(spec):
        view, lim, order = spec
        df, err = _query_athena_view(view, limit=lim, order_by=order)
        return view, df, err

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_fetch, spec) for spec in view_specs]
        for fut in concurrent.futures.as_completed(futures):
            view, df, err = fut.result()
            results[view] = df
            if err:
                errors.append(f"**{view}**: {err}")

    return {
        "candidate_perf": results.get("trainer_candidate_performance", pd.DataFrame()),
        "monthly_trend":  results.get("monthly_assessment_trend",      pd.DataFrame()),
        "retake":         results.get("candidate_retake_intervals",    pd.DataFrame()),
        "violations":     results.get("trainer_quality_violations",    pd.DataFrame()),
        "kpis":           results.get("executive_overview_kpis",       pd.DataFrame()),
        "catalog_org":    results.get("organization_catalog_kpis",     pd.DataFrame()),
        "freshness":      results.get("gold_data_freshness",           pd.DataFrame()),
    }, errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_filters(
    df: pd.DataFrame,
    years: list[str],
    quarters: list[str],
    months: list[str],
    difficulties: list[str],
    organizations: list[str] | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    if years and "attempt_year" in out.columns:
        out = out[out["attempt_year"].isin(years)]
    if quarters and "attempt_quarter" in out.columns:
        out = out[out["attempt_quarter"].isin(quarters)]
    if months and "attempt_month" in out.columns:
        out = out[out["attempt_month"].isin(months)]
    if difficulties and "test_difficulty" in out.columns:
        out = out[out["test_difficulty"].isin(difficulties)]
    if organizations and "organization_name" in out.columns:
        out = out[out["organization_name"].isin(organizations)]
    return out


def _kpi_card(label: str, value: str, *, icon: str = "") -> None:
    st.metric(f"{icon} {label}" if icon else label, value)


def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_float(n, decimals: int = 1, suffix: str = "") -> str:
    try:
        return f"{float(n):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _build_candidate_summary(cp: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the candidate-performance frame to one row per *person*.

    A single candidate (e.g. Philip Odzor) can have many `assessment_taker_id`
    values because each test session creates a new taker row in the source.
    Email is the stable per-person identifier, so we group by email.

    The roster automatically respects the slicer filters: if the user picks a
    month, the per-candidate aggregates only count attempts in that month.
    """
    if cp.empty or "email" not in cp.columns:
        return pd.DataFrame()

    grouped = (
        cp.groupby("email", dropna=False)
        .agg(
            candidate_name=("candidatename", "first"),
            total_attempts=("test_id", "count"),
            tests_taken=("test_id", "nunique"),
            avg_score=("score_pct", "mean"),
            total_pass=("is_pass", "sum"),
            total_fail=("is_pass", lambda s: (s == 0).sum()),
            avg_duration=("duration_min", "mean"),
            total_violations=("violation_count", "sum"),
            last_attempt=("start_time", "max"),
        )
        .reset_index()
    )
    grouped["pass_rate"] = grouped["total_pass"] / grouped["total_attempts"].replace(0, pd.NA) * 100
    grouped = grouped.rename(columns={
        "email":             "Email",
        "candidate_name":    "Candidate",
        "total_attempts":    "Total Attempts",
        "tests_taken":       "Tests Taken",
        "avg_score":         "Avg Score (%)",
        "pass_rate":         "Pass Rate (%)",
        "total_pass":        "Pass",
        "total_fail":        "Fail",
        "avg_duration":      "Avg Duration (min)",
        "total_violations":  "Violations",
        "last_attempt":      "Last Attempt",
    })
    return grouped[[
        "Email", "Candidate",
        "Total Attempts", "Tests Taken",
        "Pass", "Fail", "Pass Rate (%)", "Avg Score (%)",
        "Avg Duration (min)", "Violations", "Last Attempt",
    ]].sort_values("Total Attempts", ascending=False).head(2_000)


# ---------------------------------------------------------------------------
# Drill-down modal — candidate detail with embedded visualizations
# ---------------------------------------------------------------------------

@st.dialog("Candidate Performance Detail", width="large")
def show_candidate_drilldown(cp: pd.DataFrame, email: str, retake_df: pd.DataFrame) -> None:
    """Email-keyed drill-down with time-based progression analysis.

    Shows lifetime KPIs plus year-over-year and quarter-over-quarter trends so
    trainers can see if a candidate is improving or regressing over time.
    Always uses the full candidate history (ignores the page-level slicers).
    """
    history = cp[cp["email"] == email].copy()
    if history.empty:
        st.warning("No history found for this candidate.")
        if st.button("Close"):
            st.rerun()
        return

    name = history["candidatename"].iloc[0] if "candidatename" in history.columns else "—"

    st.markdown(f"### {name}")
    st.caption(email)

    # ── Lifetime KPIs ─────────────────────────────────────────────
    total_attempts   = len(history)
    tests_taken      = history["test_id"].nunique() if "test_id" in history.columns else 0
    pass_rate        = (history["pass_status"] == "passed").mean() * 100 if "pass_status" in history.columns else 0
    avg_score        = history["score_pct"].mean() if "score_pct" in history.columns else 0
    avg_duration     = history["duration_min"].mean() if "duration_min" in history.columns else 0
    total_violations = history["violation_count"].sum() if "violation_count" in history.columns else 0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Attempts", _fmt_int(total_attempts))
    k2.metric("Tests Taken",    _fmt_int(tests_taken))
    k3.metric("Pass Rate",      _fmt_float(pass_rate, 1, "%"))
    k4.metric("Avg Score",      _fmt_float(avg_score, 1, "%"))
    k5.metric("Avg Duration",   _fmt_float(avg_duration, 1, " min"))
    k6.metric("Violations",     _fmt_int(total_violations))

    st.divider()

    # ── Time-based progression (Yearly | Monthly side by side) ───
    def _period_combo_fig(df: pd.DataFrame, period_col: str, period_label: str) -> go.Figure:
        agg = (
            df.groupby(period_col)
            .agg(
                attempts=("test_id", "count"),
                avg_score=("score_pct", "mean"),
                pass_rate=("is_pass", lambda s: s.mean() * 100),
            )
            .reset_index()
            .sort_values(period_col)
        )
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=agg[period_col], y=agg["attempts"],
            name="Attempts", marker_color=ORANGE_LIGHT, yaxis="y2",
            hovertemplate=f"{period_label} %{{x}}<br>%{{y}} attempts<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=agg[period_col], y=agg["pass_rate"],
            name="Pass Rate %", mode="lines+markers",
            line=dict(color=ORANGE, width=3), marker=dict(size=9),
        ))
        fig.add_trace(go.Scatter(
            x=agg[period_col], y=agg["avg_score"],
            name="Avg Score %", mode="lines+markers",
            line=dict(color=DARK_BLUE, width=2.5, dash="dot"), marker=dict(size=8),
        ))
        fig.update_layout(
            template="plotly_white", height=290,
            margin=dict(t=10, b=0, l=0, r=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            yaxis=dict(title="Score / Pass Rate (%)", range=[0, 105]),
            yaxis2=dict(title="Attempts", overlaying="y", side="right", showgrid=False),
            xaxis=dict(type="category", title=period_label),
        )
        return fig

    col_yr, sep, col_mo = st.columns([1, 0.04, 1])

    with col_yr:
        st.markdown(
            f"<div style='color:{DARK_BLUE};font-weight:700;font-size:13px;"
            f"text-transform:uppercase;letter-spacing:0.6px;"
            f"border-left:3px solid {ORANGE};padding-left:8px;margin-bottom:6px'>"
            "Yearly Progression</div>",
            unsafe_allow_html=True,
        )
        if "attempt_year" in history.columns and history["attempt_year"].dropna().nunique() > 0:
            st.plotly_chart(_period_combo_fig(history, "attempt_year", "Year"),
                            use_container_width=True)
        else:
            st.info("Not enough data for a yearly view.")

    with sep:
        st.markdown(
            f"<div style='border-left:3px solid {DARK_BLUE};height:330px;"
            "margin-top:6px;opacity:0.9'></div>",
            unsafe_allow_html=True,
        )

    with col_mo:
        st.markdown(
            f"<div style='color:{DARK_BLUE};font-weight:700;font-size:13px;"
            f"text-transform:uppercase;letter-spacing:0.6px;"
            f"border-left:3px solid {ORANGE};padding-left:8px;margin-bottom:6px'>"
            "Monthly Progression</div>",
            unsafe_allow_html=True,
        )
        if "attempt_month" in history.columns and history["attempt_month"].dropna().nunique() > 0:
            st.plotly_chart(_period_combo_fig(history, "attempt_month", "Month"),
                            use_container_width=True)
        else:
            st.info("Not enough data for a monthly view.")

    st.divider()

    # ── Detail table — click a row to drill into that attempt ─────
    st.markdown("**All Attempts** — _click any row to view per-question detail_")
    display_cols = [
        "test_title", "start_time", "attempt_year",
        "score_pct", "pass_status", "duration_min",
        "violation_count", "test_difficulty",
    ]
    available = [c for c in display_cols if c in history.columns]
    attempts_table = history[available + ["assessment_taker_id", "test_id", "attempt_number"]].copy()
    attempts_table = attempts_table.sort_values("start_time", ascending=False).reset_index(drop=True)

    display_df = attempts_table[available].rename(columns={
        "test_title":      "Test",
        "start_time":      "Started",
        "attempt_year":    "Year",
        "score_pct":       "Score (%)",
        "pass_status":     "Outcome",
        "duration_min":    "Duration (min)",
        "violation_count": "Violations",
        "test_difficulty": "Difficulty",
    })
    attempt_event = st.dataframe(
        display_df, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "Score (%)":      st.column_config.NumberColumn("Score", format="%.1f%%"),
            "Duration (min)": st.column_config.NumberColumn("Duration", format="%.1f min"),
            "Started":        st.column_config.DatetimeColumn("Started", format="YYYY-MM-DD HH:mm"),
        },
    )
    if attempt_event and attempt_event.get("selection", {}).get("rows"):
        idx = attempt_event["selection"]["rows"][0]
        sel = attempts_table.iloc[idx]
        _render_attempt_detail(
            taker_id=sel["assessment_taker_id"],
            test_id=sel["test_id"],
            attempt_number=str(sel["attempt_number"]),
            test_title=sel.get("test_title", "Test"),
            start_time=sel.get("start_time", ""),
            candidate_name=name,
        )

    if st.button("Close", type="primary"):
        st.rerun()


def _render_attempt_detail(
    taker_id: str,
    test_id: str,
    attempt_number: str,
    test_title: str,
    start_time,
    candidate_name: str,
) -> None:
    """Per-attempt question-level drill-down rendered inline below the table."""
    st.divider()
    st.markdown(
        f"<div style='color:{DARK_BLUE};font-weight:800;font-size:16px;"
        f"border-left:4px solid {ORANGE};padding-left:10px;margin:8px 0'>"
        f"Attempt Detail — {test_title}"
        f"<span style='font-weight:500;color:{SLATE};font-size:12px;margin-left:12px'>"
        f"{candidate_name} · started {start_time}</span></div>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading per-question detail…"):
        questions, err = _query_attempt_questions(taker_id, test_id, attempt_number)
    if err:
        st.error(f"Failed to load question detail: {err}")
        return
    if questions.empty:
        st.info("No per-question data is available for this attempt.")
        return

    # Athena returns booleans as 'true'/'false' strings — coerce to real bools
    for bool_col in ("is_answered", "is_correct"):
        if bool_col in questions.columns:
            questions[bool_col] = (
                questions[bool_col].astype(str).str.lower()
                .map({"true": True, "false": False}).fillna(False)
            )
    # Numeric columns may still be strings if any value is blank — coerce
    for num_col in ("max_score", "achieved_score", "idle_time_sec",
                    "attempt_questions_total", "attempt_questions_answered",
                    "attempt_questions_passed", "attempt_questions_failed",
                    "violation_count", "violation_duration_sec",
                    "passmark", "testpercentage", "totalscore", "totalpassedscore",
                    "attempt_duration_sec"):
        if num_col in questions.columns:
            questions[num_col] = pd.to_numeric(questions[num_col], errors="coerce")

    # ── KPI cards ────────────────────────────────────────────────
    # Pinned to the testresult aggregate columns (the system's own arithmetic)
    # so the cards never disagree with the source's official counts.
    # Per-row outcome uses `achieved_score > 0` because points earned is what
    # ultimately drives the score; isAnswerCorrect is kept as a separate flag
    # so any divergence with `scored` is visible (not silently hidden).
    def _n(value, default=0):
        try:
            f = float(value)
            return default if pd.isna(f) else f
        except (TypeError, ValueError):
            return default

    first = questions.iloc[0]
    earned_per_q = questions["achieved_score"].fillna(0)

    total_q     = int(_n(first.get("attempt_questions_total"),    len(questions)))
    answered_q  = int(_n(first.get("attempt_questions_answered"), int(questions["is_answered"].sum())))
    # Source-of-truth correct/wrong counts come from the aggregates;
    # fall back to a per-row derivation only when those aggregates are blank.
    correct_q   = int(_n(first.get("attempt_questions_passed"),   int((earned_per_q > 0).sum())))
    wrong_q     = int(_n(first.get("attempt_questions_failed"),   max(answered_q - correct_q, 0)))
    unanswered  = max(total_q - answered_q, 0)
    violations  = int(_n(first.get("violation_count")))
    viol_secs   = int(_n(first.get("violation_duration_sec")))
    achieved    = _n(first.get("totalpassedscore"), float(earned_per_q.sum()))
    max_score   = _n(first.get("totalscore"), _n(questions["max_score"].sum()))
    score_pct   = _n(first.get("testpercentage"))
    total_idle  = float(questions["idle_time_sec"].fillna(0).sum())
    avg_idle    = float(questions["idle_time_sec"].fillna(0).mean()) if len(questions) else 0.0

    # Per-row outcome driven by points earned (the canonical signal)
    questions["outcome"] = questions.apply(
        lambda r: ("Correct"   if (r.get("achieved_score") or 0) > 0
                   else ("Wrong" if r.get("is_answered") else "Unanswered")),
        axis=1,
    )
    # Surface the source's `isAnswerCorrect` flag alongside; when this disagrees
    # with `outcome` it indicates a data-quality issue in the platform.
    questions["marked_correct"] = questions["is_correct"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Questions",      _fmt_int(total_q))
    c2.metric("Answered",       f"{answered_q} ({answered_q/total_q*100:.0f}%)" if total_q else "—")
    c3.metric("Correct",        f"{correct_q} ({correct_q/total_q*100:.0f}%)" if total_q else "—")
    c4.metric("Wrong",          _fmt_int(wrong_q))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Unanswered",     _fmt_int(unanswered))
    c6.metric("Score",          f"{achieved:.0f} / {max_score:.0f} ({score_pct:.1f}%)")
    c7.metric("Violations",     f"{violations} ({viol_secs}s)")
    c8.metric("Total Idle",     f"{total_idle:.0f}s · avg {avg_idle:.1f}s")

    st.divider()

    # ── Row 1: Correct/Wrong donut | Question type mix ───────────
    col_a, sep_ab, col_b = st.columns([1, 0.03, 1])
    with col_a:
        st.markdown(
            f"<div style='color:{DARK_BLUE};font-weight:700;font-size:12px;"
            f"text-transform:uppercase;letter-spacing:0.6px;"
            f"border-left:3px solid {ORANGE};padding-left:8px;margin-bottom:4px'>"
            "Correct vs Wrong vs Unanswered</div>",
            unsafe_allow_html=True,
        )
        # Drive the donut from the same KPI counts shown in the cards so the
        # two cannot disagree.
        outcome = pd.DataFrame({
            "Outcome": ["Correct", "Wrong", "Unanswered"],
            "Count":   [correct_q, wrong_q, unanswered],
        })
        outcome = outcome[outcome["Count"] > 0]
        fig_o = px.pie(
            outcome, names="Outcome", values="Count", hole=0.55,
            color="Outcome",
            color_discrete_map={"Correct": GREEN, "Wrong": RED, "Unanswered": SLATE},
            template="plotly_white",
        )
        fig_o.update_traces(textinfo="percent+label")
        fig_o.update_layout(height=260, showlegend=False,
                            margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_o, use_container_width=True)

    with sep_ab:
        st.markdown(
            f"<div style='border-left:3px solid {DARK_BLUE};height:280px;"
            "margin-top:6px;opacity:0.85'></div>",
            unsafe_allow_html=True,
        )

    with col_b:
        st.markdown(
            f"<div style='color:{DARK_BLUE};font-weight:700;font-size:12px;"
            f"text-transform:uppercase;letter-spacing:0.6px;"
            f"border-left:3px solid {ORANGE};padding-left:8px;margin-bottom:4px'>"
            "Question Type Mix</div>",
            unsafe_allow_html=True,
        )
        if "questiontype" in questions.columns and questions["questiontype"].notna().any():
            qtype = (
                questions.assign(_t=questions["questiontype"].fillna("Unknown"))
                .groupby("_t").size().reset_index(name="Count").rename(columns={"_t": "Type"})
            )
            fig_t = px.pie(
                qtype, names="Type", values="Count", hole=0.55,
                template="plotly_white",
                color_discrete_sequence=[ORANGE, NAVY, AMBER, DARK_BLUE, GREEN, "#9333EA"],
            )
            fig_t.update_traces(textinfo="percent+label")
            fig_t.update_layout(height=260, showlegend=False,
                                margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_t, use_container_width=True)
        else:
            st.info("Question type metadata not available.")

    # ── Row 2: Idle-time vs correctness scatter | Time per Q ─────
    col_c, sep_cd, col_d = st.columns([1, 0.03, 1])
    with col_c:
        st.markdown(
            f"<div style='color:{DARK_BLUE};font-weight:700;font-size:12px;"
            f"text-transform:uppercase;letter-spacing:0.6px;"
            f"border-left:3px solid {ORANGE};padding-left:8px;margin-bottom:4px'>"
            "Idle Time vs Correctness</div>",
            unsafe_allow_html=True,
        )
        plot_df = questions.copy()
        plot_df["q_num"] = range(1, len(plot_df) + 1)
        # Use the same canonical `outcome` (points-driven) the cards use
        fig_i = px.scatter(
            plot_df, x="q_num", y="idle_time_sec",
            color="outcome", size="max_score",
            color_discrete_map={"Correct": GREEN, "Wrong": RED, "Unanswered": SLATE},
            template="plotly_white", height=260,
            labels={"q_num": "Question #", "idle_time_sec": "Idle Time (s)", "outcome": ""},
            hover_data=["questiontitle", "question_difficulty"] if "questiontitle" in plot_df.columns else None,
        )
        fig_i.update_layout(margin=dict(t=10, b=10, l=0, r=0),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_i, use_container_width=True)

    with sep_cd:
        st.markdown(
            f"<div style='border-left:3px solid {DARK_BLUE};height:280px;"
            "margin-top:6px;opacity:0.85'></div>",
            unsafe_allow_html=True,
        )

    with col_d:
        st.markdown(
            f"<div style='color:{DARK_BLUE};font-weight:700;font-size:12px;"
            f"text-transform:uppercase;letter-spacing:0.6px;"
            f"border-left:3px solid {ORANGE};padding-left:8px;margin-bottom:4px'>"
            "Score Earned vs Max per Question</div>",
            unsafe_allow_html=True,
        )
        bar_df = questions.copy()
        bar_df["q_num"] = [f"Q{i+1}" for i in range(len(bar_df))]
        bar_long = pd.melt(
            bar_df[["q_num", "achieved_score", "max_score"]],
            id_vars="q_num", var_name="metric", value_name="score"
        )
        bar_long["metric"] = bar_long["metric"].map({
            "achieved_score": "Earned", "max_score": "Max"
        })
        fig_s = px.bar(
            bar_long, x="q_num", y="score", color="metric",
            barmode="group", template="plotly_white", height=260,
            color_discrete_map={"Earned": ORANGE, "Max": NAVY},
            labels={"q_num": "", "score": "Points", "metric": ""},
        )
        fig_s.update_layout(margin=dict(t=10, b=10, l=0, r=0),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_s, use_container_width=True)

    # ── Detail table ─────────────────────────────────────────────
    st.markdown("**Question-Level Detail**")
    st.caption(
        "Outcome is driven by *points earned* (the system's official score). "
        "*Marked Correct?* shows the platform's raw `isAnswerCorrect` flag — when it "
        "disagrees with Outcome, it indicates a data-quality issue in the source."
    )
    questions_display = questions.copy()
    questions_display["#"] = range(1, len(questions_display) + 1)
    cols_order = [
        "#", "questiontitle", "questiontype", "question_difficulty",
        "max_score", "achieved_score", "outcome", "marked_correct",
        "is_answered", "idle_time_sec", "question_id",
    ]
    available_q = [c for c in cols_order if c in questions_display.columns]
    table = questions_display[available_q].rename(columns={
        "questiontitle":       "Question",
        "questiontype":        "Type",
        "question_difficulty": "Difficulty",
        "max_score":           "Max Score",
        "achieved_score":      "Earned",
        "outcome":             "Outcome",
        "marked_correct":      "Marked Correct?",
        "is_answered":         "Answered?",
        "idle_time_sec":       "Idle Time (s)",
        "question_id":         "Question ID",
    })
    st.dataframe(
        table, use_container_width=True, hide_index=True,
        column_config={
            "Max Score":       st.column_config.NumberColumn(format="%.1f"),
            "Earned":          st.column_config.NumberColumn(format="%.1f"),
            "Idle Time (s)":   st.column_config.NumberColumn(format="%.1f"),
            "Answered?":       st.column_config.CheckboxColumn(),
            "Marked Correct?": st.column_config.CheckboxColumn(),
        },
    )


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def render_kpi_strip(
    kpis: pd.DataFrame,
    filtered_cp: pd.DataFrame,
    catalog_org: pd.DataFrame,
    selected_orgs: list[str],
    filtered_retake: pd.DataFrame,
) -> None:
    """Two rows of KPI cards — both rows respect the active slicers.
    Row 1 (test outcomes, from filtered_cp):
      Total Attempts | Total Pass | Total Fail | Pass Rate | Avg Duration
    Row 2 (catalog & operations):
      Assessments Created | Assessments Dispatched | Tests Created | Questions Created
      Total Violations | Avg Retake (days)
    Catalog counts come from `organization_catalog_kpis` summed over the selected
    organizations (all orgs when none selected → global total); violations and
    retake derive from the filtered attempt/retake frames.
    """
    # Row 1 — derived from current filter scope
    total_attempts = len(filtered_cp)
    total_pass = int((filtered_cp["pass_status"] == "passed").sum()) if "pass_status" in filtered_cp.columns else 0
    total_fail = int((filtered_cp["pass_status"] == "failed").sum()) if "pass_status" in filtered_cp.columns else 0
    pass_rate = (total_pass / total_attempts * 100) if total_attempts else 0
    avg_duration = filtered_cp["duration_min"].mean() if "duration_min" in filtered_cp.columns and not filtered_cp.empty else 0

    cols = st.columns(5)
    cols[0].metric("Total Attempts", _fmt_int(total_attempts))
    cols[1].metric("Total Pass", _fmt_int(total_pass))
    cols[2].metric("Total Fail", _fmt_int(total_fail))
    cols[3].metric("Pass Rate", _fmt_float(pass_rate, 1, "%"))
    cols[4].metric("Avg Duration", _fmt_float(avg_duration, 1, " min"))

    # Row 2 — catalog counts (org-scoped) + operational metrics (filter-scoped)
    # Catalog: sum the per-org view over the selected orgs (or all orgs when none
    # are selected, which equals the global total).
    catalog = catalog_org
    if not catalog.empty and selected_orgs and "organization_name" in catalog.columns:
        catalog = catalog[catalog["organization_name"].isin(selected_orgs)]

    def _sum(col: str) -> int:
        return int(catalog[col].sum()) if (not catalog.empty and col in catalog.columns) else 0

    total_violations = filtered_cp["violation_count"].sum() if "violation_count" in filtered_cp.columns and not filtered_cp.empty else 0
    if not filtered_retake.empty and "days_between_attempts" in filtered_retake.columns:
        retake = pd.to_numeric(filtered_retake["days_between_attempts"], errors="coerce").mean()
    else:
        retake = None

    cols2 = st.columns(6)
    cols2[0].metric("Assessments Created",     _fmt_int(_sum("assessments_created")))
    cols2[1].metric("Assessments Dispatched",  _fmt_int(_sum("assessments_dispatched")))
    cols2[2].metric("Tests Created",           _fmt_int(_sum("tests_created")))
    cols2[3].metric("Questions Created",       _fmt_int(_sum("questions_created")))
    cols2[4].metric("Total Violations",        _fmt_int(total_violations))
    cols2[5].metric("Avg Retake Gap",
                    _fmt_float(retake, 1, " days") if retake is not None and pd.notna(retake) else "—")


def render_monthly_trend(filtered_cp: pd.DataFrame) -> None:
    if filtered_cp.empty or "attempt_month" not in filtered_cp.columns:
        st.info("No data available for the selected filters.")
        return
    monthly = (
        filtered_cp.groupby("attempt_month")
        .agg(
            attempts=("test_id", "count"),
            passes=("is_pass", "sum"),
            avg_score=("score_pct", "mean"),
            avg_duration=("duration_min", "mean"),
        )
        .reset_index()
        .sort_values("attempt_month")
    )
    monthly["pass_rate_pct"] = monthly["passes"] / monthly["attempts"] * 100

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["attempt_month"], y=monthly["attempts"],
        name="Attempts", marker_color=ORANGE_LIGHT, yaxis="y2",
        hovertemplate="%{x}<br>Attempts: %{y:,}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=monthly["attempt_month"], y=monthly["pass_rate_pct"],
        name="Pass Rate %", mode="lines+markers",
        line=dict(color=ORANGE, width=3),
        marker=dict(size=8, color=ORANGE),
    ))
    fig.add_trace(go.Scatter(
        x=monthly["attempt_month"], y=monthly["avg_score"],
        name="Avg Score %", mode="lines+markers",
        line=dict(color=DARK_BLUE, width=2.5, dash="dot"),
        marker=dict(size=7, color=DARK_BLUE),
    ))
    fig.update_layout(
        template="plotly_white",
        height=340,
        margin=dict(t=20, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(title="Score / Pass Rate (%)", range=[0, 105]),
        yaxis2=dict(title="Attempt Volume", overlaying="y", side="right", showgrid=False),
        xaxis=dict(title=""),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_quarterly_yearly(filtered_cp: pd.DataFrame) -> None:
    c1, c2 = st.columns(2)
    if "attempt_quarter" in filtered_cp.columns and not filtered_cp.empty:
        with c1:
            st.markdown("<div class='card-title'>Quarterly Pass Rate</div>", unsafe_allow_html=True)
            q = (
                filtered_cp.groupby("attempt_quarter")
                .agg(attempts=("test_id", "count"), passes=("is_pass", "sum"))
                .reset_index()
                .sort_values("attempt_quarter")
            )
            q["pass_rate_pct"] = q["passes"] / q["attempts"] * 100
            fig = px.bar(
                q, x="attempt_quarter", y="pass_rate_pct",
                text=q["pass_rate_pct"].round(1).astype(str) + "%",
                color="pass_rate_pct",
                color_continuous_scale=[[0, RED], [0.5, AMBER], [1, GREEN]],
                range_color=[0, 100],
                template="plotly_white",
                labels={"attempt_quarter": "", "pass_rate_pct": "Pass Rate (%)"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(height=300, coloraxis_showscale=False, margin=dict(t=10, b=10, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    if "attempt_year" in filtered_cp.columns and not filtered_cp.empty:
        with c2:
            st.markdown("<div class='card-title'>Yearly Volume vs Pass Rate</div>", unsafe_allow_html=True)
            y = (
                filtered_cp.groupby("attempt_year")
                .agg(attempts=("test_id", "count"), passes=("is_pass", "sum"))
                .reset_index()
                .sort_values("attempt_year")
            )
            y["pass_rate_pct"] = y["passes"] / y["attempts"] * 100
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=y["attempt_year"], y=y["attempts"],
                name="Attempts", marker_color=NAVY,
            ))
            fig.add_trace(go.Scatter(
                x=y["attempt_year"], y=y["pass_rate_pct"],
                name="Pass Rate %", mode="lines+markers", yaxis="y2",
                line=dict(color=ORANGE, width=3), marker=dict(size=10),
            ))
            fig.update_layout(
                height=300, template="plotly_white",
                margin=dict(t=10, b=10, l=0, r=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                yaxis=dict(title="Attempts"),
                yaxis2=dict(title="Pass Rate (%)", overlaying="y", side="right",
                            range=[0, 105], showgrid=False),
            )
            st.plotly_chart(fig, use_container_width=True)


def render_pass_fail_difficulty(filtered_cp: pd.DataFrame) -> None:
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown("<div class='card-title'>Pass vs Fail Composition</div>", unsafe_allow_html=True)
        if "pass_status" in filtered_cp.columns and not filtered_cp.empty:
            pf = filtered_cp["pass_status"].value_counts().reset_index()
            pf.columns = ["status", "count"]
            fig = px.pie(
                pf, names="status", values="count", hole=0.55,
                color="status",
                color_discrete_map={"passed": GREEN, "failed": RED},
                template="plotly_white",
            )
            fig.update_traces(textinfo="percent+label")
            fig.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10),
                              showlegend=False,
                              annotations=[dict(text="Outcome", x=0.5, y=0.5,
                                                font_size=13, showarrow=False)])
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("<div class='card-title'>Attempts by Difficulty</div>", unsafe_allow_html=True)
        if "test_difficulty" in filtered_cp.columns and not filtered_cp.empty:
            d = (
                filtered_cp.groupby(["test_difficulty", "pass_status"])
                .size().reset_index(name="count")
            )
            fig = px.bar(
                d, x="test_difficulty", y="count", color="pass_status",
                color_discrete_map={"passed": GREEN, "failed": RED},
                template="plotly_white", barmode="stack",
                labels={"test_difficulty": "", "count": "Attempts", "pass_status": "Outcome"},
            )
            fig.update_layout(height=300, margin=dict(t=10, b=10, l=0, r=0),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig, use_container_width=True)


def render_violations_and_retake(filtered_cp: pd.DataFrame, retake_df: pd.DataFrame) -> None:
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown("<div class='card-title'>Monthly Violation Trend</div>", unsafe_allow_html=True)
        if "violation_count" in filtered_cp.columns and "attempt_month" in filtered_cp.columns and not filtered_cp.empty:
            v = (
                filtered_cp.groupby("attempt_month")["violation_count"].sum().reset_index()
                .sort_values("attempt_month")
            )
            fig = px.area(
                v, x="attempt_month", y="violation_count",
                template="plotly_white",
                labels={"attempt_month": "", "violation_count": "Violations"},
                color_discrete_sequence=[ORANGE],
            )
            fig.update_traces(fillcolor="rgba(249,115,22,0.25)", line_color=ORANGE)
            fig.update_layout(height=280, margin=dict(t=10, b=10, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("<div class='card-title'>Retake Interval Distribution (days)</div>", unsafe_allow_html=True)
        if not retake_df.empty and "days_between_attempts" in retake_df.columns:
            r = retake_df[retake_df["days_between_attempts"].notna()]
            r = r[(r["days_between_attempts"] >= 0) & (r["days_between_attempts"] <= 60)]
            fig = px.histogram(
                r, x="days_between_attempts", nbins=30,
                template="plotly_white",
                labels={"days_between_attempts": "Days between attempts"},
                color_discrete_sequence=[NAVY],
            )
            fig.update_traces(marker_line_color=DARK_BLUE, marker_line_width=0.5)
            fig.update_layout(height=280, margin=dict(t=10, b=10, l=0, r=0),
                              showlegend=False, bargap=0.05)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No retake data available.")


def render_freshness_bar(freshness: pd.DataFrame) -> None:
    if freshness.empty:
        return
    parts = []
    for _, row in freshness.iterrows():
        parts.append(
            f"<b style='color:#E2E8F0'>{row['table_name']}</b>"
            f"&nbsp;<span style='color:{ORANGE}'>{row['last_updated']}</span>"
        )
    html = (
        f"<div style='background:{DARK_BLUE};border-radius:8px;padding:10px 20px;"
        "font-size:12px;display:flex;gap:24px;flex-wrap:wrap;align-items:center;margin-top:16px'>"
        f"<span style='color:{ORANGE};font-weight:700;text-transform:uppercase;letter-spacing:0.6px'>Data Freshness</span>"
        + "&nbsp;|&nbsp;".join(parts) +
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.markdown("<div class='page-header'>🟧 Dodokpo Executive Intelligence</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Assessment performance, integrity & catalog operations · Gold Layer</div>", unsafe_allow_html=True)

    # Load all views in parallel
    with st.spinner("Loading live data from Athena…"):
        data, errors = load_all_data()

    cp          = data["candidate_perf"]
    kpis        = data["kpis"]
    retake_df   = data["retake"]
    catalog_org = data["catalog_org"]
    freshness   = data["freshness"]

    if errors:
        st.error("**Some views failed to load:**\n\n" + "\n\n".join(errors))

    # Sidebar slicers (Year / Quarter / Month / Difficulty)
    with st.sidebar:
        st.markdown("## ⚙ Filters")
        years = sorted([y for y in cp.get("attempt_year", pd.Series()).dropna().unique() if y])
        quarters = sorted([q for q in cp.get("attempt_quarter", pd.Series()).dropna().unique() if q])
        months = sorted([m for m in cp.get("attempt_month", pd.Series()).dropna().unique() if m])
        diffs = sorted([d for d in cp.get("test_difficulty", pd.Series()).dropna().unique() if d])
        orgs = sorted([o for o in cp.get("organization_name", pd.Series()).dropna().unique() if o])

        sel_year = st.multiselect("Year", years, default=[])
        sel_quarter = st.multiselect("Quarter", quarters, default=[])
        sel_month = st.multiselect("Month", months, default=[])
        sel_diff = st.multiselect("Difficulty", diffs, default=[])
        sel_org = st.multiselect("Organization", orgs, default=[])

        st.divider()
        st.caption(f"🟧 Connected to `{ATHENA_DATABASE}`")

    # Apply slicers
    filtered_cp = _apply_filters(cp, sel_year, sel_quarter, sel_month, sel_diff, sel_org)
    filtered_retake = retake_df
    if not retake_df.empty and "assessment_taker_id" in filtered_cp.columns:
        valid_takers = set(filtered_cp["assessment_taker_id"].unique())
        filtered_retake = retake_df[retake_df["assessment_taker_id"].isin(valid_takers)]

    if not cp.empty:
        st.success(f"**Live Data** — {len(cp):,} attempts loaded · {len(filtered_cp):,} after filters", icon="✅")

    # ───────────── KPI strip ─────────────
    render_kpi_strip(kpis, filtered_cp, catalog_org, sel_org, filtered_retake)

    st.divider()

    # ───────────── Time-based trends ─────────────
    st.markdown("<div class='card-title' style='font-size:14px'>Monthly Performance Trend — Volume, Pass Rate & Avg Score</div>", unsafe_allow_html=True)
    render_monthly_trend(filtered_cp)

    render_quarterly_yearly(filtered_cp)

    # ───────────── Pass/fail + difficulty ─────────────
    render_pass_fail_difficulty(filtered_cp)

    # ───────────── Violations + retake ─────────────
    render_violations_and_retake(filtered_cp, filtered_retake)

    st.divider()

    # ───────────── Candidate roster — one row per candidate ─────────────
    st.markdown("### Candidate Roster")
    st.caption("One row per candidate — click any row to drill into their full test history.")

    candidate_summary = _build_candidate_summary(filtered_cp)
    if candidate_summary.empty:
        st.info("No candidates found for the current filter selection.")
    else:
        st.caption(f"Showing {len(candidate_summary):,} unique candidates")
        event = st.dataframe(
            candidate_summary,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Pass Rate (%)": st.column_config.ProgressColumn(
                    "Pass Rate", format="%.1f%%", min_value=0, max_value=100,
                ),
                "Avg Score (%)": st.column_config.NumberColumn("Avg Score", format="%.1f%%"),
                "Avg Duration (min)": st.column_config.NumberColumn("Avg Duration", format="%.1f min"),
                "Last Attempt": st.column_config.DatetimeColumn("Last Attempt", format="YYYY-MM-DD HH:mm"),
            },
        )
        if event and event.get("selection") and event["selection"].get("rows"):
            idx = event["selection"]["rows"][0]
            email = candidate_summary.iloc[idx]["Email"]
            # Use the full unfiltered frame (cp) so drill-down can show
            # cross-period comparison even when slicers narrow the roster.
            show_candidate_drilldown(cp, email, retake_df)

    # ───────────── Export ─────────────
    if not filtered_cp.empty:
        st.download_button(
            "⬇ Export filtered data (CSV)",
            filtered_cp.to_csv(index=False).encode(),
            file_name="dodokpo_export.csv",
            mime="text/csv",
        )

    # ───────────── Footer ─────────────
    render_freshness_bar(freshness)


if __name__ == "__main__":
    main()
