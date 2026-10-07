from datetime import date
import json
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# Deduplicate
initial_rows = len(df)
df = df.drop_duplicates()
deduped_rows = len(df)
duplicates_removed = initial_rows - deduped_rows

# Date parsing helper
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

# Prepare FX rates dictionary
fx["date_obj"] = fx["date"].map(parse_date)
rates = {(r.date_obj, r.currency): float(r.rate_to_usd) for r in fx.itertuples()}

rows_missing_fx_rate = 0

def to_usd(row):
    global rows_missing_fx_rate
    if row.currency == "USD":
        return float(row.amount)
    rate = rates.get((row.order_dt, row.currency))
    if rate is None:
        rows_missing_fx_rate += 1
        return None
    return float(row.amount) * rate

df["usd"] = df.apply(to_usd, axis=1)
df = df[df["usd"].notna()].copy()

median_val = float(df["usd"].median())

print(f"ANSWER: {json.dumps(median_val)}")
print("EVIDENCE: " + json.dumps({
    "rows_raw": initial_rows,
    "rows_deduped": deduped_rows,
    "duplicate_rows_removed": duplicates_removed,
    "nulls_skipped": null_amounts,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": len(df)
}))