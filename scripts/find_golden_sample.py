import pandas as pd
import json

df = pd.read_csv("data/ml/training_data.csv")
# Filter for QQQ and Label 1
sample = df[(df['symbol'] == 'QQQ') & (df['label'] == 1)].head(1)

if not sample.empty:
    print("Found Golden Sample. Saving to golden_sample.json")
    # Convert to dict and dump to json string
    rec = sample.iloc[0].to_dict()
    with open("golden_sample.json", "w") as f:
        json.dump(rec, f, indent=2)
    print(f"Timestamp: {rec['timestamp']}")
else:
    print("No QQQ sample found with label 1")
