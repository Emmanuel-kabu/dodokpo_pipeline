# Cohort & Specialization KPI Dictionary (Additional Analytics)

This page defines the **additional** analytics layer that brings reporting down from
organization level to **cohort**, **specialization**, and **individual** grain. It is
**purely additive** — it does not modify any organization-level view in
[`trainer_executive_metrics_views.sql`](../../infra/sql/trainer_executive_metrics_views.sql).
All views live in `dodokpo_dev_gold` and are defined in
[`cohort_specialization_views.sql`](../../infra/sql/cohort_specialization_views.sql).

The measures (score, pass, duration, violations, proficiency) are reused from the
untouched per-attempt base view `trainer_candidate_performance`. What this layer adds
is four new **dimensions** plus the aggregates and rankings built on them.

---

## 1. New Dimensions

| Dimension | Meaning | Derivation | Source |
| :--- | :--- | :--- | :--- |
| **specialization** | AmaliTech discipline (Backend, Frontend, Data Engineering …) | `crosswalk(normalized Domain.name)`; default `Unmapped` | `TestResult.testid → Test.domainid → Domain.name` |
| **cohort** | `<year> <program>` (e.g. `2026 NSP`); default `Unassigned`. Programs: **NSP** (12 mo, annual), **Apprenticeship** (6 mo), **CDC**, **Upskilling** | program tag from `tags` + year from dispatch `commencedate`/`createdat` | `AssessmentTaker.dispatchid → AssessmentDispatch.tags` |
| **program_type / assessment_type** | splits the conflated `tags` array into program (cohort) vs assessment purpose | classified via `cohort_tag_vocabulary` | `tags` |
| **center** | Training Center vs Service Center | program in (NSP/Apprenticeship/Upskilling) → Training Center; else a resolved specialization → Service Center | derived |

---

## 2. The Seed Layer (edit these two as real data arrives)

| View | Purpose | How to extend |
| :--- | :--- | :--- |
| **`specialization_crosswalk`** | hard map: normalized domain name → specialization | add `('<normalized domain>','<specialization>')` rows |
| **`category_crosswalk`** | hard map: normalized category → tech + parent specialization | add `('<category>','<tech>','<specialization>')` rows |
| **`cohort_tag_vocabulary`** | classifies each tag as `program` / `assessment_type` + canonical name | add `('<tag>','program'|'assessment_type','<canonical>')` rows |
| **`cohort_program_reference`** | program → cohort duration in months (NSP 12, Apprenticeship 6) | add `('<program>', <months>)` rows |

Normalization strips trailing epoch/id suffixes: `Backend Engineering 1781523206632` → `Backend Engineering`.
Re-run `python infra/sql/deploy_views.py cohort_specialization_views.sql` after editing; every metric back-fills automatically.

---

## 3. Views by Consumer

| View | Grain | Consumer |
| :--- | :--- | :--- |
| `cohort_specialization_attempt` | per attempt (base) | — |
| `cohort_performance_kpis` | per cohort | Training Center |
| `cohort_specialization_kpis` | per cohort × specialization | **Training Center (primary)** |
| `specialization_performance_kpis` | per specialization | **Service Center (primary)** |
| `specialization_tech_kpis` | per specialization × tech (content coverage) | Service Center |
| `candidate_cohort_performance` | per candidate within cohort (ranked) | Individual |
| `candidate_specialization_performance` | per candidate within specialization (ranked) | Individual |
| `cohort_progression_trend` | per cohort × month | Training Center trend |
| `additional_analytics_coverage` | single row | Data-quality gauge |

---

## 4. Metric Definitions

### Core performance set (cohort, cohort × specialization, specialization grains)

| Metric | Formula |
| :--- | :--- |
| `attempts` | `COUNT(*)` |
| `unique_candidates` | `COUNT(DISTINCT assessment_taker_id)` |
| `pass_rate_pct` | `SUM(is_pass) × 100 / COUNT(*)` |
| `first_attempt_pass_rate_pct` | passes on attempt 1 ÷ candidates with an attempt 1 |
| `avg_score_pct` | `AVG(score_pct)` |
| `median_score_pct` | `APPROX_PERCENTILE(score_pct, 0.5)` |
| `pct_advanced / intermediate / beginner` | share of attempts per `proficiency_level` tier (Advanced ≥80 · Intermediate 50–79 · Beginner <50) |
| `avg_attempts_to_pass` | `AVG(total_attempts_before_pass)` |
| `avg_duration_min` | `AVG(duration_min)` |
| `completion_rate_pct` | `AVG((questions_total − questions_failed) / questions_total) × 100` |
| `total_violations` / `avg_violations_per_attempt` | `SUM` / `AVG(violation_count)` |

### Individual grain (adds ranking within cohort / specialization)

| Metric | Formula |
| :--- | :--- |
| `attempts`, `tests_taken`, `pass_rate_pct`, `avg_score_pct` | per `assessment_taker_id` |
| `best_score_pct` / `latest_score_pct` | `MAX(score_pct)` / score at latest `attempt_number` |
| `latest_proficiency` | proficiency at latest attempt |
| `score_improvement` | latest-attempt score − first-attempt score |
| `integrity_risk_score` | `SUM(violation_count) × 2 + SUM(violation_duration_sec) / 60` (reuses org formula) |
| `rank_in_cohort` / `rank_in_specialization` | `RANK() OVER (PARTITION BY group ORDER BY avg_score_pct DESC)` |
| `percentile_in_cohort` / `percentile_in_specialization` | `PERCENT_RANK() OVER (PARTITION BY group ORDER BY avg_score_pct)` |

### Coverage / data-quality (`additional_analytics_coverage`)

| Metric | Meaning |
| :--- | :--- |
| `pct_specialization_resolved` / `pct_cohort_resolved` | % of attempts that map to a real specialization / cohort |
| `distinct_specializations` / `distinct_cohorts` | count of resolved values |
| `unmapped_specialization_attempts` / `unassigned_cohort_attempts` | volume still falling to the default bucket |

---

## 5. Current State (synthetic staging data)

With the hard crosswalks applied, **98% of attempts match a crosswalk entry**. Of 1,837 attempts:
**47.6% (875) resolve to a real specialization** (10 tracks — Software Development, Backend,
Frontend, Cloud, Software Testing, Product & Project Mgmt, Business Development, Finance,
General Education, IT Skills), **~50% (926) are excluded** (Aptitude = assessment type;
Internal/Test = scaffolding), and **~2% (36) remain Unmapped**. The
`additional_analytics_coverage` view reports this split. Excluded buckets are filtered OUT of
the specialization performance/ranking views but kept in the coverage gauge for reconciliation
(`is_excluded` flag on the base view).

**Cohort is proven end-to-end but sparse** — only ~0.1% of attempts carry a program tag today,
but the chain works: 2 NSP-tagged attempts resolve to the cohort **`2025 NSP`** (program NSP,
12-month duration, `<year> <program>` label). As real program tags (NSP/Apprenticeship/CDC/
Upskilling) populate `tags` upstream, the cohort, cohort×specialization, and candidate-in-cohort
views back-fill automatically — no code change needed.

### Notes / future work
- **`specialization_tech_kpis` is content coverage** (questions/calibration per tech), not
  candidate performance by tech — per-question response data is needed for the latter.
- `tags` carrying both a group (`Full Stack Group 1`) and an assessment type (`Aptitude`)
  is the reason program vs assessment_type are split into separate dimensions.
