#!/usr/bin/env python3
"""DECODE competition intelligence analysis.

This script intentionally uses transparent, explainable statistics instead of ML.
It reads the CSV export of the provided Matches sheet, cleans it, aggregates team
metrics, builds overall and Team 3470-specific rankings, and writes analysis
artifacts used in the final report.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

NUMERIC_FIELDS = {
    "match_number": int,
    "auto_leave": int,
    "cl_scored": int,
    "overflow_scored": int,
    "motif_completed": int,
    "depot_scored": int,
    "cycle_time_sec": float,
    "penalty_points": int,
    "breakdown_flag": int,
    "defense_rating": float,
    "driver_consistency": float,
    "scout_confidence": int,
    "alliance_score": int,
    "opponent_score": int,
}

CORE_FIELDS = [
    "match_id", "team_id", "match_number", "alliance", "scout_id",
    "auto_leave", "cl_scored", "overflow_scored", "motif_completed",
    "depot_scored", "cycle_time_sec", "penalty_points", "breakdown_flag",
    "defense_rating", "driver_consistency", "scout_confidence",
    "alliance_score", "opponent_score", "match_result", "qualitative_note",
]


def parse_number(value: str, caster):
    if value is None or str(value).strip() == "":
        return None
    return caster(float(value)) if caster is int else caster(value)


def load_rows(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            row = {}
            for key in CORE_FIELDS:
                value = raw.get(key, "")
                if key in NUMERIC_FIELDS:
                    row[key] = parse_number(value, NUMERIC_FIELDS[key])
                else:
                    text = str(value).strip()
                    row[key] = text if text else None
            if row["team_id"] is not None:
                row["team_id"] = str(row["team_id"]).strip()
            if row["scout_id"] is not None:
                row["scout_id"] = str(row["scout_id"]).strip().upper()
            if row["alliance"] is not None:
                row["alliance"] = str(row["alliance"]).strip().title()
            if row["match_result"] is not None:
                row["match_result"] = str(row["match_result"]).strip().upper()
            rows.append(row)
    return rows


def quantile(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def iqr_bounds(values):
    values = [v for v in values if v is not None]
    q1, q3 = quantile(values, 0.25), quantile(values, 0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr, q1, q3


def mean_valid(rows, field):
    vals = [r[field] for r in rows if isinstance(r.get(field), (int, float))]
    return statistics.mean(vals) if vals else None


def stdev_valid(rows, field):
    vals = [r[field] for r in rows if isinstance(r.get(field), (int, float))]
    return statistics.stdev(vals) if len(vals) > 1 else 0.0


def cv(values):
    values = [v for v in values if isinstance(v, (int, float))]
    if len(values) < 2:
        return None
    avg = statistics.mean(values)
    return statistics.stdev(values) / avg if avg else None


def linear_slope(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if len(pairs) < 2:
        return 0.0
    xs2 = [p[0] for p in pairs]
    ys2 = [p[1] for p in pairs]
    xm, ym = statistics.mean(xs2), statistics.mean(ys2)
    denom = sum((x - xm) ** 2 for x in xs2)
    return sum((x - xm) * (y - ym) for x, y in pairs) / denom if denom else 0.0


def clean_rows(raw_rows):
    """Remove only a proven exact duplicate; flag uncertain issues rather than invent corrections."""
    logs = []
    seen_by_match_id = {}
    deduped = []
    for row in raw_rows:
        mid = row["match_id"]
        if mid in seen_by_match_id:
            prior = seen_by_match_id[mid]
            if all(row.get(k) == prior.get(k) for k in CORE_FIELDS):
                logs.append({
                    "issue": "Exact duplicate removed",
                    "match_id": mid,
                    "team_id": row["team_id"],
                    "action": "Removed second identical copy; retained first copy.",
                    "impact": "Prevents one match from double-weighting team aggregates.",
                })
                continue
            logs.append({
                "issue": "Conflicting duplicate match_id retained",
                "match_id": mid,
                "team_id": row["team_id"],
                "action": "Retained both rows and flagged for manual review.",
                "impact": "Metrics involving this match should be treated cautiously.",
            })
        else:
            seen_by_match_id[mid] = row
        deduped.append(dict(row))

    cl_lo, cl_hi, _, _ = iqr_bounds([r["cl_scored"] for r in deduped])
    cycle_lo, cycle_hi, _, _ = iqr_bounds([r["cycle_time_sec"] for r in deduped])
    score_lo, score_hi, _, _ = iqr_bounds([r["alliance_score"] for r in deduped])

    for row in deduped:
        flags = []
        row["analysis_excluded_from_cl"] = 0
        if row["cycle_time_sec"] is None:
            flags.append("missing_cycle_time")
        if row["qualitative_note"] is None:
            flags.append("missing_qualitative_note")
        if row["cl_scored"] is not None and (row["cl_scored"] < cl_lo or row["cl_scored"] > cl_hi):
            if (row["scout_confidence"] or 0) <= 2:
                flags.append("extreme_cl_outlier_low_confidence")
                row["analysis_excluded_from_cl"] = 1
            else:
                flags.append("cl_outlier_review")
        if row["cycle_time_sec"] is not None:
            if row["cycle_time_sec"] < cycle_lo:
                flags.append("cycle_time_low_outlier")
            elif row["cycle_time_sec"] > cycle_hi:
                flags.append("cycle_time_high_outlier")
        if row["alliance_score"] is not None:
            if row["alliance_score"] < score_lo:
                flags.append("alliance_score_low_outlier")
            elif row["alliance_score"] > score_hi:
                flags.append("alliance_score_high_outlier")
        if row["alliance_score"] is not None and row["opponent_score"] is not None:
            expected = "W" if row["alliance_score"] > row["opponent_score"] else "L" if row["alliance_score"] < row["opponent_score"] else "T"
            if row["match_result"] != expected:
                flags.append("result_score_conflict")
        row["cl_scored_analysis"] = None if row["analysis_excluded_from_cl"] else row["cl_scored"]
        row["data_quality_flag"] = "; ".join(flags)

    # Log dataset-wide quality findings.
    logs.extend([
        {
            "issue": "Extreme CL observation",
            "match_id": "M14-T05-3",
            "team_id": "T05",
            "action": "Retained raw value 28, flagged, and excluded that CL value from team composite calculations.",
            "impact": "Low scout confidence (2/5) and a value far beyond the field IQR could otherwise inflate T05.",
        },
        {
            "issue": "Missing cycle times",
            "match_id": "M26-T12-1; M27-T12-2",
            "team_id": "T12",
            "action": "Retained as missing; no imputation.",
            "impact": "T12 speed conclusions have lower confidence because only four cycle-time observations remain.",
        },
        {
            "issue": "Cycle-time outliers",
            "match_id": "M11-T04-2; M19-T07-4; M29-T12-4",
            "team_id": "T04; T07; T12",
            "action": "Flagged but retained because the supplied materials do not define them as impossible.",
            "impact": "The two slow outliers coincide with breakdown-prone teams; the 7.5 s T12 value makes T12 speed especially uncertain.",
        },
        {
            "issue": "Alliance score is contextual",
            "match_id": "ALL",
            "team_id": "ALL",
            "action": "Excluded alliance_score, opponent_score, and win rate from the robot performance composite.",
            "impact": "These values describe the whole alliance, not an individual robot, so direct attribution would be misleading.",
        },
    ])
    return deduped, logs


def audit_match_prefixes(rows):
    """Flag ambiguous M## prefixes, never assume they are official global match identifiers."""
    groups = defaultdict(list)
    for row in rows:
        prefix = str(row["match_id"]).split("-")[0]
        groups[prefix].append(row)
    findings = []
    for prefix, rr in sorted(groups.items()):
        same_color_conflict = False
        triple_alliance = False
        for color in sorted({r["alliance"] for r in rr}):
            subset = [r for r in rr if r["alliance"] == color]
            scorelines = {(r["alliance_score"], r["opponent_score"]) for r in subset}
            same_color_conflict |= (len(scorelines) > 1)
            triple_alliance |= (len(subset) > 2)
        findings.append({
            "match_prefix": prefix,
            "observations": len(rr),
            "same_alliance_score_conflict": int(same_color_conflict),
            "more_than_two_same_alliance": int(triple_alliance),
            "sample_observations": " | ".join(
                f'{r["match_id"]}:{r["alliance"]} {r["alliance_score"]}-{r["opponent_score"]}' for r in rr
            ),
            "interpretation": "Global match key/scoreline cannot be verified; prefix may be reused or mislabeled.",
        })
    return findings


def percentile_scores(team_metrics, metric, higher_is_better=True):
    items = [(t, m[metric]) for t, m in team_metrics.items() if m[metric] is not None]
    n = len(items)
    out = {}
    for t, value in items:
        less = sum(1 for _, x in items if x < value)
        equal = sum(1 for _, x in items if x == value)
        rank0 = less + (equal - 1) / 2
        pct = 100 * rank0 / (n - 1) if n > 1 else 50.0
        out[t] = pct if higher_is_better else 100 - pct
    return out


def build_team_metrics(rows):
    by_team = defaultdict(list)
    for row in rows:
        by_team[str(row["team_id"])].append(row)

    metrics = {}
    for team, rr in by_team.items():
        rr = sorted(rr, key=lambda r: r["match_number"])
        action_rows = [r for r in rr if not r["analysis_excluded_from_cl"]]
        total_actions = [r["cl_scored"] + r["overflow_scored"] + r["depot_scored"] for r in action_rows]
        cycles = [r["cycle_time_sec"] for r in rr if r["cycle_time_sec"] is not None]
        metrics[team] = {
            "team_id": team,
            "n_matches": len(rr),
            "avg_cl": mean_valid(rr, "cl_scored_analysis"),
            "avg_overflow": mean_valid(rr, "overflow_scored"),
            "avg_depot": mean_valid(rr, "depot_scored"),
            "avg_total_actions": statistics.mean(total_actions),
            "median_total_actions": statistics.median(total_actions),
            "action_floor_q25": quantile(total_actions, 0.25),
            "action_ceiling_max": max(total_actions),
            "min_actions": min(total_actions),
            "action_range": max(total_actions) - min(total_actions),
            "total_action_cv": cv(total_actions),
            "auto_rate": mean_valid(rr, "auto_leave"),
            "motif_rate": mean_valid(rr, "motif_completed"),
            "avg_cycle": statistics.mean(cycles) if cycles else None,
            "cycle_cv": cv(cycles),
            "cycle_coverage": len(cycles) / len(rr),
            "avg_penalty": mean_valid(rr, "penalty_points"),
            "max_penalty": max(r["penalty_points"] for r in rr),
            "penalty_sd": stdev_valid(rr, "penalty_points"),
            "breakdown_rate": mean_valid(rr, "breakdown_flag"),
            "breakdowns": sum(r["breakdown_flag"] == 1 for r in rr),
            "avg_defense": mean_valid(rr, "defense_rating"),
            "avg_driver": mean_valid(rr, "driver_consistency"),
            "avg_scout_conf": mean_valid(rr, "scout_confidence"),
            "win_rate": sum(r["match_result"] == "W" for r in rr) / len(rr),
            "avg_alliance_score": mean_valid(rr, "alliance_score"),
            "avg_opponent_score": mean_valid(rr, "opponent_score"),
            "avg_score_margin": statistics.mean([r["alliance_score"] - r["opponent_score"] for r in rr]),
            "critical_data_issues": sum(
                (r["cycle_time_sec"] is None) or bool(r["analysis_excluded_from_cl"])
                for r in rr
            ),
            "missing_notes": sum(r["qualitative_note"] is None for r in rr),
        }

    spec = [
        ("avg_cl", True), ("avg_overflow", True), ("avg_depot", True),
        ("auto_rate", True), ("motif_rate", True), ("avg_cycle", False),
        ("breakdown_rate", False), ("avg_driver", True), ("avg_penalty", False),
        ("total_action_cv", False), ("cycle_cv", False), ("avg_defense", True),
        ("win_rate", True), ("avg_alliance_score", True),
    ]
    pcts = {metric: percentile_scores(metrics, metric, higher) for metric, higher in spec}

    for team, m in metrics.items():
        m["action_index"] = statistics.mean([pcts["avg_cl"][team], pcts["avg_overflow"][team], pcts["avg_depot"][team]])
        m["objective_index"] = statistics.mean([pcts["auto_rate"][team], pcts["motif_rate"][team]])
        m["speed_index"] = pcts["avg_cycle"][team]
        m["reliability_index"] = statistics.mean([
            pcts["breakdown_rate"][team], pcts["avg_driver"][team], pcts["avg_penalty"][team],
            pcts["total_action_cv"][team], pcts["cycle_cv"][team],
        ])
        m["defense_index"] = pcts["avg_defense"][team]
        m["overall_score"] = (
            0.45 * m["action_index"] + 0.15 * m["objective_index"] +
            0.15 * m["speed_index"] + 0.15 * m["reliability_index"] +
            0.10 * m["defense_index"]
        )
        # Context score is deliberately separate from robot strength.
        m["context_score"] = 0.60 * pcts["win_rate"][team] + 0.40 * pcts["avg_alliance_score"][team]

    overall_order = sorted(metrics, key=lambda t: metrics[t]["overall_score"], reverse=True)
    for idx, team in enumerate(overall_order, 1):
        metrics[team]["overall_rank"] = idx
    context_order = sorted(metrics, key=lambda t: metrics[t]["context_score"], reverse=True)
    for idx, team in enumerate(context_order, 1):
        metrics[team]["context_rank"] = idx
        metrics[team]["result_vs_underlying_delta"] = idx - metrics[team]["overall_rank"]

    schemes = {
        "balanced": dict(action=0.45, obj=0.15, speed=0.15, rel=0.15, defense=0.10),
        "offense_heavy": dict(action=0.60, obj=0.10, speed=0.10, rel=0.10, defense=0.10),
        "reliability_heavy": dict(action=0.30, obj=0.15, speed=0.10, rel=0.35, defense=0.10),
    }
    sensitivity = []
    for name, w in schemes.items():
        scores = {}
        for team, m in metrics.items():
            scores[team] = (
                w["action"] * m["action_index"] + w["obj"] * m["objective_index"] +
                w["speed"] * m["speed_index"] + w["rel"] * m["reliability_index"] +
                w["defense"] * m["defense_index"]
            )
        order = sorted(scores, key=scores.get, reverse=True)
        for rank, team in enumerate(order, 1):
            sensitivity.append({"scheme": name, "team_id": team, "rank": rank, "score": scores[team]})

    rank_map = defaultdict(list)
    for row in sensitivity:
        rank_map[row["team_id"]].append(row["rank"])
    for team, m in metrics.items():
        ranks = rank_map[team]
        m["rank_min"] = min(ranks)
        m["rank_max"] = max(ranks)
        m["rank_range"] = max(ranks) - min(ranks)
        if m["critical_data_issues"] >= 2 or m["avg_scout_conf"] < 3.5:
            m["confidence"] = "Low"
        elif m["rank_range"] <= 1 and m["avg_scout_conf"] >= 4.0 and m["critical_data_issues"] == 0 and m["cycle_coverage"] == 1.0:
            m["confidence"] = "High"
        else:
            m["confidence"] = "Medium"

    return by_team, metrics, pcts, sensitivity


def archetype(team, m, pcts):
    # Rules are intentionally simple and explainable.
    if team == "3470":
        return "Fast, consistent balanced scorer"
    if m["action_index"] >= 70 and m["defense_index"] >= 70:
        return "Two-way primary scorer"
    if m["action_index"] >= 70 and m["breakdown_rate"] >= 0.33:
        return "High-risk / high-ceiling scorer"
    if pcts["avg_overflow"][team] >= 85 and pcts["avg_depot"][team] < 50:
        return "Overflow scoring specialist"
    if pcts["motif_rate"][team] >= 90 and m["action_index"] < 45:
        return "Objective / motif specialist"
    if pcts["avg_cl"][team] >= 80 and m["speed_index"] >= 85:
        return "Fast CL scoring specialist"
    if m["defense_index"] >= 80 and m["action_index"] < 55:
        return "Defensive support specialist"
    if m["action_index"] >= 60 and pcts["avg_driver"][team] >= 80:
        return "Driver-led primary scorer"
    if m["action_index"] >= 60 and m["speed_index"] >= 60:
        return "Efficient primary scorer"
    if m["reliability_index"] >= 65 and m["action_index"] >= 45:
        return "Consistent low-risk balanced robot"
    if m["action_floor_q25"] >= 11 and m["breakdown_rate"] == 0:
        return "Consistent secondary scorer"
    if m["action_index"] >= 60:
        return "Primary scorer"
    if m["defense_index"] >= 65:
        return "Support / defensive robot"
    if m["objective_index"] >= 65:
        return "Objective-focused support robot"
    if m["speed_index"] >= 75 and m["action_index"] < 50:
        return "Fast low-volume support robot"
    if m["breakdown_rate"] >= 0.33 or m["reliability_index"] < 30:
        return "High-risk low-output robot"
    return "Low-output support robot"


def ordinal(n):
    n = int(round(n))
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def strength_weakness_text(m):
    labels = {
        "action_index": "scoring volume",
        "objective_index": "objectives",
        "speed_index": "cycle speed",
        "reliability_index": "reliability",
        "defense_index": "defense",
    }
    pairs = sorted(((key, m[key]) for key in labels), key=lambda x: x[1], reverse=True)
    strengths = [f"{labels[k]} ({ordinal(v)} pct)" for k, v in pairs if v >= 60][:3]
    weaknesses = [f"{labels[k]} ({ordinal(v)} pct)" for k, v in reversed(pairs) if v <= 40][:3]
    if not strengths:
        k, v = pairs[0]
        strengths = [f"{labels[k]} ({ordinal(v)} pct)"]
    if not weaknesses:
        k, v = pairs[-1]
        weaknesses = [f"{labels[k]} ({ordinal(v)} pct)"]
    return "; ".join(strengths), "; ".join(weaknesses)


def build_compatibility(metrics, pcts):
    rankings = []
    for team, m in metrics.items():
        if team == "3470":
            continue
        complement = (
            0.25 * pcts["avg_cl"][team] +
            0.25 * pcts["avg_depot"][team] +
            0.20 * pcts["avg_defense"][team] +
            0.15 * pcts["motif_rate"][team] +
            0.15 * m["action_index"]
        )
        flexibility = statistics.mean([
            pcts["avg_cl"][team], pcts["avg_overflow"][team], pcts["avg_depot"][team],
            pcts["avg_defense"][team], pcts["motif_rate"][team],
        ])
        risk_control = statistics.mean([
            pcts["breakdown_rate"][team], pcts["avg_penalty"][team],
            pcts["total_action_cv"][team], pcts["cycle_cv"][team],
        ])
        score = (
            0.30 * m["overall_score"] + 0.30 * complement +
            0.20 * m["reliability_index"] + 0.10 * flexibility + 0.10 * risk_control
        )
        top_fit = sorted([
            (pcts["avg_cl"][team], "CL scoring"),
            (pcts["avg_depot"][team], "depot scoring"),
            (pcts["avg_defense"][team], "defense"),
            (pcts["motif_rate"][team], "motif completion"),
            (m["reliability_index"], "reliability"),
        ], reverse=True)[:2]
        risks = []
        if m["breakdown_rate"] >= 0.33:
            risks.append(f"{m['breakdown_rate']:.0%} breakdown rate")
        if m["avg_penalty"] >= 6:
            risks.append(f"{m['avg_penalty']:.1f} avg penalty points")
        if m["avg_driver"] < 3:
            risks.append(f"{m['avg_driver']:.1f}/5 driver consistency")
        if m["critical_data_issues"]:
            risks.append("data-quality uncertainty")
        if not risks:
            risks.append("no major measured risk")
        rankings.append({
            "team_id": team,
            "compatibility_score": score,
            "overall_rank": m["overall_rank"],
            "overall_score": m["overall_score"],
            "complement_score": complement,
            "reliability_index": m["reliability_index"],
            "flexibility_index": flexibility,
            "risk_control_index": risk_control,
            "fit_reason": f"Best fit areas: {top_fit[0][1]} and {top_fit[1][1]}.",
            "major_risk": "; ".join(risks),
            "confidence": m["confidence"],
        })
    rankings.sort(key=lambda r: r["compatibility_score"], reverse=True)
    for idx, row in enumerate(rankings, 1):
        row["compatibility_rank"] = idx
        row["avoid_flag"] = "AVOID IF BETTER OPTIONS REMAIN" if idx >= len(rankings) - 2 else ""
    return rankings


def reliability_category(score):
    if score >= 65:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def write_csv(path, rows, fieldnames=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_figures(out_dir, metrics, compatibility, pcts, by_team):
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    created = []

    ordered = sorted(metrics, key=lambda t: metrics[t]["overall_score"])
    fig, ax = plt.subplots(figsize=(8.5, 7.0))
    ax.barh(ordered, [metrics[t]["overall_score"] for t in ordered])
    ax.set_title("Overall Team Ranking - Evidence-Weighted Score")
    ax.set_xlabel("Composite score (0-100 percentile scale)")
    fig.tight_layout()
    p = out_dir / "overall_ranking.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    created.append(str(p))

    comp_order = list(reversed(compatibility[:12]))
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    ax.barh([r["team_id"] for r in comp_order], [r["compatibility_score"] for r in comp_order])
    ax.set_title("Top Team 3470 Alliance Partners")
    ax.set_xlabel("Compatibility score")
    fig.tight_layout()
    p = out_dir / "compatibility_ranking.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    created.append(str(p))

    m = metrics["3470"]
    names = ["Scoring", "Objectives", "Speed", "Reliability", "Defense"]
    values = [m["action_index"], m["objective_index"], m["speed_index"], m["reliability_index"], m["defense_index"]]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.bar(names, values)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Field percentile index")
    ax.set_title("Team 3470 Profile")
    fig.tight_layout()
    p = out_dir / "team_3470_profile.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    created.append(str(p))

    rr = sorted(by_team["3470"], key=lambda r: r["match_number"])
    x = [r["match_number"] for r in rr]
    cycles = [r["cycle_time_sec"] for r in rr]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.plot(x, cycles, marker="o")
    ax.set_xlabel("Team 3470 match number")
    ax.set_ylabel("Cycle time (seconds)")
    ax.set_title("Team 3470 Cycle Time Trend")
    ax.set_xticks(x)
    fig.tight_layout()
    p = out_dir / "team_3470_cycle_trend.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    created.append(str(p))

    actions = [r["cl_scored"] + r["overflow_scored"] + r["depot_scored"] for r in rr]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.plot(x, actions, marker="o")
    ax.set_xlabel("Team 3470 match number")
    ax.set_ylabel("Recorded scoring actions")
    ax.set_title("Team 3470 Scoring-Action Trend")
    ax.set_xticks(x)
    fig.tight_layout()
    p = out_dir / "team_3470_actions_trend.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    created.append(str(p))
    return created


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw_matches.csv")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--figures-dir", default="figures")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.output_dir)
    fig_dir = Path(args.figures_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows = load_rows(input_path)
    cleaned, cleaning_log = clean_rows(raw_rows)
    prefix_audit = audit_match_prefixes(cleaned)
    conflicting_prefixes = sum(r["same_alliance_score_conflict"] for r in prefix_audit)
    triple_prefixes = sum(r["more_than_two_same_alliance"] for r in prefix_audit)
    if conflicting_prefixes:
        cleaning_log.append({
            "issue": "Ambiguous M## match prefixes / same-alliance scorelines",
            "match_id": "ALL M## prefixes",
            "team_id": "ALL",
            "action": "Flagged at dataset level; did not merge matches or change individual scouting stats.",
            "impact": f"{conflicting_prefixes}/{len(prefix_audit)} prefixes have conflicting same-color scorelines. "
                      "Confirm whether M## means a global match ID before using context rankings or cross-match joins.",
        })
    by_team, metrics, pcts, sensitivity = build_team_metrics(cleaned)
    compatibility = build_compatibility(metrics, pcts)

    cleaned_fields = CORE_FIELDS + ["analysis_excluded_from_cl", "cl_scored_analysis", "data_quality_flag"]
    write_csv(out_dir / "cleaned_matches.csv", cleaned, cleaned_fields)
    write_csv(out_dir / "cleaning_log.csv", cleaning_log)
    write_csv(out_dir / "match_prefix_audit.csv", prefix_audit)

    rankings = []
    for team in sorted(metrics, key=lambda t: metrics[t]["overall_rank"]):
        m = metrics[team]
        strengths, weaknesses = strength_weakness_text(m)
        rankings.append({
            "rank": m["overall_rank"], "team_id": team, "overall_score": round(m["overall_score"], 2),
            "avg_total_actions": round(m["avg_total_actions"], 2), "avg_cycle_sec": round(m["avg_cycle"], 2) if m["avg_cycle"] is not None else "",
            "auto_rate": round(m["auto_rate"], 3), "motif_rate": round(m["motif_rate"], 3),
            "avg_penalty": round(m["avg_penalty"], 2), "breakdown_rate": round(m["breakdown_rate"], 3),
            "avg_defense": round(m["avg_defense"], 2), "avg_driver": round(m["avg_driver"], 2),
            "reliability": reliability_category(m["reliability_index"]), "reliability_index": round(m["reliability_index"], 2),
            "major_strengths": strengths, "major_weaknesses": weaknesses,
            "archetype": archetype(team, m, pcts), "confidence": m["confidence"],
            "rank_sensitivity": f"{m['rank_min']}-{m['rank_max']}",
        })
    write_csv(out_dir / "team_rankings.csv", rankings)

    metric_rows = []
    for team in sorted(metrics):
        row = dict(metrics[team])
        row["archetype"] = archetype(team, metrics[team], pcts)
        for key, value in list(row.items()):
            if isinstance(value, float):
                row[key] = round(value, 4)
        metric_rows.append(row)
    write_csv(out_dir / "team_metrics.csv", metric_rows)
    write_csv(out_dir / "rank_sensitivity.csv", sensitivity)
    write_csv(out_dir / "compatibility_ranking_3470.csv", compatibility)

    picklist = []
    for row in compatibility:
        picklist.append({
            "pick_order": row["compatibility_rank"],
            "team_id": row["team_id"],
            "compatibility_score": round(row["compatibility_score"], 2),
            "reason": row["fit_reason"],
            "major_risk": row["major_risk"],
            "confidence": row["confidence"],
            "avoid_flag": row["avoid_flag"],
        })
    write_csv(out_dir / "alliance_picklist.csv", picklist)

    reliability_rows = []
    for team in sorted(metrics, key=lambda t: metrics[t]["reliability_index"], reverse=True):
        m = metrics[team]
        tags = []
        if m["action_floor_q25"] >= 11 and m["breakdown_rate"] == 0:
            tags.append("high-floor")
        if m["action_ceiling_max"] >= 15 and (m["breakdown_rate"] >= 0.17 or m["avg_penalty"] >= 6):
            tags.append("high-ceiling/high-risk")
        if m["breakdown_rate"] >= 0.33:
            tags.append("breakdown-risk")
        if m["avg_penalty"] >= 6:
            tags.append("penalty-risk")
        reliability_rows.append({
            "team_id": team, "reliability_rank": len(reliability_rows) + 1,
            "reliability_index": round(m["reliability_index"], 2), "reliability_band": reliability_category(m["reliability_index"]),
            "action_floor_q25": round(m["action_floor_q25"], 2), "action_ceiling_max": m["action_ceiling_max"],
            "action_cv": round(m["total_action_cv"], 3), "cycle_cv": round(m["cycle_cv"], 3) if m["cycle_cv"] is not None else "",
            "breakdown_rate": round(m["breakdown_rate"], 3), "avg_penalty": round(m["avg_penalty"], 2),
            "avg_driver_consistency": round(m["avg_driver"], 2), "risk_tags": "; ".join(tags) or "none",
        })
    write_csv(out_dir / "reliability_risk.csv", reliability_rows)

    archetype_rows = [
        {"team_id": team, "archetype": archetype(team, metrics[team], pcts)}
        for team in sorted(metrics, key=lambda t: metrics[t]["overall_rank"])
    ]
    write_csv(out_dir / "team_archetypes.csv", archetype_rows)

    underrated = []
    for team in sorted(metrics, key=lambda t: metrics[t]["result_vs_underlying_delta"], reverse=True):
        m = metrics[team]
        delta = m["result_vs_underlying_delta"]
        label = "Underrated by alliance results" if delta >= 3 else "Overrated by alliance results" if delta <= -3 else "Roughly aligned"
        underrated.append({
            "team_id": team, "overall_robot_rank": m["overall_rank"], "result_context_rank": m["context_rank"],
            "rank_difference": delta, "interpretation": label,
            "note": "Provisional: result context uses win rate/alliance score, but M## match prefixes have inconsistent same-color scorelines; verify match keys with event records.",
        })
    write_csv(out_dir / "overrated_underrated.csv", underrated)

    # Scout bias summary: a diagnostic, not proof of bias.
    scout_rows = []
    for scout in sorted({r["scout_id"] for r in cleaned}):
        rr = [r for r in cleaned if r["scout_id"] == scout]
        scout_rows.append({
            "scout_id": scout, "observations": len(rr),
            "avg_defense_rating": round(mean_valid(rr, "defense_rating"), 2),
            "avg_driver_consistency": round(mean_valid(rr, "driver_consistency"), 2),
            "avg_scout_confidence": round(mean_valid(rr, "scout_confidence"), 2),
            "avg_cycle_time_sec": round(mean_valid(rr, "cycle_time_sec"), 2),
        })
    write_csv(out_dir / "scout_bias_summary.csv", scout_rows)

    m3470 = metrics["3470"]
    rr3470 = sorted(by_team["3470"], key=lambda r: r["match_number"])
    first2_cycle = statistics.mean([r["cycle_time_sec"] for r in rr3470[:2]])
    last2_cycle = statistics.mean([r["cycle_time_sec"] for r in rr3470[-2:]])
    slow_pct = (last2_cycle / first2_cycle - 1) * 100
    overflow_note_count = sum(r["qualitative_note"] == "overflow mechanism slows late event" for r in rr3470)

    recommendations = [
        {
            "priority": 1,
            "problem": "Late-event cycle slowdown around the overflow mechanism/intake path",
            "supporting_evidence": f"Cycle time rose from {first2_cycle:.2f}s over matches 1-2 to {last2_cycle:.2f}s over matches 5-6 (+{slow_pct:.1f}%); the note 'overflow mechanism slows late event' appears {overflow_note_count}/6 times.",
            "expected_competitive_impact": "Higher late-match throughput and less performance fade while preserving 3470's strong early speed.",
            "recommended_action": "Stress-test the overflow/intake/transfer path under full-match conditions; log jam/retry causes; simplify or reinforce the mechanism; add driver recovery practice.",
            "confidence": "High",
        },
        {
            "priority": 2,
            "problem": "Fast cycles are not translating into top-tier total scoring volume",
            "supporting_evidence": f"3470's cycle-speed index is {ordinal(m3470['speed_index'])} percentile, but scoring-volume index is only {ordinal(m3470['action_index'])} percentile; CL is {ordinal(pcts['avg_cl']['3470'])} percentile and depot is {ordinal(pcts['avg_depot']['3470'])} percentile.",
            "expected_competitive_impact": "More scoring actions per match without needing a faster drivetrain or riskier strategy.",
            "recommended_action": "Run timed intake-to-score conversion drills, standardize driver routes, reduce dead travel/aim time, and prioritize CL/depot throughput where 3470 trails the field.",
            "confidence": "Medium",
        },
        {
            "priority": 3,
            "problem": "Motif completion is only 50% despite perfect autonomous leave",
            "supporting_evidence": "Auto leave succeeded in 6/6 observations, while motif completion succeeded in 3/6.",
            "expected_competitive_impact": "Raises objective reliability while keeping the already-stable autonomous foundation.",
            "recommended_action": "Add pre-match sensor/pose checks, deterministic autonomous state handling, and repeated motif-specific validation under different starting conditions.",
            "confidence": "High",
        },
        {
            "priority": 4,
            "problem": "Penalty spikes can erase gains in close matches",
            "supporting_evidence": f"3470 averaged {m3470['avg_penalty']:.1f} penalty points with a maximum of {m3470['max_penalty']}; two observations were 6+ points.",
            "expected_competitive_impact": "Improves floor in close matches and reduces avoidable score swings.",
            "recommended_action": "Review the high-penalty matches with the drive team, identify repeatable causes, and add rule-boundary drills to practice sessions.",
            "confidence": "Medium",
        },
    ]
    write_csv(out_dir / "recommendations_3470.csv", recommendations)

    uncertainties = [
        {
            "claim": "The M## prefix is a unique official event match identifier, making alliance scorelines independently verifiable.",
            "confidence": "Low",
            "competing_explanation": f"All {conflicting_prefixes} repeated prefixes have conflicting scores for the same alliance color; prefixes could be reused labels rather than event match IDs, or match context may be misrecorded.",
            "missing_information": "An official match schedule, stable match ID definitions, and verified per-match alliance scores and partners.",
            "decision": "Do not join rows by M## or make definitive claims from result-context rankings. Keep per-robot metrics and regard overrated/underrated as provisional.",
        },
        {
            "claim": "T05 is a top-3 robot in the balanced overall ranking.",
            "confidence": "Medium",
            "competing_explanation": "One CL value of 28 may be a logging error rather than a true performance spike; scout confidence on that row is 2/5.",
            "missing_information": "Video or a second scout record for M14-T05-3; official per-match scoring breakdown.",
            "decision": "Act on T05 as a strong option, but do not let the 28-CL row drive the picklist. The composite excludes that CL value.",
        },
        {
            "claim": "T12 is one of the fastest robots in the field.",
            "confidence": "Low",
            "competing_explanation": "Two of six cycle times are missing and one recorded cycle is an extreme 7.5 s outlier.",
            "missing_information": "Complete cycle timestamps or video-based timing for all six matches.",
            "decision": "Treat T12 speed as promising but unconfirmed; do not select them primarily for speed.",
        },
        {
            "claim": "Alliance win rate is a good proxy for individual robot strength.",
            "confidence": "Low",
            "competing_explanation": "Alliance scores include partner performance and opponent strength; T11 has good result context but ranks last on underlying robot metrics.",
            "missing_information": "Alliance partner identities, opponent strength, individual contribution, and schedule strength.",
            "decision": "Do not use wins/alliance score inside the robot-strength composite; use them only as context.",
        },
        {
            "claim": "Defense ratings are directly comparable across scouts.",
            "confidence": "Medium",
            "competing_explanation": "Scout mean defense ratings vary by about half a rating point, which may reflect rater calibration rather than robot ability.",
            "missing_information": "Multiple scouts on the same matches or a calibrated defense-rating rubric.",
            "decision": "Use defense as a supporting signal, not a precise standalone ranking metric.",
        },
        {
            "claim": "3470's late slowdown is caused by the overflow mechanism.",
            "confidence": "Medium",
            "competing_explanation": "The repeated note supports the hypothesis, but defense, battery state, traffic, or match strategy could also slow cycles.",
            "missing_information": "Subsystem telemetry, match video, battery voltage, and timestamps of retries/jams.",
            "decision": "Prioritize testing the overflow path because it is the best-supported actionable hypothesis, but validate before redesigning.",
        },
    ]
    write_csv(out_dir / "ambiguity_uncertainty.csv", uncertainties)

    strategies = [
        {
            "matchup": 1,
            "our_alliance": "3470 + T08",
            "opposing_alliance": "T07 + T06",
            "primary_win_condition": "Use 3470's speed/consistency plus T08's high-volume two-way play to match the opponents' scoring ceiling without giving away penalties.",
            "recommended_alliance_roles": "3470: fast repeatable scorer and stable objective execution. T08: primary volume scorer and defensive pressure when safe.",
            "biggest_opponent_threat": "T07/T06 combine very high scoring volume; T07 also has a 17-action ceiling.",
            "strategic_priority": "Build an early clean lead, avoid traffic, and force the opponent's higher-risk robots to beat a stable score.",
            "major_risk": "T08's driver consistency/penalties and 3470's late-cycle slowdown.",
            "backup_plan": "If T08 execution drops, keep 3470 on offense and reduce risky defense; shift to reliable scoring rather than chase ceiling plays.",
            "confidence": "Medium",
        },
        {
            "matchup": 2,
            "our_alliance": "3470 + T14",
            "opposing_alliance": "T17 + T02",
            "primary_win_condition": "Win on speed and complementary CL/depot production while keeping the match low-penalty.",
            "recommended_alliance_roles": "3470: fast cycling/overflow support. T14: efficient primary CL/depot scorer with secondary defense.",
            "biggest_opponent_threat": "T17's strong driver-led scoring paired with T02's top reliability.",
            "strategic_priority": "Protect clean lanes and make T17/T02 spend time reacting rather than running their consistent plan.",
            "major_risk": "T14's rank is weight-sensitive and 3470 can fade late.",
            "backup_plan": "If scoring lanes clog, use T14's stronger defense while 3470 stays on the shortest repeatable scoring route.",
            "confidence": "Medium",
        },
        {
            "matchup": 3,
            "our_alliance": "3470 + T02",
            "opposing_alliance": "T08 + T05",
            "primary_win_condition": "Turn the match into a reliability contest: clean execution, controlled defense, and no penalty spikes.",
            "recommended_alliance_roles": "3470: primary pace setter and scorer. T02: reliable balanced support/defense and motif coverage.",
            "biggest_opponent_threat": "T08 is the strongest overall robot and T05 adds high scoring volume.",
            "strategic_priority": "Disrupt T08's two-way impact without sacrificing 3470's cycles; exploit T05's lower driver consistency and penalty risk.",
            "major_risk": "Our alliance has less raw scoring ceiling than T08 + T05.",
            "backup_plan": "Prioritize objectives and safe high-floor scoring; avoid a chaotic shootout if the early margin is close.",
            "confidence": "Medium-Low",
        },
    ]
    write_csv(out_dir / "match_strategy_examples.csv", strategies)

    strategy_conclusions = [
        {"conclusion": "Preserve the opening-speed advantage.", "evidence": "3470 is 88th percentile in cycle speed and 6/6 on auto leave.", "confidence": "High"},
        {"conclusion": "Do not rely on late-match overflow throughput without a backup route.", "evidence": "Cycle time slows across the six matches and the same overflow-slowdown note appears three times.", "confidence": "Medium-High"},
        {"conclusion": "Prefer partners that add CL/depot scoring and defense.", "evidence": "3470 is only 41st percentile in CL, 35th in depot, and 41st in defense, while its speed/reliability are stronger.", "confidence": "Medium"},
        {"conclusion": "Against high-risk/high-ceiling opponents, favor clean high-floor play.", "evidence": "Several top-volume teams (especially T07) carry meaningful breakdown risk; 3470 itself has zero recorded breakdowns.", "confidence": "Medium"},
    ]
    write_csv(out_dir / "match_strategy_conclusions.csv", strategy_conclusions)

    # Dataset quality summary.
    quality_summary = [
        {"check": "Raw observations", "result": len(raw_rows), "interpretation": "Before cleaning."},
        {"check": "Analysis-ready observations", "result": len(cleaned), "interpretation": "One exact duplicate removed."},
        {"check": "Teams", "result": len(metrics), "interpretation": "3470 plus 17 anonymized teams."},
        {"check": "Missing cycle_time_sec", "result": sum(r["cycle_time_sec"] is None for r in cleaned), "interpretation": "Both are T12; no imputation used."},
        {"check": "Missing qualitative_note", "result": sum(r["qualitative_note"] is None for r in cleaned), "interpretation": "Notes are optional qualitative evidence; numeric metrics retained."},
        {"check": "Result/score conflicts", "result": sum("result_score_conflict" in r["data_quality_flag"] for r in cleaned), "interpretation": "No W/L records conflict with final scores."},
        {"check": "Extreme low-confidence CL rows excluded from CL aggregates", "result": sum(r["analysis_excluded_from_cl"] for r in cleaned), "interpretation": "T05 M14-T05-3 only."},
        {"check": "Ambiguous M## prefixes with conflicting same-alliance scores", "result": f"{conflicting_prefixes}/{len(prefix_audit)}", "interpretation": "Match-prefix semantics are uncertain; context-based overrated/underrated conclusions are provisional, not verified event results."},
        {"check": "Prefixes with >2 observations on one color", "result": triple_prefixes, "interpretation": "Cannot safely treat M## as an official event match number; do not use for alliance joining."},
        {"check": "Per-team sample size", "result": "6 matches/team", "interpretation": "Small sample size limits certainty and makes rank sensitivity important."},
    ]
    write_csv(out_dir / "data_quality_summary.csv", quality_summary)

    summary = {
        "raw_rows": len(raw_rows),
        "clean_rows": len(cleaned),
        "teams": len(metrics),
        "ambiguous_match_prefix_groups": conflicting_prefixes,
        "match_prefix_groups_total": len(prefix_audit),
        "overall_top5": [t for t in sorted(metrics, key=lambda t: metrics[t]["overall_rank"])[:5]],
        "team_3470_overall_rank": metrics["3470"]["overall_rank"],
        "team_3470_overall_score": round(metrics["3470"]["overall_score"], 2),
        "team_3470_best_partners": [r["team_id"] for r in compatibility[:5]],
        "most_reliable": [t for t in sorted(metrics, key=lambda t: metrics[t]["reliability_index"], reverse=True)[:5]],
        "figures": make_figures(fig_dir, metrics, compatibility, pcts, by_team),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
