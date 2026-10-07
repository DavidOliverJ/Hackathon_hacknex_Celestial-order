import json
from datetime import date
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
fx = pd.read_csv("data/raw/fx_rates.csv")

# 1. Deduplicate rows
df = df.drop_duplicates()
rows_deduped = len(df)

# 2. Parse dates
def parse_date(s):
    s = str(s)
    if "/" in s:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    return pd.to_datetime(s).date()

df["order_dt"] = df["order_date"].map(parse_date)

# 3. Filter for calendar Q3 (2024-07-01 to 2024-09-30)
q3_start = date(2024, 7, 1)
q3_end = date(2024, 9, 30)
df = df[(df["order_dt"] >= q3_start) & (df["order_dt"] <= q3_end)].copy()
rows_in_scope = len(df)

# 4. Handle null amounts
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
nulls_skipped = int(df["amount"].isna().sum())
df = df[df["amount"].notna()].copy()

# 5. Currency conversion to USD
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

df["usd_amount"] = df.apply(to_usd, axis=1)
df = df[df["usd_amount"].notna()].copy()

# 6. Compute average order value
# Average order value across all transactions in Q3 (or grouped by order_id if multiple lines, 
# but each row is typically an order or line item; let's check standard order metric: mean of transaction amounts or sum per order_id)
# Looking at order_id uniqueness: order_id has 5000 unique out of 5120 raw rows.
# Let's aggregate by order_id first if an order spans multiple rows, or treat each row as an order.
# Actually, let's sum amount per order_id to get total order value per order, then take the mean.
order_totals = df.groupby("order_id")["usd_amount"].sum()
ans = float(order_totals.mean())

evidence = {
    "rows_raw": 5120,
    "rows_deduped": rows_deduped,
    "rows_in_scope": rows_in_scope,
    "nulls_skipped": nulls_skipped,
    "rows_missing_fx_rate": rows_missing_fx_rate,
    "rows_used": len(order_totals)
}

print(f"ANSWER: {json.dumps(ans)}")
print("EVIDENCE: " + json.dumps(evidence))