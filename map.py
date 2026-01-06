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

# =======================
# HELPER
# =======================
def extract_lat_lon(lokasi_str):
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
    df_konsumen = pd.read_excel("Data ZipCode.xlsx")
    df_kantor   = pd.read_excel("master_zip.xlsx", sheet_name="kantor")
    df_zip      = pd.read_excel("master_zip.xlsx", sheet_name="Sheet1")

    df_konsumen.columns = df_konsumen.columns.str.strip().str.upper()
    df_kantor.columns   = df_kantor.columns.str.strip().str.upper()
    df_zip.columns      = df_zip.columns.str.strip()

    if "REALISASIDATE" in df_konsumen.columns:
        df_konsumen["REALISASIDATE"] = pd.to_datetime(
            df_konsumen["REALISASIDATE"], errors="coerce", dayfirst=True
        )
        df_konsumen = df_konsumen[df_konsumen["REALISASIDATE"].notna()]

    df_konsumen["KODEPOS"] = normalize_postal_code(df_konsumen["KODEPOS"])
    df_zip["postal_code"] = normalize_postal_code(df_zip["postal_code"])

    df_konsumen = df_konsumen.merge(
        df_zip[["postal_code", "Latitude", "Longitude"]],
        left_on="KODEPOS",
        right_on="postal_code",
        how="left"
    )

    df_konsumen["lat"] = pd.to_numeric(df_konsumen["Latitude"], errors="coerce")
    df_konsumen["lon"] = pd.to_numeric(df_konsumen["Longitude"], errors="coerce")
    df_konsumen = df_konsumen[df_konsumen["lat"].notna() & df_konsumen["lon"].notna()]

    if "LOKASI" in df_kantor.columns:
        df_kantor[["lat", "lon"]] = df_kantor["LOKASI"].apply(
            lambda x: pd.Series(extract_lat_lon(x))
        )
    df_kantor = df_kantor[df_kantor["lat"].notna() & df_kantor["lon"].notna()]

    for col in ["PRODUK", "CABANG", "NAMA KANTOR"]:
        if col in df_konsumen.columns:
            df_konsumen[col] = df_konsumen[col].astype(str).str.strip().str.upper()
        if col in df_kantor.columns:
            df_kantor[col] = df_kantor[col].astype(str).str.strip().str.upper()

    return df_konsumen, df_kantor

# =======================
# APP
# =======================
st.set_page_config(page_title="Sebaran Konsumen per Kantor", layout="wide")
st.title("📍 Sebaran Konsumen per Kantor")

df_konsumen, df_kantor = load_data()

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
# COLOR MAP PER KANTOR (KONTRAS, 6 WARNA)
# =======================
kantor_list = sorted(df_kantor["NAMA KANTOR"].unique())

PALETTE_6 = [
    "#1f77b4",  # biru
    "#d62728",  # merah
    "#2ca02c",  # hijau
    "#ff7f0e",  # oranye
    "#9467bd",  # ungu
    "#17becf",  # cyan
]

warna_kantor = {
    kantor: PALETTE_6[i % len(PALETTE_6)]
    for i, kantor in enumerate(kantor_list)
}

# =======================
# DRAW KONSUMEN PER KANTOR
# =======================
for kantor in kantor_list:

    # 👉 FILTER KANTOR (INI PATCH UTAMA)
    if selected_kantor != "ALL" and kantor != selected_kantor:
        continue

    df_kantor_k = df_kantor[df_kantor["NAMA KANTOR"] == kantor]
    cabang_list = df_kantor_k["CABANG"].unique().tolist()

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
# MARKER KANTOR
# =======================
for _, row in df_kantor.iterrows():
    if selected_kantor != "ALL" and row["NAMA KANTOR"] != selected_kantor:
        continue

    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=row["NAMA KANTOR"],
        icon=folium.Icon(
            color="black",
            icon="building",
            prefix="fa"
        )
    ).add_to(m)

# =======================
# HITUNG JUMLAH KONSUMEN PER KANTOR
# =======================
data_kantor_count = []

for kantor in kantor_list:
    if selected_kantor != "ALL" and kantor != selected_kantor:
        continue

    df_kantor_k = df_kantor[df_kantor["NAMA KANTOR"] == kantor]
    cabang_list = df_kantor_k["CABANG"].unique().tolist()

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
)

# =======================
# RENDER MAP
# =======================
st.subheader("🗺️ Peta Sebaran Konsumen per Kantor")
st_folium(
    m,
    use_container_width=True,
    height=650,
    returned_objects=[],   # << ini kuncinya
    key="map"              # optional tapi bagus untuk state
)

# =======================
# SIDEBAR LEGEND
# =======================
total_konsumen = df_konsumen.shape[0]

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Legend Kantor")

for _, row in df_legend.iterrows():
    st.sidebar.markdown(
        f"""
        <div style="display:flex; align-items:center; margin-bottom:4px;">
            <div style="
                width:12px;
                height:12px;
                background:{row['WARNA']};
                margin-right:8px;
            "></div>
            <div style="font-size:13px;">
                {row['KANTOR']} ({row['JUMLAH']:,})
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.sidebar.caption(f"👥 Total Konsumen: **{total_konsumen:,}**")






