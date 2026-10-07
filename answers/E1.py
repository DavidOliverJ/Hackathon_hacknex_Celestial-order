import json
import pandas as pd

df = pd.read_csv("data/raw/sales_transactions.csv")
total_rows = len(df)

print(f"ANSWER: {json.dumps(total_rows)}")
print("EVIDENCE: " + json.dumps({"rows_raw": total_rows}))