import json
from datetime import date
import pandas as pd

# Load datasets
df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# 1. Deduplicate rows from ETL double-run
initial_rows = len(df)
df = df.drop_duplicates()
deduped_rows = len(df)
duplicates_removed = initial_rows - deduped_rows

# 2. Parse dates using the specified helper
def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)

# 3. Filter for July 2024
df = df[(df["order_dt"] >= date(2024, 7, 1)) & (df["order_dt"] <= date(2024, 7, 31))].copy()
rows_in_scope = len(df)

# 4. Handle null amounts
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
nulls_skipped = int(df["amount"].isna().sum())
df = df[df["amount"].notna()].copy()

# 5. Currency conversion setup
fx["date_obj"] = pd.to_datetime(fx["date"]).dt.date
rates = {(r.date_obj, r.currency): float(r.rate_to_usd) for r in fx.itertuples()}

rows_missing_fx_rate = 0
def to_usd(row):
    global rows_missing_fx_rate
    if row.currency == "USD":
        return float(row.amount)
    rate = rates.get((row.order_dt, row.currency))
    if rate is not None:
        return float(row.amount) * rate
    else:
        rows_missing_fx_rate += 1
        return None

df["usd_amount"] = df.apply(to_usd, axis=1)
df = df[df["usd_amount"].notna()].copy()

# 6. Compute total revenue in USD
total_revenue = float(df["usd_amount"].sum())

# 7. Output results
print(f"ANSWER: {json.dumps(total_revenue)}")
print("EVIDENCE: " + json.dumps({
    "rows_raw": initial_rows,
    "duplicate_rows_removed": duplicates_removed,
    "rows_deduped": deduped_rows,
    "rows_in_scope": rows_in_scope,
    "nulls_skipped": nulls_skipped,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": len(df)
}))