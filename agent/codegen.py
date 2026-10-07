"""Stage 2: turn an approved plan into a re-runnable pandas proof script."""
from __future__ import annotations

import json
import re

from . import llm

SYSTEM = """You are the CODEGEN stage of a proof-carrying data analyst agent.
You receive a dataset profile, a user question and an approved plan. You write
ONE self-contained pandas script that computes the answer. Someone else must be
able to run your script and get the same number, so it must be deterministic
and complete - no placeholders, no TODOs, no pseudocode.

HARD OUTPUT CONTRACT
  - Reply with exactly ONE ```python fenced code block and nothing else.
  - The script must print exactly these two lines and may print nothing else:
      ANSWER: <JSON scalar>      e.g. ANSWER: 421.42   or   ANSWER: "North America"
      EVIDENCE: {"rows_used": 123, ...}
  - ANSWER must be a bare JSON number or JSON string (json.dumps of the value).
  - EVIDENCE must be a JSON object describing what the number rests on:
    rows_raw, rows_deduped, duplicate_rows_removed, nulls_skipped, rows_in_scope,
    currencies_converted, rows_missing_fx_rate - include whichever apply.
    For non-numeric answers (best region/category) still report row counts.

RULES
  - Allowed imports: pandas, numpy, datetime, calendar, re, math, json,
    statistics, itertools, functools, collections, pathlib, csv, decimal.
    NOTHING else (no os, sys, subprocess, requests).
  - Read CSVs with repo-relative paths: data/raw/<file>.csv
  - Deterministic only: no random sampling without a fixed seed, no
    time.now(), no network.
  - Dates in sales_transactions.csv come in THREE formats:
      2024-07-12  (ISO)        Jul 12, 2024 (text)      12/07/2024 (legacy)
    Parse them with this helper - legacy slash rows always have day in 13..28,
    so DD/MM/YYYY is the only possible reading:
        def parse_date(s):
            s = str(s)
            if "/" in s:
                d, m, y = s.split("/")
                return date(int(y), int(m), int(d))
            return pd.to_datetime(s).date()
    Never rely on pd.to_datetime alone - it misparses mixed formats.
  - Duplicates: sales_transactions.csv contains exact duplicate rows from an
    ETL double-run. Any metric that counts or aggregates rows must start with
    df = df.drop_duplicates(). Only skip this when the question explicitly
    asks about raw rows.
  - Missing values: pd.to_numeric(..., errors="coerce") then drop rows whose
    amount is null for amount-based metrics; count how many you dropped.
  - Currency: amounts are in the row's `currency` (USD/EUR/INR) and must be
    converted to the requested currency using fx_rates.csv daily rates
    (column rate_to_usd = USD per 1 unit). Join on (date, currency). If a rate
    is missing for a row, that row cannot be converted - report
    rows_missing_fx_rate in EVIDENCE. Negative amounts are returns and stay in.
  - Never mix currencies without converting. Never sum a column whose unit is
    ambiguous without stating the unit in EVIDENCE.
  - Column named `dt` breaks pandas accessors - use `order_dt` instead.
  - Safety valve (use ONLY when the result is truly undefined): if the filtered
    scope is EMPTY, or if EVERY in-scope row fails currency conversion because
    fx_rates.csv has no rate for their date, do not invent a value and do not
    report 0 for an aggregate - print `ANSWER: null` and put `scope_empty: true`
    (or `rows_missing_fx_rate` + `rows_in_scope`) in EVIDENCE.
    If only SOME rows lack rates, compute over the convertible rows and report
    `rows_missing_fx_rate` in EVIDENCE - that is a disclosed partial coverage,
    not a null result.
  - Keep the script under ~80 lines.

EXAMPLE OF THE REQUIRED STYLE (different metric, shows conventions):
```python
import json
from datetime import date

import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")
df = df.drop_duplicates()

def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
null_amounts = int(df["amount"].isna().sum())
df = df[df["amount"].notna()].copy()

rates = {(str(r.date), r.currency): float(r.rate_to_usd) for r in fx.itertuples()}
def to_usd(row):
    if row.currency == "USD":
        return float(row.amount)
    rate = rates.get((str(row.order_dt), row.currency))
    return float(row.amount) * rate if rate is not None else None

df["usd"] = df.apply(to_usd, axis=1)
df = df[df["usd"].notna()].copy()
# ... compute the metric from df ...

value = 0.0  # replaced by the real computation
print(f"ANSWER: {json.dumps(value)}")
print("EVIDENCE: " + json.dumps({"rows_used": len(df), "nulls_skipped": null_amounts}))
```"""


def _user(question: str, profile: str, plan: dict) -> str:
    return (
        f"DATASET PROFILE:\n{profile}\n\n"
        f"USER QUESTION:\n{question}\n\n"
        f"APPROVED PLAN (from the planning stage):\n"
        f"{json.dumps(plan, indent=2, ensure_ascii=False)}"
    )


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    return text.strip()


def generate(question: str, profile: str, plan: dict) -> str:
    user = _user(question, profile, plan)
    code = extract_code(llm.chat(SYSTEM, user))
    return code


def repair(question: str, profile: str, plan: dict, code: str, error: str) -> str:
    user = (
        _user(question, profile, plan)
        + f"\n\nYOUR PREVIOUS SCRIPT FAILED:\n```python\n{code}\n```\n"
        + f"ERROR:\n{error}\n\n"
        "Fix it and reply with ONE complete ```python block only. "
        "Remember the ANSWER:/EVIDENCE: output contract."
    )
    return extract_code(llm.chat(SYSTEM, user))
