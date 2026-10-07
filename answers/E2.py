import json
import pandas as pd

# Load products.csv
df = pd.read_csv("data/raw/products.csv")

# Clean category column: drop nulls, strip whitespace, convert to lowercase for uniform counting
df = df.dropna(subset=["category"]).copy()
df["clean_category"] = df["category"].astype(str).str.strip().str.lower()

# Count occurrences of each cleaned category
category_counts = df["clean_category"].value_counts()

# Identify the category with the highest count
top_category = category_counts.idxmax()

# To present a clean title case or standard form from the original values,
# let's find one of the original string representations for this category.
original_matches = df[df["clean_category"] == top_category]["category"]
best_category_display = original_matches.iloc[0].strip().title()

# Collect evidence metrics
rows_raw = len(pd.read_csv("data/raw/products.csv"))
nulls_skipped = int(pd.read_csv("data/raw/products.csv")["category"].isna().sum())
rows_used = len(df)

print(f"ANSWER: {json.dumps(best_category_display)}")
print(
    "EVIDENCE: "
    + json.dumps(
        {
            "rows_raw": rows_raw,
            "nulls_skipped": nulls_skipped,
            "rows_used": rows_used,
            "category_counts": category_counts.to_dict(),
        }
    )
)