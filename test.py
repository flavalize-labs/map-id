import pandas as pd

df = pd.read_parquet("konsumen.parquet")
print(df.columns.tolist())
