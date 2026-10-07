"""Sandboxed execution of proof scripts.

Safety: AST import whitelist + subprocess with timeout + no shell.
Determinism: run twice, the ANSWER line must be byte-identical.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ALLOWED_IMPORTS = {
    "pandas", "numpy", "datetime", "calendar", "re", "math", "json",
    "statistics", "itertools", "functools", "collections", "pathlib",
    "csv", "decimal", "typing",
}
FORBIDDEN_ROOTS = {
    "socket", "requests", "urllib", "http", "subprocess", "os", "sys",
    "shutil", "pickle", "importlib", "webbrowser", "smtplib", "ftplib",
}

ANSWER_RE = re.compile(r"^ANSWER:\s*(?P<val>.+)$", re.MULTILINE)
EVIDENCE_RE = re.compile(r"^EVIDENCE:\s*(?P<val>\{.*\})$", re.MULTILINE)


class SandboxError(Exception):
    pass


def check_imports(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SandboxError(f"syntax error: {exc}") from exc
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods = [node.module.split(".")[0]]
        for m in mods:
            if m in FORBIDDEN_ROOTS:
                raise SandboxError(f"forbidden import: {m}")
            if m not in ALLOWED_IMPORTS:
                raise SandboxError(f"import not on whitelist: {m}")


@dataclass
class RunResult:
    answer: object
    evidence: dict
    stdout: str = ""
    stderr: str = ""
    runs: int = 2

    @property
    def answer_json(self) -> str:
        return json.dumps(self.answer)


def execute(code_path: Path, timeout: int = 60) -> RunResult:
    """Run a proof script twice in a fresh subprocess; answers must match."""
    code_path = Path(code_path)
    if not code_path.is_absolute():
        code_path = ROOT / code_path
    code = code_path.read_text(encoding="utf-8")
    check_imports(code)

    outputs = []
    for _ in range(2):
        try:
            proc = subprocess.run(
                [sys.executable, str(code_path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"timeout after {timeout}s") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise SandboxError(f"exit code {proc.returncode}: {tail}")
        outputs.append(proc.stdout)

    if outputs[0] != outputs[1]:
        raise SandboxError("non-deterministic: two runs produced different output")

    m = ANSWER_RE.search(outputs[0])
    if not m:
        raise SandboxError("no ANSWER: line in output")
    raw = m.group("val").strip()
    try:
        answer = json.loads(raw)
    except json.JSONDecodeError:
        answer = raw

    evidence = {}
    ev = EVIDENCE_RE.search(outputs[0])
    if ev:
        try:
            evidence = json.loads(ev.group("val"))
        except json.JSONDecodeError:
            evidence = {}

    return RunResult(answer=answer, evidence=evidence, stdout=outputs[0])


def values_match(claimed: object, actual: object, tol: float = 0.01) -> bool:
    if isinstance(claimed, bool) or isinstance(actual, bool):
        return claimed == actual
    if isinstance(claimed, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(claimed) - float(actual)) <= max(tol, tol * abs(float(claimed)))
    return str(claimed) == str(actual)
