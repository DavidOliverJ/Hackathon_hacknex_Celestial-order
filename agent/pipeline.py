"""End-to-end orchestration: question -> verdict -> proof script -> verified answer."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import analyze, codegen, llm
from .profile import build_profile, profile_digest
from .sandbox import ROOT, SandboxError, check_imports, execute

ANSWERS_DIR = ROOT / "answers"


def _slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:limit]


def run(
    question: str,
    qid: str | None = None,
    profile: str | None = None,
    write_claim: bool = True,
) -> dict:
    t0 = time.time()
    profile = profile if profile is not None else build_profile()
    qid = qid or _slug(question)
    result: dict = {
        "id": qid,
        "question": question,
        "mode": llm.mode(),
        "model": llm.model_name(),
        "answerable": True,
        "answer": None,
        "code": None,
        "code_file": None,
        "evidence": {},
        "verified": False,
        "verify_detail": "",
        "refusal_category": None,
        "reason": "",
        "ambiguities": [],
        "traps": [],
        "confidence": "medium",
        "repair_count": 0,
        "latency_s": 0.0,
    }

    verdict = analyze.analyze(question, profile)
    result["traps"] = verdict["traps"]
    result["ambiguities"] = verdict["ambiguities"]
    result["confidence"] = verdict["confidence"]

    if not verdict["answerable"]:
        result["answerable"] = False
        result["refusal_category"] = verdict["refusal_category"]
        result["reason"] = verdict["reason"]
        result["latency_s"] = round(time.time() - t0, 2)
        if write_claim:
            _write_claim(result)
        return result

    plan = verdict["plan"] or {"metric": verdict.get("reason", "as asked")}
    code = codegen.generate(question, profile, plan)

    # stage A: static checks, stage B: execution - repair up to 2 times.
    # A null/NaN answer counts as a failure worth repairing; only after the
    # repairs are exhausted does it degrade to an honest refusal.
    proof_path = ANSWERS_DIR / f"{qid}.py"
    ANSWERS_DIR.mkdir(exist_ok=True)
    empty_evidence: dict = {}
    last_error = ""
    for attempt in range(3):
        run_result = None
        try:
            check_imports(code)
            proof_path.write_text(code, encoding="utf-8")
            run_result = execute(proof_path)
            if not _is_empty_answer(run_result.answer):
                result["answer"] = run_result.answer
                result["evidence"] = run_result.evidence
                result["verified"] = True
                result["verify_detail"] = "ran twice in sandbox, outputs identical"
                break
            empty_evidence = run_result.evidence or {}
            last_error = (
                "your script printed a null/NaN answer. If the question is "
                "answerable, fix the scope or conversion and print a real "
                f"value. Script evidence: {json.dumps(empty_evidence, default=str)[:300]}"
            )
        except SandboxError as exc:
            last_error = str(exc)

        result["repair_count"] += 1
        if attempt == 2:
            if run_result is not None:
                _degrade_to_refusal(result, empty_evidence)
            else:
                result["answerable"] = False
                result["refusal_category"] = "execution_failure"
                result["reason"] = f"could not produce a working proof: {last_error}"
            break
        code = codegen.repair(question, profile, plan, code, last_error)

    result["code"] = code
    result["latency_s"] = round(time.time() - t0, 2)

    if result["verified"]:
        result["code_file"] = f"answers/{qid}.py"
        if write_claim:
            _write_claim(result)
        return result

    if write_claim:
        _write_claim(result)
    return result


def _degrade_to_refusal(result: dict, evidence: dict) -> None:
    """Null answer after repairs exhausted -> honest refusal, never 'None'."""
    ev = evidence or {}
    unconvertible = (
        ev.get("rows_missing_fx_rate") is not None
        and ev.get("rows_in_scope") is not None
        and ev["rows_missing_fx_rate"] >= ev["rows_in_scope"]
        and ev["rows_in_scope"] > 0
    ) or bool(ev.get("scope_empty") is False and ev.get("rows_missing_fx_rate"))
    result["verified"] = False
    result["answerable"] = False
    result["refusal_category"] = "unit_mismatch" if unconvertible else "no_data"
    result["evidence"] = ev
    result["reason"] = (
        "fx_rates.csv has no rate for the in-scope rows, so they cannot be "
        f"converted to USD (evidence: {json.dumps(ev, default=str)[:200]})"
        if unconvertible
        else "the computation's row scope is empty - no rows in the data match "
        f"the question's filters (evidence: {json.dumps(ev, default=str)[:200]})"
    )
    result["answer"] = None


def _is_empty_answer(value) -> bool:
    if value is None or value == "None":
        return True
    if isinstance(value, float) and value != value:  # NaN
        return True
    if isinstance(value, str) and value.strip().lower() in ("none", "null", "nan", ""):
        return True
    if isinstance(value, dict) and value.get("scope_empty"):
        return True
    return False


def _write_claim(result: dict) -> None:
    ANSWERS_DIR.mkdir(exist_ok=True)
    if result["code"]:
        (ANSWERS_DIR / f"{result['id']}.py").write_text(result["code"], encoding="utf-8")
    claim = {
        "id": result["id"],
        "question": result["question"],
        "answerable": result["answerable"],
        "answer": result["answer"],
        "code_file": result["code_file"],
        "refusal_category": result["refusal_category"],
        "refusal_reason": result["reason"],
        "ambiguities": result["ambiguities"],
        "traps": result["traps"],
        "evidence": result["evidence"],
        "confidence": result["confidence"],
        "generated_by": f"{result['model']} ({result['mode']})",
    }
    (ANSWERS_DIR / f"{result['id']}.json").write_text(
        json.dumps(claim, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def main() -> None:
    import sys

    q = " ".join(sys.argv[1:]) or "How many rows are in the sales transactions table?"
    res = run(q)
    print(json.dumps({k: v for k, v in res.items() if k != "code"}, indent=2, default=str))
    if res["code"]:
        print("\n--- proof script ---\n" + res["code"])


if __name__ == "__main__":
    main()
