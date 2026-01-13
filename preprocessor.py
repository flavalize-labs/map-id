import pandas as pd

# =======================
# LOAD EXCEL
# =======================
df_konsumen = pd.read_excel(
    "Data ZipCode.xlsx",
    dtype={"KODEPOS": "string", "CABANG": "string", "PRODUK": "string"},
)

xls = pd.ExcelFile("master_zip.xlsx")
df_mapping = xls.parse("mapping", dtype={"CABANG": "string", "KANTOR_ID": "string"})
df_kantor  = xls.parse("alamat")
df_zip     = xls.parse("Sheet1", dtype={"postal_code": "string"})

# =======================
# CLEAN & NORMALIZE
# =======================
def normalize_postal_code(series):
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(5)
    )

df_konsumen.columns = df_konsumen.columns.str.strip().str.upper()
df_mapping.columns  = df_mapping.columns.str.strip().str.upper()
df_kantor.columns   = df_kantor.columns.str.strip().str.upper()
df_zip.columns      = df_zip.columns.str.strip()

df_konsumen["KODEPOS"] = normalize_postal_code(df_konsumen["KODEPOS"])
df_zip["postal_code"]  = normalize_postal_code(df_zip["postal_code"])

df_konsumen = df_konsumen.merge(
    df_zip[["postal_code", "Latitude", "Longitude"]],
    left_on="KODEPOS",
    right_on="postal_code",
    how="left"
)

df_konsumen["lat"] = pd.to_numeric(df_konsumen["Latitude"], errors="coerce")
df_konsumen["lon"] = pd.to_numeric(df_konsumen["Longitude"], errors="coerce")
df_konsumen = df_konsumen.dropna(subset=["lat", "lon"])

df_mapping["CABANG"] = df_mapping["CABANG"].str.upper().str.strip()
df_mapping["KANTOR_ID"] = df_mapping["KANTOR_ID"].astype(str)

df_konsumen = df_konsumen.merge(
    df_mapping[["CABANG", "KANTOR_ID"]].drop_duplicates("CABANG"),
    on="CABANG",
    how="left"
)

for c in ["LATITUDE", "LONGITUDE"]:
    df_kantor[c] = (
        df_kantor[c].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^0-9\.\-]", "", regex=True)
    )

df_kantor["LAT"] = pd.to_numeric(df_kantor["LATITUDE"], errors="coerce")
df_kantor["LON"] = pd.to_numeric(df_kantor["LONGITUDE"], errors="coerce")

# =======================
# SAVE PARQUET
# =======================
df_konsumen.to_parquet("konsumen.parquet", index=False)
df_kantor.to_parquet("kantor.parquet", index=False)
df_mapping.to_parquet("mapping.parquet", index=False)

print("✅ Parquet files created")
