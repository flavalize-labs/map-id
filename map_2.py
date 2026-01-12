import streamlit as st
import pandas as pd
import folium
from folium import CircleMarker, FeatureGroup
from streamlit_folium import st_folium
import matplotlib.cm as cm
import matplotlib.colors as mcolors

# =======================
# CONFIG
# =======================
MAX_POINTS_PER_KANTOR = 3000
TOP_N_LEGEND = 10

# =======================
# HELPER
# =======================
def extract_lat_lon(lokasi_str):
    """
    (Tidak dipakai lagi untuk kantor, karena kantor sekarang pakai sheet 'alamat'
    dengan kolom LATITUDE/LONGITUDE. Tetap disimpan bila suatu saat dipakai.)
    """
    try:
        lat, lon = map(float, str(lokasi_str).split(","))
        return lat, lon
    except Exception:
        return None, None

def normalize_postal_code(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(5)
    )

# =======================
# LOAD DATA
# =======================
@st.cache_data(show_spinner=False)
def load_data():
    # Konsumen
    df_konsumen = pd.read_excel("Data ZipCode.xlsx")

    # Master zip (NEW)
    df_mapping  = pd.read_excel("master_zip.xlsx", sheet_name="mapping")  # CABANG, KANTOR_ID
    df_kantor   = pd.read_excel("master_zip.xlsx", sheet_name="alamat")   # ID, NAMA KANTOR, ..., LATITUDE, LONGITUDE
    df_zip      = pd.read_excel("master_zip.xlsx", sheet_name="Sheet1")   # postal_code, Latitude, Longitude

    # Normalisasi header
    df_konsumen.columns = df_konsumen.columns.str.strip().str.upper()
    df_mapping.columns  = df_mapping.columns.str.strip().str.upper()
    df_kantor.columns   = df_kantor.columns.str.strip().str.upper()
    df_zip.columns      = df_zip.columns.str.strip()

    # Filter tanggal (kalau ada)
    if "REALISASIDATE" in df_konsumen.columns:
        df_konsumen["REALISASIDATE"] = pd.to_datetime(
            df_konsumen["REALISASIDATE"], errors="coerce", dayfirst=True
        )
        df_konsumen = df_konsumen[df_konsumen["REALISASIDATE"].notna()]

    # Normalisasi kodepos
    if "KODEPOS" in df_konsumen.columns:
        df_konsumen["KODEPOS"] = normalize_postal_code(df_konsumen["KODEPOS"])
    if "postal_code" in df_zip.columns:
        df_zip["postal_code"] = normalize_postal_code(df_zip["postal_code"])

    # Merge zipcode -> lat/lon konsumen
    df_konsumen = df_konsumen.merge(
        df_zip[["postal_code", "Latitude", "Longitude"]],
        left_on="KODEPOS",
        right_on="postal_code",
        how="left"
    )
    df_konsumen["lat"] = pd.to_numeric(df_konsumen["Latitude"], errors="coerce")
    df_konsumen["lon"] = pd.to_numeric(df_konsumen["Longitude"], errors="coerce")
    df_konsumen = df_konsumen[df_konsumen["lat"].notna() & df_konsumen["lon"].notna()]

    # Kantor dari sheet 'alamat'
    # Tangani kemungkinan decimal koma
    for col in ["LATITUDE", "LONGITUDE"]:
        if col in df_kantor.columns:
            df_kantor[col] = (
                df_kantor[col].astype(str)
                .str.strip()
                .str.replace(",", ".", regex=False)
            )

    df_kantor["LAT"] = pd.to_numeric(df_kantor["LATITUDE"], errors="coerce")
    df_kantor["LON"] = pd.to_numeric(df_kantor["LONGITUDE"], errors="coerce")
    df_kantor = df_kantor[df_kantor["LAT"].notna() & df_kantor["LON"].notna()]

    # Mapping cabang -> kantor_id
    if "CABANG" in df_mapping.columns:
        df_mapping["CABANG"] = df_mapping["CABANG"].astype(str).str.strip().str.upper()

    # Konsistensi teks
    for col in ["PRODUK", "CABANG"]:
        if col in df_konsumen.columns:
            df_konsumen[col] = df_konsumen[col].astype(str).str.strip().str.upper()

    if "NAMA KANTOR" in df_kantor.columns:
        df_kantor["NAMA KANTOR"] = df_kantor["NAMA KANTOR"].astype(str).str.strip().str.upper()

    return df_konsumen, df_kantor, df_mapping

# =======================
# APP
# =======================
st.set_page_config(page_title="Sebaran Konsumen per Kantor", layout="wide")
st.title("📍 Sebaran Konsumen per Kantor")

df_konsumen, df_kantor, df_mapping = load_data()

# =======================
# SIDEBAR FILTER
# =======================
st.sidebar.header("🔎 Filter")

# ---- PRODUK ----
produk_opsi = ["ALL"] + sorted(df_konsumen["PRODUK"].unique())
selected_produk = st.sidebar.selectbox("Produk", produk_opsi)

if selected_produk != "ALL":
    df_konsumen = df_konsumen[df_konsumen["PRODUK"] == selected_produk]

# ---- KANTOR ----
kantor_opsi = ["ALL"] + sorted(df_kantor["NAMA KANTOR"].unique())
selected_kantor = st.sidebar.selectbox("Kantor", kantor_opsi)

# =======================
# TOTAL APLIKASI
# =======================
st.sidebar.markdown("---")
st.sidebar.metric("Total Aplikasi", f"{df_konsumen.shape[0]:,}")

# =======================
# MAP INIT
# =======================
center_lat = df_konsumen["lat"].mean()
center_lon = df_konsumen["lon"].mean()

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=6,
    tiles="CartoDB positron"
)

# =======================
# COLOR MAP PER KANTOR (AUTO)
# =======================
kantor_list = sorted(df_kantor["NAMA KANTOR"].unique())

cmap = cm.get_cmap("tab20", len(kantor_list))  # alternatif: "hsv", "nipy_spectral", "turbo"
warna_kantor = {
    kantor: mcolors.to_hex(cmap(i))
    for i, kantor in enumerate(kantor_list)
}

# =======================
# HITUNG JUMLAH KONSUMEN PER KANTOR (untuk legend Top 10)
# =======================
data_kantor_count = []

for kantor in kantor_list:
    # kalau user pilih kantor spesifik, legend akan otomatis cuma 1
    if selected_kantor != "ALL" and kantor != selected_kantor:
        continue

    kantor_row = df_kantor[df_kantor["NAMA KANTOR"] == kantor].head(1)
    if kantor_row.empty:
        continue

    kantor_id = kantor_row["ID"].iloc[0]

    cabang_list = (
        df_mapping[df_mapping["KANTOR_ID"] == kantor_id]["CABANG"]
        .dropna()
        .astype(str).str.strip().str.upper()
        .unique()
        .tolist()
    )

    jumlah = df_konsumen[df_konsumen["CABANG"].isin(cabang_list)].shape[0]

    if jumlah > 0:
        data_kantor_count.append({
            "KANTOR": kantor,
            "JUMLAH": jumlah,
            "WARNA": warna_kantor[kantor]
        })

df_legend = (
    pd.DataFrame(data_kantor_count)
    .sort_values("JUMLAH", ascending=False)
    .head(TOP_N_LEGEND)
)

# =======================
# DRAW KONSUMEN PER KANTOR (pakai mapping -> kantor_id)
# =======================
for kantor in kantor_list:

    # Filter kantor
    if selected_kantor != "ALL" and kantor != selected_kantor:
        continue

    kantor_row = df_kantor[df_kantor["NAMA KANTOR"] == kantor].head(1)
    if kantor_row.empty:
        continue

    kantor_id = kantor_row["ID"].iloc[0]

    cabang_list = (
        df_mapping[df_mapping["KANTOR_ID"] == kantor_id]["CABANG"]
        .dropna()
        .astype(str).str.strip().str.upper()
        .unique()
        .tolist()
    )

    df_kons_k = df_konsumen[df_konsumen["CABANG"].isin(cabang_list)]
    if df_kons_k.empty:
        continue

    if len(df_kons_k) > MAX_POINTS_PER_KANTOR:
        df_kons_k = df_kons_k.sample(MAX_POINTS_PER_KANTOR, random_state=42)

    fg = FeatureGroup(name=kantor)

    for _, row in df_kons_k.iterrows():
        CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=3,
            color=warna_kantor[kantor],
            fill=True,
            fill_color=warna_kantor[kantor],
            fill_opacity=0.6,
            weight=0,
            tooltip=(
                f"Cabang: {row['CABANG']}<br>"
                f"APPID: {row.get('APPID', '-')}"
            )
        ).add_to(fg)

    fg.add_to(m)

# =======================
# MARKER KANTOR (dari sheet 'alamat')
# =======================
for _, row in df_kantor.iterrows():
    if selected_kantor != "ALL" and row["NAMA KANTOR"] != selected_kantor:
        continue

    folium.Marker(
        location=[row["LAT"], row["LON"]],
        popup=row["NAMA KANTOR"],
        icon=folium.Icon(
            color="black",
            icon="building",
            prefix="fa"
        )
    ).add_to(m)

# =======================
# RENDER MAP
# =======================
st.subheader("🗺️ Peta Sebaran Konsumen per Kantor")
st_folium(
    m,
    use_container_width=True,
    height=650,
    returned_objects=[],   # ini kuncinya
    key="map"
)

# =======================
# SIDEBAR LEGEND (Top 10)
# =======================
st.sidebar.markdown("---")
st.sidebar.subheader(f"🎨 (Top {TOP_N_LEGEND})")

if df_legend.empty:
    st.sidebar.caption("Tidak ada data untuk ditampilkan.")
else:
    for _, row in df_legend.iterrows():
        st.sidebar.markdown(
            f"""
            <div style="display:flex; align-items:center; margin-bottom:6px;">
                <div style="
                    width:12px;
                    height:12px;
                    background:{row['WARNA']};
                    margin-right:8px;
                    border-radius:2px;
                "></div>
                <div style="font-size:13px; line-height:1.2;">
                    {row['KANTOR']}<br>
                    <span style="opacity:0.8;">{row['JUMLAH']:,} aplikasi</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

