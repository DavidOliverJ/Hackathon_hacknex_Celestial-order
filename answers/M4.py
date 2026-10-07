import json
from datetime import date
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# Record initial raw rows
rows_raw = len(df)

# Deduplicate
df = df.drop_duplicates()
rows_deduped = len(df)
duplicate_rows_removed = rows_raw - rows_deduped

# Date parser helper
def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)

# Filter for calendar Q3 2024: 2024-07-01 to 2024-09-30
start_date = date(2024, 7, 1)
end_date = date(2024, 9, 30)
df = df[(df["order_dt"] >= start_date) & (df["order_dt"] <= end_date)].copy()
rows_in_scope = len(df)

# Handle amounts
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
nulls_skipped = int(df["amount"].isna().sum())
df = df[df["amount"].notna()].copy()

# Prepare fx rates dictionary
rates = {(str(r.date), r.currency): float(r.rate_to_usd) for r in fx.itertuples()}

rows_missing_fx_rate = 0
def to_usd(row):
    global rows_missing_fx_rate
    if row.currency == "USD":
        return float(row.amount)
    rate = rates.get((str(row.order_dt), row.currency))
    if rate is not None:
        return float(row.amount) * rate
    else:
        rows_missing_fx_rate += 1
        return None

df["usd"] = df.apply(to_usd, axis=1)
df = df[df["usd"].notna()].copy()

# Group by region and sum USD revenue
region_revenue = df.groupby("region")["usd"].sum()
best_region = region_revenue.idxmax()

evidence = {
    "rows_raw": rows_raw,
    "rows_deduped": rows_deduped,
    "duplicate_rows_removed": duplicate_rows_removed,
    "rows_in_scope": rows_in_scope,
    "nulls_skipped": nulls_skipped,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": len(df)
}

print(f"ANSWER: {json.dumps(best_region)}")
print(f"EVIDENCE: {json.dumps(evidence)}")