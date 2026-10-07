"""Dataset profile: the factual context handed to every LLM call."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

MAX_CELLS = 500  # truncate oversized samples


def _series_profile(s: pd.Series) -> dict:
    info: dict = {
        "dtype": str(s.dtype),
        "nulls": int(s.isna().sum()),
        "unique": int(s.nunique(dropna=True)),
    }
    non_null = s.dropna()
    if non_null.empty:
        return info
    if info["unique"] <= 15:
        info["values"] = sorted(str(v) for v in non_null.unique())
    else:
        info["sample"] = [str(v) for v in non_null.head(4)]
    return info


def build_profile() -> str:
    sections: list[str] = []
    for path in sorted(RAW.glob("*")):
        if path.suffix == ".txt":
            sections.append(f"### {path.name} (document)\n{path.read_text(encoding='utf-8')}")
            continue
        df = pd.read_csv(path)
        cols = {c: _series_profile(df[c]) for c in df.columns}
        head = df.head(3).to_dict(orient="records")
        # date-format hints + monthly row counts for the messy table
        extra = ""
        if "order_date" in df.columns:
            patterns = {
                "ISO (YYYY-MM-DD)": int(df.order_date.str.match(r"^\d{4}-\d{2}-\d{2}$").sum()),
                "Slash (DD/MM/YYYY)": int(df.order_date.str.match(r"^\d{2}/\d{2}/\d{4}$").sum()),
                "Text (Mon D, YYYY)": int(df.order_date.str.match(r"^[A-Za-z]{3} \d{1,2}, \d{4}$").sum()),
            }

            def _true_date(s: str) -> str:
                s = str(s)
                if "/" in s:
                    dd, mm, yy = s.split("/")
                    return f"{yy}-{int(mm):02d}"
                return str(pd.to_datetime(s).date())[:7]

            months = df.order_date.map(_true_date).value_counts().sort_index()
            slash_days = (
                df.order_date[df.order_date.str.contains("/", na=False)]
                .str.split("/").str[0].astype(int)
            )
            extra = (
                f"\ndate_format_counts: {patterns}\n"
                f"slash_dates_day_range: {int(slash_days.min())}..{int(slash_days.max())}\n"
                f"rows_by_month (parsed): {json.dumps(months.to_dict())}\n"
                f"DATE SPAN: {months.index.min()} .. {months.index.max()} "
                "- any scope outside this span has ZERO rows"
                if len(slash_days) else ""
            )
        # FX coverage: expose missing rate windows so refusals are evidence-based
        if {"date", "currency"} <= set(df.columns):
            union = sorted(df["date"].unique())
            gaps = []
            for cur in sorted(df["currency"].unique()):
                have = set(df.loc[df["currency"] == cur, "date"])
                missing = [d for d in union if d not in have]
                if missing:
                    gaps.append(
                        f"{cur}: MISSING rates for {len(missing)} dates "
                        f"({min(missing)}..{max(missing)})"
                    )
            extra += "\nfx_coverage: " + (
                "; ".join(gaps) if gaps else "complete for all currencies/dates"
            )
        sections.append(
            f"### {path.name}\nrows: {len(df)}\ncolumns:\n"
            + json.dumps(cols, indent=2, ensure_ascii=False)
            + f"\nfirst_rows: {json.dumps(head, default=str, ensure_ascii=False)}"
            + extra
        )
    return "\n\n".join(sections)


def profile_digest() -> str:
    """Compact one-line facts used in refusal-reasoning prompts."""
    sales = pd.read_csv(RAW / "sales_transactions.csv")
    fx = pd.read_csv(RAW / "fx_rates.csv")
    return json.dumps(
        {
            "sales_rows": len(sales),
            "sales_date_span": "2024-01-01..2024-09-30 (see formats in profile)",
            "currencies": sorted(sales.currency.dropna().unique()),
            "fx_currencies": sorted(fx.currency.unique()),
            "fx_date_span": f"{fx.date.min()}..{fx.date.max()}",
            "tables": sorted(p.name for p in RAW.glob("*")),
        },
        ensure_ascii=False,
    )
