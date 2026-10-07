import json
from datetime import date
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# Deduplicate
df_raw_len = len(df)
df = df.drop_duplicates()
rows_deduped = len(df)
duplicates_removed = df_raw_len - rows_deduped

def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)

# Filter for April 3, 2024
target_date = date(2024, 4, 3)
df_in_scope = df[df["order_dt"] == target_date].copy()
rows_in_scope = len(df_in_scope)

# Drop null amounts
nulls_skipped = int(df_in_scope["amount"].isna().sum())
df_in_scope["amount"] = pd.to_numeric(df_in_scope["amount"], errors="coerce")
df_in_scope = df_in_scope[df_in_scope["amount"].notna()].copy()

# Currency conversion
rates = {(str(r.date), r.currency): float(r.rate_to_usd) for r in fx.itertuples()}

rows_missing_fx_rate = 0
converted_amounts = []
rows_used_count = 0

for row in df_in_scope.itertuples():
    amt = float(row.amount)
    curr = row.currency
    if curr == "USD":
        converted_amounts.append(amt)
        rows_used_count += 1
    else:
        rate = rates.get((str(row.order_dt), curr))
        if rate is not None:
            converted_amounts.append(amt * rate)
            rows_used_count += 1
        else:
            rows_missing_fx_rate += 1

total_revenue = sum(converted_amounts) if converted_amounts else 0.0

print(f"ANSWER: {json.dumps(round(total_revenue, 2))}")
print("EVIDENCE: " + json.dumps({
    "rows_raw": df_raw_len,
    "duplicate_rows_removed": duplicates_removed,
    "rows_in_scope": rows_in_scope,
    "nulls_skipped": nulls_skipped,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": rows_used_count
}))