import json
from datetime import date
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# Deduplicate
initial_rows = len(df)
df = df.drop_duplicates()
deduped_rows = len(df)

def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)

# Filter for calendar Q3 2024: July 1, 2024 to September 30, 2024
start_date = date(2024, 7, 1)
end_date = date(2024, 9, 30)
df_q3 = df[(df["order_dt"] >= start_date) & (df["order_dt"] <= end_date)].copy()
rows_in_scope = len(df_q3)

# Handle null amounts
df_q3["amount"] = pd.to_numeric(df_q3["amount"], errors="coerce")
nulls_skipped = int(df_q3["amount"].isna().sum())
df_q3 = df_q3[df_q3["amount"].notna()].copy()

# Currency conversion rates
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

df_q3["usd"] = df_q3.apply(to_usd, axis=1)
df_q3 = df_q3[df_q3["usd"].notna()].copy()

rows_used = len(df_q3)
avg_order_value = float(df_q3["usd"].mean()) if rows_used > 0 else None

print(f"ANSWER: {json.dumps(avg_order_value)}")
print("EVIDENCE: " + json.dumps({
    "rows_raw": initial_rows,
    "rows_deduped": deduped_rows,
    "rows_in_scope": rows_in_scope,
    "nulls_skipped": nulls_skipped,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": rows_used
}))