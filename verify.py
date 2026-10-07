"""Judge-facing verifier.

Runs every proof script in answers/ twice in a sandbox and checks the
reproduced number matches the agent's claimed answer.

    python verify.py

Exit code 0 = every claim reproduced. Non-zero = at least one failed.
This is the "someone else can run the code" check from the problem rules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.sandbox import SandboxError, execute, values_match  # noqa: E402

ANSWERS = ROOT / "answers"

GREEN, RED, YELLOW, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def main() -> int:
    claims = sorted(ANSWERS.glob("*.json"))
    if not claims:
        print("No claims in answers/ - run the agent first.")
        return 1

    passed = failed = refusals = 0
    print(f"{'ID':<6} {'TYPE':<9} {'RESULT':<8} DETAIL")
    print("-" * 78)

    for claim_path in claims:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        qid = claim.get("id", claim_path.stem)
        if not claim.get("answerable", True):
            refusals += 1
            ok = claim.get("answerable") is False and claim.get("refusal_reason")
            tag = f"{GREEN}REFUSED{RESET}" if ok else f"{RED}BAD{RESET}"
            print(f"{qid:<6} {'refusal':<9} {tag:<18} {claim.get('refusal_category', '')}")
            if not ok:
                failed += 1
            else:
                passed += 1
            continue

        code_file = claim.get("code_file")
        if not code_file or not (ROOT / code_file).exists():
            failed += 1
            print(f"{qid:<6} {'answer':<9} {RED}NO CODE{RESET:<18} proof script missing")
            continue

        try:
            result = execute(ROOT / code_file)
        except SandboxError as exc:
            failed += 1
            print(f"{qid:<6} {'answer':<9} {RED}ERROR{RESET:<18} {exc}")
            continue

        if values_match(claim.get("answer"), result.answer):
            passed += 1
            print(f"{qid:<6} {'answer':<9} {GREEN}PASS{RESET:<18} "
                  f"{result.answer_json} == claimed {json.dumps(claim.get('answer'))}")
        else:
            failed += 1
            print(f"{qid:<6} {'answer':<9} {RED}MISMATCH{RESET:<18} "
                  f"code={result.answer_json} claimed={json.dumps(claim.get('answer'))}")

    print("-" * 78)
    total = passed + failed
    print(f"TOTAL {GREEN}{passed}{RESET}/{total} reproduced  "
          f"({refusals} refusal claims checked)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
