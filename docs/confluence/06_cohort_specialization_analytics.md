# Cohort & Specialization Analytics — Implementation & Operations Guide

> Companion to the metric reference in [`05_cohort_specialization_kpis.md`](05_cohort_specialization_kpis.md).
> This page covers **how the feature works, how to operate it, and how to extend it.**

## 1. Purpose

Dodokpo analytics originally existed only at the **organization level**. At sprint review,
stakeholders asked to drill down to:

- **Specialization level** — for the Service Center (developers).
- **Cohort level, filterable by specialization** — for the Training Center.
- **Individual performance** within a cohort or specialization.

This feature delivers that as an **additive** layer in the gold database `dodokpo_dev_gold`.
The original organization-level views in `infra/sql/trainer_executive_metrics_views.sql`
are **not modified** — the new layer reuses them as a read-only source.

---

## 2. How it works

The analytics splits every assessment attempt along two axes:

- **People axis** — *who* took it: individual → cohort → specialization.
- **Content axis** — *what* it covered: category (tech) → domain.

The grain is **one assessment attempt**. Measures (score, pass, duration, violations,
proficiency) are reused from the untouched per-attempt view
`trainer_candidate_performance`; the new layer only attaches four dimensions.

```
 TestResult (one attempt)  ──reuse──►  trainer_candidate_performance   (ORG base — UNCHANGED)
        │                                       │
        │ assessment_taker_id                   │ test_id
        ▼                                       ▼
 AssessmentTaker.tags  (or dispatch.tags)   Test.domainid → Domain.name
        │ keyword match + year-from-tag         │ normalize + specialization_crosswalk
        ▼                                       ▼
   cohort = "<year> <program>"             specialization   (Aptitude / Internal-Test excluded)
                          \                /
                           ▼              ▼
                  cohort_specialization_attempt   (1 row/attempt + cohort, specialization,
                                   │                program_type, center, coverage flags)
          ┌────────────────────────┼─────────────────────────┐
     cohort_* views          specialization_* views     candidate_* views + coverage gauge
```

**Derivations**
- **specialization** ← assessment domain: `TestResult.testid → Test.domainid → Domain.name`,
  normalized (epoch/id suffix stripped) and mapped via `specialization_crosswalk`. Default `Unmapped`.
- **tech** ← question category, mapped via `category_crosswalk` (content/curriculum grain only).
- **cohort** ← `tags` on the taker (or its dispatch): a **keyword** match (`cohort_tag_vocabulary`)
  detects the program; the **year** is extracted from the tag (first `20xx`, else the dispatch date).
  Label = `<year> <program>`, e.g. `2025 NSP`. Default `Unassigned`.
- **center** ← Training Center if the program is NSP/Apprenticeship/Graduate/CDC/Upskilling;
  Service Center if a real specialization resolved; else Unclassified.

---

## 3. Gold-layer changes (prerequisites)

These fixes were required before the analytics could be built (gold Lambda image **`v2.3`**):

| Change | Why |
| :--- | :--- |
| Added gold dataset `test_creation_assessment_dispatch` | `AssessmentDispatch` carries the cohort `tags`; it reached silver but not gold. |
| Fixed `Skill` write path → `dodokpo_test_creation_staging/Skill/` | Was writing to a stray `dodokpo/` prefix and creating a bogus `dodokpo` Glue table. |
| Preserved `createdAt`/`updatedAt` + `TestResult.startTime`/`finishTime` | Needed for cohort-year and trend/growth analytics. |
| Fixed `organizations` config drift (`terraform apply` + new `user_mgt` silver crawler) | The table was in the repo config but missing from the live pipeline input. |

> **Known quirk (intentionally not fixed):** the org-level gold transforms' `columns_to_drop`
> lists are lowercase while the parquet columns are camelCase, so several drops
> (`organizationId`, `createdAt`, `startTime`) are silent no-ops. This is currently *load-bearing*
> (it's why those columns survive). Changing it is a separate, reviewed task.

---

## 4. View catalog (`infra/sql/cohort_specialization_views.sql`, db `dodokpo_dev_gold`)

**Seed / crosswalk (edit these to extend):**
- `specialization_crosswalk` — normalized domain → specialization (+ `is_excluded`)
- `category_crosswalk` — category → tech + parent specialization
- `cohort_tag_vocabulary` — program **keyword** → canonical program
- `cohort_program_reference` — program → cohort duration (months)

**Base:** `cohort_specialization_attempt` (one row per attempt + the four dimensions)

**Aggregates:** `cohort_performance_kpis`, `cohort_specialization_kpis`,
`specialization_performance_kpis`, `specialization_tech_kpis`,
`candidate_cohort_performance`, `candidate_specialization_performance`,
`cohort_progression_trend`, `additional_analytics_coverage`.

Metric formulas for each are in [`05_cohort_specialization_kpis.md`](05_cohort_specialization_kpis.md).

---

## 5. Runbook — maintaining the crosswalks

All mapping logic lives in the four seed views. To change a mapping, edit the `VALUES`
list and redeploy (Section 7). No Lambda or Terraform change is needed.

**Add / change a specialization** (`specialization_crosswalk`)
```sql
-- key_norm = the domain name with any trailing epoch/id suffix stripped
('Backend Engineering', 'Backend', false),     -- (key_norm, specialization, is_excluded)
('Data Science',        'Data Science', false),
('Aptitude',            'Aptitude', true),      -- is_excluded=true => kept in coverage, hidden from spec views
```

**Add a tech** (`category_crosswalk`)
```sql
('Kafka', 'Kafka', 'Backend'),                 -- (category, tech, specialization)
```

**Add / change a cohort program** (`cohort_tag_vocabulary` + `cohort_program_reference`)
```sql
-- keyword is matched case-insensitively as a SUBSTRING of the tag, so
-- "2025 National Service Personnel" matches 'national service'.
('national service', 'NSP'),                   -- (keyword, program)
('graduate',         'Graduate'),
-- and give it a duration:
('NSP', 12),                                    -- (program, duration_months)
```

Notes:
- Domain matching is **normalized exact** (case-insensitive) on the cleaned name.
- Tag→program matching is **case-insensitive substring**, because real tags embed the
  program in longer strings (`CDC December 2025`, `IT Skill Batch 2026`).
- Anything not mapped falls to `Unmapped` (specialization) or `Unassigned` (cohort) and is
  reported by `additional_analytics_coverage`.

---

## 6. Dashboards (`dashboard/`, Streamlit multipage)

| File | Page |
| :--- | :--- |
| `app.py` | Executive (org-level) — **unchanged** except a 3-button nav bar |
| `pages/1_Training_Center.py` | **Training Center** — cohort KPIs, cohort × specialization heatmap, progression trend, ranked candidate roster; filters: cohort / program / specialization |
| `pages/2_Service_Center.py` | **Service Center** — specialization KPIs, proficiency mix, tech content coverage, ranked developer roster; filters: specialization / tech, Hide-Unmapped |
| `shared.py` | Shared theme, Athena query helper, formatters, and `render_nav()` (the cross-page buttons) |

Navigation: every page shows the **Executive / Training Center / Service Center** buttons at
the top (plus Streamlit's sidebar nav). Each page reads the gold views live via Athena and
caches results for 5 minutes.

**Run locally**
```bash
streamlit run dashboard/app.py        # from repo root, using the project venv
```

---

## 7. Operations

**Deploy / redeploy the analytics views** (after editing the SQL file):
```bash
python infra/sql/deploy_views.py cohort_specialization_views.sql   # one file
python infra/sql/deploy_views.py                                   # all view files
```

**Deploy a new gold Lambda image** (ECR is IMMUTABLE — bump the tag; Terraform ignores the
image, so update the function out-of-band):
```bash
REPO=585008053249.dkr.ecr.eu-west-1.amazonaws.com/dodokpo-dev-gold-transform
docker build --platform linux/amd64 --provenance=false --sbom=false -t $REPO:v2.4 src/lambda/gold
docker push $REPO:v2.4
aws lambda update-function-code --function-name dodokpo-dev-gold-transform --image-uri $REPO:v2.4 --publish
```
> Always build with `--provenance=false` — Docker's default attestation manifest is rejected by Lambda.

**One-off backfill** (don't wait for the weekly run):
```bash
aws lambda invoke --function-name dodokpo-dev-gold-transform \
  --cli-binary-format raw-in-base64-out \
  --payload '{"datasets":["test_creation_assessment_dispatch"]}' out.json
```

**Cadence:** the pipeline runs weekly (silver/gold Mondays 06:00 UTC); bronze export lands
weekly (Sundays). Dashboard results are Athena-cached for 5 minutes (clear via ☰ → Clear cache).

**Config:** database `dodokpo_dev_gold` · workgroup `dodokpo-dev-workgroup` · region `eu-west-1`.

---

## 8. Data quality & coverage

`additional_analytics_coverage` is the trust gauge. Current state on the present data:

- **Specialization:** ~47.6% of attempts resolve to a real specialization (10 tracks);
  ~50% are excluded (`Aptitude` = assessment type, `Internal/Test` = scaffolding); ~2% `Unmapped`.
- **Cohort:** ~1.2% of attempts carry a recognized program tag (4 cohorts: 2025 NSP, 2025
  Graduate, 2025 CDC, 2026 Upskilling).

The low cohort coverage is **not a logic gap** — most assessments are dispatched with a
**skill-group/specialization** tag (`Frontend`, `Full Stack Group 1`, `Software Testing`)
rather than a **program** tag. Coverage rises automatically as more dispatches are
program-tagged upstream.

---

## 9. Known limitations & follow-ups

- **Cohort coverage depends on upstream program-tagging** — biggest lever; owned by the
  assessment-platform/data team (separate ticket).
- **Production vs staging** — confirm whether reporting should run on the production export.
- **`specialization_tech_kpis` is content coverage**, not per-tech candidate performance
  (the latter needs per-question response data).
- **36 Unmapped domains** — extend `specialization_crosswalk` as needed.
- **Gold transform case-sensitivity quirk** (Section 3) — separate reviewed change.
- Optional: candidate per-attempt drill-down modals in the new dashboards; a `group`
  sub-dimension from skill-group tags.
