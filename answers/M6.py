import json
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
rows_raw = len(df)
df_deduped = df.drop_duplicates()
rows_deduped = len(df_deduped)
duplicate_rows_removed = rows_raw - rows_deduped

print(f"ANSWER: {json.dumps(rows_deduped)}")
print("EVIDENCE: " + json.dumps({
    "rows_raw": rows_raw,
    "rows_deduped": rows_deduped,
    "duplicate_rows_removed": duplicate_rows_removed
}))