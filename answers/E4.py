import json
from datetime import date
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
rows_raw = len(df)
df = df.drop_duplicates()
rows_deduped = len(df)
duplicate_rows_removed = rows_raw - rows_deduped

avg_quantity = float(df["quantity"].mean())

print(f"ANSWER: {json.dumps(round(avg_quantity, 4))}")
print("EVIDENCE: " + json.dumps({
    "rows_raw": rows_raw,
    "rows_deduped": rows_deduped,
    "duplicate_rows_removed": duplicate_rows_removed,
    "rows_used": rows_deduped
}))