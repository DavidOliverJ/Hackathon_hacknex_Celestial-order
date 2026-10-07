import json
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
raw_rows = len(df)
df = df.drop_duplicates()
deduped_rows = len(df)
duplicate_rows_removed = raw_rows - deduped_rows

distinct_customers = int(df["customer_id"].nunique())

print(f"ANSWER: {json.dumps(distinct_customers)}")
print(
    "EVIDENCE: "
    + json.dumps(
        {
            "rows_raw": raw_rows,
            "rows_deduped": deduped_rows,
            "duplicate_rows_removed": duplicate_rows_removed,
        }
    )
)