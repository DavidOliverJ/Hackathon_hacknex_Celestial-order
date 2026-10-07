import json
from datetime import date
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# Deduplicate as instructed
df = df.drop_duplicates()
rows_deduped = len(df)

def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)

# Filter for May 2024 and currency == 'INR'
df = df[(df["currency"] == "INR") & 
        (df["order_dt"] >= date(2024, 5, 1)) & 
        (df["order_dt"] <= date(2024, 5, 31))].copy()

# Handle null amounts
nulls_skipped = int(df["amount"].isna().sum())
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
df = df[df["amount"].notna()].copy()

rows_in_scope = len(df)

# Prepare FX rates dictionary
rates = {(str(r.date), r.currency): float(r.rate_to_usd) for r in fx.itertuples()}

def get_usd(row):
    rate = rates.get((str(row.order_dt), row.currency))
    return float(row.amount) * rate if rate is not None else None

df["usd"] = df.apply(get_usd, axis=1)

rows_missing_fx_rate = int(df["usd"].isna().sum())
df = df[df["usd"].notna()].copy()

total_usd = float(df["usd"].sum())

evidence = {
    "rows_deduped": rows_deduped,
    "rows_in_scope": rows_in_scope,
    "nulls_skipped": nulls_skipped,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": len(df)
}

print(f"ANSWER: {json.dumps(total_usd)}")
print("EVIDENCE: " + json.dumps(evidence))