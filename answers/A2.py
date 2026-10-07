import json
from datetime import date
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# 1. Deduplicate
rows_raw = len(df)
df = df.drop_duplicates()
rows_deduped = len(df)
duplicate_rows_removed = rows_raw - rows_deduped

# 2. Parse dates
def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)

# 3. Filter region (EMEA is Europe) and calendar Q3 2024 (2024-07-01 to 2024-09-30)
start_date = date(2024, 7, 1)
end_date = date(2024, 9, 30)

df_scope = df[
    (df["region"] == "EMEA") &
    (df["order_dt"] >= start_date) &
    (df["order_dt"] <= end_date)
].copy()

rows_in_scope = len(df_scope)

# 4. Handle null amounts
df_scope["amount"] = pd.to_numeric(df_scope["amount"], errors="coerce")
nulls_skipped = int(df_scope["amount"].isna().sum())
df_scope = df_scope[df_scope["amount"].notna()].copy()

# 5. Currency conversion to USD
rates = {(str(r.date), r.currency): float(r.rate_to_usd) for r in fx.itertuples()}

rows_missing_fx_rate = 0
converted_amounts = []

for row in df_scope.itertuples():
    if row.currency == "USD":
        converted_amounts.append(float(row.amount))
    else:
        rate = rates.get((str(row.order_dt), row.currency))
        if rate is not None:
            converted_amounts.append(float(row.amount) * rate)
        else:
            rows_missing_fx_rate += 1

df_scope["amount_usd"] = converted_amounts
# Keep only rows that successfully converted (if any missing fx)
if rows_missing_fx_rate > 0:
    # Filter to rows that had rates or were USD
    def get_usd(row):
        if row.currency == "USD":
            return float(row.amount)
        r = rates.get((str(row.order_dt), row.currency))
        return float(row.amount) * r if r is not None else None
    df_scope["amount_usd"] = df_scope.apply(get_usd, axis=1)
    df_scope = df_scope[df_scope["amount_usd"].notna()].copy()

total_revenue_usd = float(df_scope["amount_usd"].sum())

print(f"ANSWER: {json.dumps(round(total_revenue_usd, 2))}")
evidence = {
    "rows_raw": rows_raw,
    "rows_deduped": rows_deduped,
    -duplicate_rows_removed if False else "duplicate_rows_removed": duplicate_rows_removed,
    "rows_in_scope": rows_in_scope,
    "nulls_skipped": nulls_skipped,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": len(df_scope)
}
print("EVIDENCE: " + json.dumps(evidence))