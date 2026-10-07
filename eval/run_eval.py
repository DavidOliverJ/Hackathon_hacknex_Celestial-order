"""Scoring harness mapped to the HackNex judging criteria.

    python eval/run_eval.py            # scores using answers/ claims
    AGENT_MODE=record python eval/run_eval.py   # runs the agent first, recording LLM calls

Scoring (100 pts per question):
  answer     55 correct + 25 proof reproduces + 20 evidence quality
  refuse     60 right category (+40 near-miss) + 25 reason quality + 15 specificity
  ambiguous  40 ambiguity flagged + 40 correct under stated assumption + 20 proof
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.sandbox import SandboxError, execute, values_match  # noqa: E402

ANSWERS = ROOT / "answers"
GOLD = json.loads((ROOT / "data" / "gold.json").read_text(encoding="utf-8"))
QUESTIONS = yaml.safe_load(
    (ROOT / "eval" / "questions.yaml").read_text(encoding="utf-8")
)["questions"]

RELATED = {
    "no_data": {"missing_column", "unit_mismatch"},
    "missing_column": {"no_data", "unit_mismatch"},
    "unit_mismatch": {"missing_column", "no_data"},
    "contradiction": set(),
}
# a specific reason names an artifact: a file, a date, a quoted token, or a
# data element (column/table/rows/rate/region/...)
ARTIFACT_RE = re.compile(
    r"\.csv|\b20\d{2}\b|\d{4}-\d{2}-\d{2}|['\"`]"
    r"|\b(column|table|row|rows|rate|rates|span|region|currency|unit|field"
    r"|products?|sales|catalog|transactions|customers?)\b",
    re.I,
)
REASON_KEYWORDS = {
    "no_data": ["2023", "no rows", "no data", "empty", "not in", "outside", "range", "span", "never"],
    "missing_column": ["column", "does not exist", "not exist", "absent", "no such", "profit", "cost", "no field", "no column"],
    "unit_mismatch": ["rate", "currency", "fx", "jpy", "yen", "exchange", "convert", "no rate", "missing rate"],
    "contradiction": ["conflict", "contradict", "disagree", "inconsistent", "both",
                      "two table", "differ", "clash", "tie-breaker", "tiebreaker",
                      "whereas", "while", "no way", "cannot", "adjudicat", "either"],
}


def norm_str(v) -> str:
    return str(v).strip().lower()


def match_answer(claimed, gold, tol) -> bool:
    if isinstance(gold, str):
        return norm_str(claimed) == norm_str(gold)
    return values_match(gold, claimed, tol=tol)


def load_claims() -> dict:
    claims = {}
    for p in sorted(ANSWERS.glob("*.json")):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "id" in c:
            claims[str(c["id"]).upper()] = c
    return claims


def reproducibility(claim: dict) -> tuple[bool, str]:
    code_file = claim.get("code_file")
    if not code_file or not (ROOT / code_file).exists():
        return False, "proof script missing"
    try:
        result = execute(ROOT / code_file)
    except SandboxError as exc:
        return False, f"error: {exc}"
    if not values_match(claim.get("answer"), result.answer):
        return False, f"output {result.answer_json} != claim {json.dumps(claim.get('answer'))}"
    return True, "ran twice, identical output"


def score_answer(q: dict, claim: dict | None) -> tuple[int, int, str]:
    if claim is None:
        return 0, 100, "no claim produced"
    if not claim.get("answerable", True):
        return 0, 100, f"refused ({claim.get('refusal_category')}) - question IS answerable"
    gold = GOLD[q["gold_key"]]
    pts = 0
    detail = []
    ok = match_answer(claim.get("answer"), gold, q.get("tol", 0.01))
    if ok:
        pts += 55
        detail.append(f"correct={claim.get('answer')}")
    else:
        detail.append(f"WRONG got={claim.get('answer')} want={gold}")
    repro, rdetail = reproducibility(claim)
    if repro:
        pts += 25
    detail.append("repro:ok" if repro else f"repro:FAIL({rdetail})")
    ev = claim.get("evidence") or {}
    ev_str = json.dumps(ev, ensure_ascii=False).lower()
    ev_pts = 0
    if ev:
        ev_pts += 10
    if "row" in ev_str:
        ev_pts += 5
    mess_pts = 0
    checks = {
        "dupes": "dup" in ev_str,
        "nulls": "null" in ev_str,
        "fx": any(k in ev_str for k in ["currency", "currencies", "usd", "rate", "convert", "fx"]),
        "dates": any(k in ev_str for k in ["date", "q3", "july", "2024-07", "range", "period", "month", "scope"]),
        "region": "region" in ev_str,
    }
    for tag in q.get("mess", []):
        if checks.get(tag):
            mess_pts += 5
    ev_pts = min(ev_pts + min(mess_pts, 10), 20)
    pts += ev_pts
    if mess_pts:
        detail.append(f"mess-aware={min(mess_pts, 10)}/10")
    mx = 100 if q.get("mess") else 95
    return pts, mx, "; ".join(detail)


def score_refuse(q: dict, claim: dict | None) -> tuple[int, int, str]:
    if claim is None:
        return 0, 100, "no claim produced"
    if claim.get("answerable", True):
        return 0, 100, f"ANSWERED ({json.dumps(claim.get('answer'))}) - must refuse"
    got = str(claim.get("refusal_category") or "").strip()
    want = q["gold_category"]
    pts, detail = 0, []
    if got == want:
        pts += 60
        detail.append(f"category={got}")
    elif got in RELATED.get(want, set()):
        pts += 40
        detail.append(f"near-miss category={got} (want {want})")
    else:
        detail.append(f"WRONG category={got} want={want}")
    reason = str(claim.get("refusal_reason") or "").strip()
    if reason:
        pts += 10
    low = reason.lower()
    if any(k in low for k in REASON_KEYWORDS[want]):
        pts += 15
        detail.append("reason cites evidence")
    elif reason:
        detail.append("reason too vague")
    else:
        detail.append("no reason given")
    if len(reason) >= 60 and ARTIFACT_RE.search(reason):
        pts += 15
        detail.append("reason names concrete artifacts")
    elif reason:
        detail.append("reason lacks specifics")
    return pts, 100, "; ".join(detail)


def score_ambiguous(q: dict, claim: dict | None) -> tuple[int, int, str]:
    if claim is None:
        return 0, 100, "no claim produced"
    flags = json.dumps(claim.get("ambiguities") or [], ensure_ascii=False).lower()
    reason = str(claim.get("refusal_reason") or "").lower()
    keywords = q["flag_keywords"]
    flag_text = flags + " " + reason
    pts, detail = 0, []
    if any(k in flag_text for k in keywords):
        pts += 40
        detail.append("ambiguity flagged")
    elif claim.get("ambiguities"):
        pts += 15
        detail.append("flagged wrong aspect")
    else:
        detail.append("MISSED ambiguity")

    answered = claim.get("answerable", True) and claim.get("answer") is not None
    if answered:
        hits = [
            name
            for name, key in q["interpretations"].items()
            if match_answer(claim.get("answer"), GOLD[key], q.get("tol", 0.01))
        ]
        if hits:
            pts += 40
            detail.append(f"matches interpretation {hits[0]}")
        else:
            detail.append(f"wrong value {claim.get('answer')}")
        repro, rdetail = reproducibility(claim)
        if repro:
            pts += 20
        else:
            detail.append(f"repro:FAIL({rdetail})")
    else:
        pts += 15
        detail.append("declined after flagging")
    return pts, 100, "; ".join(detail)


SCORERS = {"answer": score_answer, "refuse": score_refuse, "ambiguous": score_ambiguous}


def main() -> int:
    run_agent = os.environ.get("RUN_AGENT", "").strip() in {"1", "true", "yes"}
    if run_agent:
        from agent.pipeline import run
        from agent.profile import build_profile

        profile = build_profile()
        for q in QUESTIONS:
            print(f"[agent] {q['id']} ...", flush=True)
            run(q["question"], qid=q["id"], profile=profile)

    claims = load_claims()
    total = max_total = 0
    stats = {"answer": [0, 0], "refuse": [0, 0], "ambiguous": [0, 0]}
    repro_ok = repro_total = 0

    print(f"\n{'ID':<4} {'TYPE':<10} {'PTS':>7}  DETAIL")
    print("-" * 96)
    for q in QUESTIONS:
        claim = claims.get(q["id"].upper())
        scorer = SCORERS[q["type"]]
        pts, mx, detail = scorer(q, claim)
        total += pts
        max_total += mx
        stats[q["type"]][0] += pts
        stats[q["type"]][1] += mx
        if q["type"] in ("answer", "ambiguous") and claim and claim.get("answerable", True):
            repro_total += 1
            ok, _ = reproducibility(claim)
            repro_ok += int(ok)
        flag = "" if pts >= 85 else ("  <<<" if pts < 60 else "  <")
        print(f"{q['id']:<4} {q['type']:<10} {pts:>4}/{mx}  {detail}{flag}")

    score = 100.0 * total / max_total
    print("-" * 96)
    for t, (p, m) in stats.items():
        print(f"  {t:<10} {p:>4}/{m}  ({100 * p / m:.0f}%)")
    if repro_total:
        print(f"  proof reproducibility: {repro_ok}/{repro_total}")
    print(f"\n  OVERALL SCORE: {score:.1f}/100   (target >= 85)")

    (ROOT / "eval" / "last_score.json").write_text(
        json.dumps(
            {
                "score": round(score, 1),
                "points": total,
                "max": max_total,
                "per_type": {t: p for t, (p, _) in stats.items()},
                "reproducibility": f"{repro_ok}/{repro_total}",
                "mode": os.environ.get("AGENT_MODE", "replay"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if score >= 85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
