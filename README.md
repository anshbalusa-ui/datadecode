# DECODE Competition Intelligence — Team 3470

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/anshbalusa-ui/datadecode/blob/main/DECODE_Competition_Intelligence_Colab.ipynb)

An **explainable Python scouting-analysis pipeline** for the anonymized DECODE dataset. The goal is to turn six observations per team into practical decisions for **FTC Team 3470**: overall strength, reliable alliance partners, robot roles, risk, and match strategy. This project is a data-analysis certification submission, **not a trained machine-learning model**. ML was optional and the dataset is too small to warrant an opaque predictor.

## Start here

| Want to… | Open |
|---|---|
| **Run and demonstrate the full analysis** | [Google Colab notebook](DECODE_Competition_Intelligence_Colab.ipynb) · [Run in Colab ↗](https://colab.research.google.com/github/anshbalusa-ui/datadecode/blob/main/DECODE_Competition_Intelligence_Colab.ipynb) |
| **Read the conclusions** | [13-page final report (PDF)](report/DECODE_Competition_Intelligence_Report.pdf) |
| **See all team rankings** | [Overall rankings](outputs/team_rankings.csv) |
| **Pick 3470's partners** | [3470 compatibility ranking](outputs/compatibility_ranking_3470.csv) · [Final picklist](outputs/alliance_picklist.csv) |
| **Review the source** | [Analysis engine](src/analyze_decode.py) · [Report builder](src/build_report.py) |
| **Check questionable records** | [Cleaning log](outputs/cleaning_log.csv) · [Match-prefix audit](outputs/match_prefix_audit.csv) |
| **Prepare for questions** | [Interview explanations](INTERVIEW_PREP.md) · [AI use](AI_USE_DISCLOSURE.md) |

**Colab demo:** click **Open in Colab**, then **Runtime → Run all**. The original workbook is embedded in the notebook with a SHA-256 integrity check, so no uploads or Drive permissions are necessary. It generates the cleaned workbook, rankings, figures, and a ZIP of outputs. You may need to approve notebook execution in your own Colab session.

## Findings at a glance

- **#1 overall:** T08. **Team 3470:** #6 overall (within this six-observation sample).
- **Top five 3470 partner choices:** **T08, T14, T17, T02, T06**, based on a *separate* compatibility model rather than overall ranking alone.
- **3470's strength:** fast cycles (88th percentile) with no recorded breakdowns and 6/6 autonomous leaves.
- **3470's bottleneck:** average cycle time rises from **12.40 s** in its first two observations to **17.55 s** in its last two; three notes mention an overflow slowdown. This is an **actionable hypothesis**, not established causality.
- **Most important data caveat:** all 36 reused `M##` prefixes contain same-color alliance-score conflicts. They **cannot be assumed to be official global match IDs**; contextual win-based labels are provisional. See the [match-prefix audit](outputs/match_prefix_audit.csv).

## How the model works

1. **Clean without fabricating data.** Remove one exact duplicate (109 → 108 rows), preserve missing values, flag anomalies, and exclude one extremely suspicious low-confidence T05 CL observation *from the CL aggregate only* while keeping it in the cleaned file.
2. **Aggregate** match-level actions, average cycle speed, driver and defense ratings, penalties, breakdowns, and consistency for all **18 teams**.
3. **Rank robots** with within-field percentiles to put unlike units on a 0–100 scale: **45% scoring volume + 15% objectives + 15% cycle speed + 15% reliability + 10% defense.** These are analyst-chosen weights, not official scoring points. Rankings are compared under alternative weighting schemes in [`rank_sensitivity.csv`](outputs/rank_sensitivity.csv).
4. **Rank alliance partners** separately using Team 3470's weaknesses, complementary CL/depot/defense/motif production, overall strength, reliability, flexibility, and risk.
5. **Report uncertainty** instead of inferring unsupported win probabilities, exact point contributions, or matchup predictions from partial scouting data.

**Important:** Alliance score and win rate are *not* included in robot-strength scores because they reflect both robots, opponents, and schedule effects. The “overrated/underrated” analysis is based on provisional outcome context and is less reliable than action-derived metrics.

## Repository structure

```text
datadecode/
├── DECODE_Competition_Intelligence_Colab.ipynb  # one-click live walkthrough
├── README.md
├── requirements.txt
├── AI_USE_DISCLOSURE.md
├── INTERVIEW_PREP.md
├── SUBMISSION_CHECKLIST.md
├── data/
│   ├── DECODE_Candidate_1_original.xlsx         # unchanged source
│   ├── DECODE_Candidate_1_cleaned.xlsx          # annotated cleaned workbook
│   └── raw_matches.csv                          # input exported from Matches sheet
├── src/
│   ├── analyze_decode.py                        # complete reproducible pipeline
│   └── build_report.py                          # editable DOCX report generator
├── outputs/                                     # rankings, picklist, QC, strategies
├── figures/                                     # performance charts
├── report/                                      # PDF and editable DOCX
└── tests/                                       # basic reproducibility smoke test
```

## Run locally (Python 3.10+)

```bash
python -m pip install -r requirements.txt
python src/analyze_decode.py --input data/raw_matches.csv --output-dir outputs --figures-dir figures
python src/build_report.py
python -m unittest discover -s tests -v
```

The first command installs the dependencies. The analysis script uses Python's standard library for ranking and `matplotlib` for graphs; the report builder uses `python-docx`. The Colab notebook additionally uses `pandas` and an Excel writer for display and export. Rebuilding the DOCX does not automatically convert it into PDF; the checked-in PDF is the publication copy.

## Assignment coverage

The [submission checklist](SUBMISSION_CHECKLIST.md) maps **all 11 required deliverables** to files: source code, cleaned data, final report, overall/3470 rankings, picklist, recommendations, strategy examples, ambiguity analysis, README, and AI-use disclosure. The report additionally answers the **15 analytical questions** (including archetypes, data quality, risk, 3470's weak points, and three hypothetical matchups).

## Limitations & verification

There are **six rows per team**, no official per-action point weights, no reliable alliance partner/opponent graph, and no proof that the `M##` prefix identifies one actual match. Certain scout ratings are subjective; two T12 cycle values are missing; T05 has a flagged 28-CL observation. Results are *comparative guidance*, not official competition rankings or a validated predictive model. To resolve uncertainty, collect official match IDs/score sheets, video, timestamped cycle telemetry, independent scouting, and alliance details.

**AI disclosure:** AI was used in developing this project; see [AI_USE_DISCLOSURE.md](AI_USE_DISCLOSURE.md). The candidate should personally run the notebook, verify key records and figures, and be able to defend the weighting and exclusions before submitting or interviewing.
