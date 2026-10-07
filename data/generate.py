"""Seeded generator for a messy, multi-table retail sales dataset.

Design rules (fairness contract):
  * Every mess is either (a) resolvable by a careful agent, or (b) an
    explicit refusal/ambiguity question. Nothing is randomly wrong.
  * Slash-format dates always have day in 13..28 so DD/MM/YYYY is the
    only possible reading (the agent must infer this from the data).
  * gold.json is computed from ground truth BEFORE corruption, so the
    evaluator knows the right answer for every answerable question.
"""
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
OUT = Path(__file__).parent / "raw"

REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
CATEGORIES = [
    "Electronics", "Home & Kitchen", "Apparel", "Sports", "Toys", "Books",
]
FX_FLAT_EUR = 1.09  # legacy flat rate mentioned (and deprecated) in the memo
FX_GAP = (date(2024, 6, 10), date(2024, 6, 20))  # INR rates missing here
START, END = date(2024, 1, 1), date(2024, 9, 30)


def build_products(rng: np.random.Generator) -> pd.DataFrame:
    names = [
        "Wireless Headphones", "Espresso Machine", "Yoga Mat", "Board Game",
        "Running Shoes", "Desk Lamp", "Bluetooth Speaker", "Chef's Knife",
        "Rain Jacket", "Puzzle Box", "Novel: Deep Water", "USB-C Hub",
        "Air Fryer", "Resistance Bands", "Kids Drone", "Chess Set",
        "Mechanical Keyboard", "Blender", "Hiking Backpack", "Action Figure",
        "Poetry Anthology", "Monitor Stand", "Rice Cooker", "Tennis Racket",
        "Building Blocks", "Canvas Easel", "Webcam HD", "Toaster",
        "Wool Scarf", "Card Deck", "Graphic Novel", "Laptop Sleeve",
        "Stand Mixer", "Camping Tent", "Soccer Ball", "Robot Kit",
        "Sci-Fi Trilogy", "Phone Charger", "Smart Plug", "Duvet Cover",
        "Cycling Gloves", "Stuffed Bear", "Art Supplies", "HDMI Cable",
        "Electric Kettle", "Fishing Rod", "Baby Monitor", "Tablet Case",
        "LED Strip", "Microwave", "Swim Goggles", "Toy Car Set",
        "Fountain Pen", "Power Bank", "Office Chair", "Blender Bottle",
        "Sneakers", "Lantern", "Karaoke Mic", "Memory Game",
    ]
    rows = []
    for i, name in enumerate(names):
        cat = CATEGORIES[i % len(CATEGORIES)]
        rows.append(
            {
                "product_id": f"P{i + 1:03d}",
                "product_name": name,
                "category": cat,
                "launch_date": str(
                    START - timedelta(days=int(rng.integers(30, 900)))
                ),
                "standard_price_usd": round(float(rng.uniform(8, 600)), 2),
            }
        )
    df = pd.DataFrame(rows)
    # mess: inconsistent casing / padding in ~12% of category cells
    idx = rng.choice(len(df), size=max(1, len(df) // 8), replace=False)
    for j, i in enumerate(idx):
        style = j % 3
        if style == 0:
            df.loc[i, "category"] = df.loc[i, "category"].lower()
        elif style == 1:
            df.loc[i, "category"] = df.loc[i, "category"].upper() + " "
        else:
            df.loc[i, "category"] = " " + df.loc[i, "category"].title()
    # mess: a few missing categories
    miss = rng.choice(len(df), size=3, replace=False)
    df.loc[miss, "category"] = None
    return df


def build_catalog_export(products: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Second catalog that CONTRADICTS products.csv for a handful of items."""
    df = products[["product_id", "product_name", "category"]].copy()
    df["supplier"] = [f"SUP-{i % 17:03d}" for i in range(len(df))]
    df["last_updated"] = "2024-08-15"
    # pick 8 products to contradict (always including P001 Wireless Headphones)
    force = [0]
    others = rng.choice(
        [i for i in range(1, len(df))], size=7, replace=False
    )
    for i in list(force) + list(others):
        wrong = "Accessories" if df.loc[i, "category"] != "Accessories" else "Gadgets"
        df.loc[i, "category"] = wrong
    return df


def build_fx(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    d = START
    while d <= END:
        # rate_to_usd = USD per 1 unit of currency (EUR ~1.08, INR ~0.0121)
        for cur, base, vol in (("EUR", 1.08, 0.02), ("INR", 0.0121, 0.0002)):
            if cur == "INR" and FX_GAP[0] <= d <= FX_GAP[1]:
                continue  # the deliberate gap
            rows.append(
                {
                    "date": str(d),
                    "currency": cur,
                    "rate_to_usd": round(base + float(rng.normal(0, vol)), 4),
                }
            )
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def fmt_date(rng: np.random.Generator, d: date) -> str:
    """Mixed date formats. Slash rows always have day in 13..28 (DD/MM forced)."""
    style = rng.random()
    if style < 0.60:
        return d.isoformat()
    if style < 0.90:
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    if 13 <= d.day <= 28:
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    forced = date(d.year, d.month, int(rng.integers(13, 29)))
    return f"{forced.day:02d}/{forced.month:02d}/{forced.year}"


def parse_written(rng: np.random.Generator, s: str) -> date:
    """Ground-truth date for a formatted string written by fmt_date."""
    if "/" in s:
        dd, mm, yy = s.split("/")
        return date(int(yy), int(mm), int(dd))
    if s[0].isdigit():
        return date.fromisoformat(s)
    return pd.to_datetime(s).date()


def build_sales(rng: np.random.Generator, products: pd.DataFrame) -> pd.DataFrame:
    n = 5000
    n_days = (END - START).days + 1
    n_customers = 800
    currency = rng.choice(["USD", "EUR", "INR"], size=n, p=[0.70, 0.20, 0.10])
    region_w = np.array([0.42, 0.30, 0.18, 0.10])
    rows = []
    for i in range(n):
        d = START + timedelta(days=int(rng.integers(0, n_days)))
        written = fmt_date(rng, d)
        true_date = parse_written(rng, written)
        pid = f"P{int(rng.integers(1, len(products) + 1)):03d}"
        cur = currency[i]
        base = float(products.loc[products.product_id == pid, "standard_price_usd"].iloc[0])
        fx = {"USD": 1.0, "EUR": 1.08, "INR": 0.0121}[cur]
        qty = int(rng.choice([1, 1, 1, 2, 2, 3, 4], p=[0.35, 0.2, 0.1, 0.14, 0.1, 0.07, 0.04]))
        amount = round(base * qty / fx * float(rng.uniform(0.85, 1.15)), 2)
        if rng.random() < 0.012:
            amount = -amount  # return / refund row
        rows.append(
            {
                "order_id": f"O{i + 1:05d}",
                "order_date": written,
                "true_date": true_date,
                "customer_id": f"C{int(rng.integers(1, n_customers + 1)):04d}",
                "product_id": pid,
                "region": REGIONS[
                    int(rng.choice(4, p=region_w))
                ],
                "quantity": qty,
                "amount": amount,
                "currency": cur,
            }
        )
    df = pd.DataFrame(rows)

    # mess: missing amounts (~1.4%)
    miss = rng.choice(n, size=70, replace=False)
    df.loc[miss, "amount"] = None
    # mess: missing region (~0.3%)
    miss_r = rng.choice(n, size=15, replace=False)
    df.loc[miss_r, "region"] = None
    # mess: exact duplicate rows (~2.4%)
    dup = rng.choice(n, size=120, replace=False)
    df = pd.concat([df, df.iloc[dup]], ignore_index=True)
    df = df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    return df


def to_usd(amount, currency, d: date, fx: pd.DataFrame) -> float | None:
    if amount is None or (isinstance(amount, float) and np.isnan(amount)):
        return None
    if currency == "USD":
        return float(amount)
    hit = fx[(fx.currency == currency) & (fx.date == str(d))]
    if hit.empty:
        return None
    return float(amount) * float(hit.rate_to_usd.iloc[0])


def compute_gold(raw: pd.DataFrame, products: pd.DataFrame, fx: pd.DataFrame) -> dict:
    """Gold values computed from true dates, deduped, null-safe."""
    df = raw.drop_duplicates().copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["usd"] = [
        to_usd(a, c, d, fx)
        for a, c, d in zip(df["amount"], df["currency"], df["true_date"])
    ]
    valid = df[df["usd"].notna()]
    q3 = valid[(valid.true_date >= date(2024, 7, 1)) & (valid.true_date <= date(2024, 9, 30))]
    jul = valid[(valid.true_date >= date(2024, 7, 1)) & (valid.true_date <= date(2024, 7, 31))]
    jan_mar = valid[(valid.true_date >= date(2024, 1, 1)) & (valid.true_date <= date(2024, 3, 31))]
    may = valid[(valid.true_date >= date(2024, 5, 1)) & (valid.true_date <= date(2024, 5, 31))]
    mar04 = valid[valid.true_date == date(2024, 3, 4)]
    apr03 = valid[valid.true_date == date(2024, 4, 3)]

    pnorm = products.dropna(subset=["category"]).copy()
    pnorm["cat_norm"] = pnorm["category"].str.strip().str.title()

    gold = {
        "rows_raw": int(len(raw)),
        "rows_deduped": int(len(df)),
        "distinct_customers": int(df.customer_id.nunique()),
        "top_product_category": str(pnorm.cat_norm.value_counts().idxmax()),
        "top_product_category_count": int(pnorm.cat_norm.value_counts().max()),
        "avg_qty_per_order": round(float(df.quantity.mean()), 4),
        "avg_order_value_usd_q3_2024": round(float(q3.usd.mean()), 2),
        "total_revenue_usd_jul2024": round(float(jul.usd.sum()), 2),
        "median_order_value_usd": round(float(valid.usd.median()), 2),
        "top_region_usd_q3_2024": str(
            q3.dropna(subset=["region"]).groupby("region").usd.sum().idxmax()
        ),
        "total_revenue_usd_inr_may2024": round(
            float(may[may.currency == "INR"].usd.sum()), 2
        ),
        "avg_order_value_usd_q3_calendar": round(float(q3.usd.mean()), 2),
        "avg_order_value_usd_q3_fiscal_jan_mar": round(float(jan_mar.usd.mean()), 2),
        "total_revenue_usd_q3_emea": round(
            float(q3[q3.region == "EMEA"].usd.sum()), 2
        ),
        "revenue_usd_2024_03_04": round(float(mar04.usd.sum()), 2),
        "revenue_usd_2024_04_03": round(float(apr03.usd.sum()), 2),
        "null_amount_rows": int(raw["amount"].isna().sum()),
        "negative_amount_rows": int((pd.to_numeric(raw["amount"], errors="coerce") < 0).sum()),
        "duplicate_rows": int(len(raw) - len(df)),
    }
    return gold


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    products = build_products(rng)
    catalog = build_catalog_export(products, rng)
    fx = build_fx(rng)
    sales = build_sales(rng, products)
    gold = compute_gold(sales, products, fx)

    targets = pd.DataFrame(
        {
            "quarter": ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024"],
            "target_revenue_inr": [42_000_000, 45_500_000, 51_000_000, 55_000_000],
            "fiscal_year": ["FY2024", "FY2024", "FY2024", "FY2024"],
        }
    )

    memo = """FINANCE MEMO - FY2024 DATA NOTES (treasury team)
=====================================================

1. Revenue definition
   The `amount` column in sales_transactions.csv is the line total in the
   transaction's ORIGINAL currency. Returns/refunds are recorded as negative
   amounts and ARE included in revenue. Do not filter them out.

2. Currency conversion
   Amounts arrive in USD, EUR and INR. Always convert using the daily rates
   in fx_rates.csv (column `rate_to_usd`).
   NOTE: older reports used a flat 1 EUR = 1.09 USD. That convention was
   retired in 2024 -- always use the daily table instead.

3. Fiscal year
   Our fiscal year starts on APRIL 1. So "fiscal Q3" is NOT the same as
   calendar Q3. When someone says just "Q3", confirm which one they mean.

4. Data caveats
   - sales_transactions.csv contains duplicate rows from an ETL double-run.
   - Some rows have missing amounts or missing regions.
   - Two catalog exports exist and they do not always agree.
"""
    (OUT / "finance_memo.txt").write_text(memo, encoding="utf-8")

    sales_out = sales.drop(columns=["true_date"]).copy()
    sales_out.to_csv(OUT / "sales_transactions.csv", index=False)
    products.to_csv(OUT / "products.csv", index=False)
    catalog.to_csv(OUT / "product_catalog_export.csv", index=False)
    fx.to_csv(OUT / "fx_rates.csv", index=False)
    targets.to_csv(OUT / "quarterly_targets.csv", index=False)

    (Path(__file__).parent / "gold.json").write_text(
        json.dumps(gold, indent=2), encoding="utf-8"
    )

    print(f"Wrote 6 files to {OUT}")
    print(f"rows raw={gold['rows_raw']} deduped={gold['rows_deduped']} "
          f"dupes={gold['duplicate_rows']} nulls={gold['null_amount_rows']}")
    print("gold:", json.dumps(gold, indent=2))


if __name__ == "__main__":
    main()
