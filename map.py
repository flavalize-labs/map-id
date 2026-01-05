import streamlit as st
import pandas as pd
import folium
from folium import Marker
from folium.plugins import HeatMap
from streamlit_folium import st_folium

# =======================
# CONFIG
# =======================
MAX_HEAT_POINTS = 6000
MAP_ZOOM = 11

# =======================
# HELPER
# =======================
def extract_lat_lon(lokasi_str):
    try:
        lat, lon = map(float, str(lokasi_str).split(","))
        return lat, lon
    except:
        return None, None

# =======================
# LOAD & PREP DATA
# =======================
@st.cache_data(show_spinner=False)
def load_and_prepare_data():
    df_konsumen = pd.read_excel("Data ZipCode.xlsx")
    df_kantor   = pd.read_excel("master_zip.xlsx", sheet_name="kantor")
    df_zip      = pd.read_excel("master_zip.xlsx", sheet_name="Sheet1")

    # Normalisasi kolom
    df_konsumen.columns = df_konsumen.columns.str.strip().str.upper()
    df_kantor.columns   = df_kantor.columns.str.strip().str.upper()
    df_zip.columns      = df_zip.columns.str.strip()

    # Filter realisasi
    if "REALISASIDATE" in df_konsumen.columns:
        df_konsumen["REALISASIDATE"] = pd.to_datetime(
            df_konsumen["REALISASIDATE"],
            errors="coerce",
            dayfirst=True
        )
        df_konsumen = df_konsumen[df_konsumen["REALISASIDATE"].notna()]

    # Kode pos
    if "KODEPOS" in df_konsumen.columns:
        df_konsumen["KODEPOS"] = df_konsumen["KODEPOS"].astype(str).str.strip()

    df_zip["postal_code"] = df_zip["postal_code"].astype(str).str.strip()

    # KONSUMEN
    df_konsumen["KODEPOS"] = (
        df_konsumen["KODEPOS"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .str.zfill(5)
    )

    # MASTER ZIP
    df_zip["postal_code"] = (
        df_zip["postal_code"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .str.zfill(5)
    )

    # Merge lat lon konsumen
    df_konsumen = df_konsumen.merge(
        df_zip[["postal_code", "Latitude", "Longitude"]],
        left_on="KODEPOS",
        right_on="postal_code",
        how="left"
    )

    df_konsumen["lat"] = pd.to_numeric(df_konsumen["Latitude"], errors="coerce")
    df_konsumen["lon"] = pd.to_numeric(df_konsumen["Longitude"], errors="coerce")
    df_konsumen = df_konsumen[df_konsumen["lat"].notna() & df_konsumen["lon"].notna()]

    # Lat lon kantor
    if "LOKASI" in df_kantor.columns:
        df_kantor[["lat", "lon"]] = df_kantor["LOKASI"].apply(
            lambda x: pd.Series(extract_lat_lon(x))
        )
    df_kantor = df_kantor[df_kantor["lat"].notna() & df_kantor["lon"].notna()]

    # Normalisasi text filter
    for col in ["CABANG", "NAMA KANTOR"]:
        if col in df_konsumen.columns:
            df_konsumen[col] = df_konsumen[col].astype(str).str.strip().str.upper()
        if col in df_kantor.columns:
            df_kantor[col] = df_kantor[col].astype(str).str.strip().str.upper()

    return df_konsumen, df_kantor

# =======================
# BUILD MAP
# =======================
@st.cache_data(show_spinner=False)
def build_map(heat_points, kantor_points, center_lat, center_lon):
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=MAP_ZOOM,
        tiles="CartoDB positron"
    )

    if heat_points:
        HeatMap(
            heat_points,
            radius=12,
            blur=15,
            min_opacity=0.3
        ).add_to(m)

    for kantor in kantor_points:
        Marker(
            location=kantor["loc"],
            popup=kantor["popup"],
            icon=folium.Icon(color="red", icon="building", prefix="fa")
        ).add_to(m)

    return m

# =======================
# STREAMLIT UI
# =======================
st.set_page_config(page_title="Peta Konsumen", layout="wide")
st.title("📍 Visualisasi Sebaran Konsumen BCAF")

try:
    df_konsumen, df_kantor = load_and_prepare_data()

    # =======================
    # SIDEBAR FILTER (FINAL)
    # =======================
    st.sidebar.header("🔎 Filter Data")

    # -----------------------
    # 1️⃣ PRODUK
    # -----------------------
    daftar_produk = (
        sorted(df_konsumen["PRODUK"].dropna().unique().tolist())
        if "PRODUK" in df_konsumen.columns else []
    )

    selected_produk = st.sidebar.multiselect(
        "Pilih Produk",
        daftar_produk,
        default=daftar_produk
    )

    if selected_produk:
        df_konsumen = df_konsumen[df_konsumen["PRODUK"].isin(selected_produk)]
    else:
        st.warning("Pilih minimal satu produk")
        st.stop()

    # -----------------------
    # 2️⃣ NAMA KANTOR
    # -----------------------
    daftar_kantor = (
        sorted(df_kantor["NAMA KANTOR"].dropna().unique().tolist())
        if "NAMA KANTOR" in df_kantor.columns else []
    )

    selected_kantor = st.sidebar.selectbox(
        "Pilih Nama Kantor",
        ["ALL"] + daftar_kantor
    )

    if selected_kantor != "ALL":
        df_kantor = df_kantor[df_kantor["NAMA KANTOR"] == selected_kantor]

    # -----------------------
    # 3️⃣ CABANG
    # -----------------------
    daftar_cabang = (
        sorted(df_kantor["CABANG"].dropna().unique().tolist())
        if "CABANG" in df_kantor.columns else []
    )

    selected_cabang = st.sidebar.multiselect(
        "Pilih Cabang",
        daftar_cabang,
        default=daftar_cabang
    )

    if selected_cabang:
        if "CABANG" in df_kantor.columns:
            df_kantor = df_kantor[df_kantor["CABANG"].isin(selected_cabang)]
    else:
        st.warning("Pilih minimal satu cabang")
        st.stop()

    # -----------------------
    # INFO SIDEBAR
    # -----------------------
    st.sidebar.markdown("---")
    st.sidebar.caption(f"📌 Konsumen: {len(df_konsumen):,}")
    st.sidebar.caption(f"🏢 Kantor: {len(df_kantor):,}")

    # =======================
    # VALIDASI DATA
    # =======================
    if df_konsumen.empty and df_kantor.empty:
        st.warning("Tidak ada data untuk filter yang dipilih")
        st.stop()

    # =======================
    # HEATMAP
    # =======================
    heat_df = df_konsumen[["lat", "lon"]]

    if len(heat_df) > MAX_HEAT_POINTS:
        heat_df = heat_df.sample(MAX_HEAT_POINTS, random_state=42)

    heat_points = heat_df.values.tolist()

    # =======================
    # KANTOR MARKER
    # =======================
    kantor_points = [
        {
            "loc": [row["lat"], row["lon"]],
            "popup": row.get("NAMA KANTOR", "Kantor")
        }
        for _, row in df_kantor.iterrows()
    ]

    # =======================
    # CENTER MAP
    # =======================
    if not df_kantor.empty:
        center_lat = df_kantor["lat"].mean()
        center_lon = df_kantor["lon"].mean()
    else:
        center_lat = df_konsumen["lat"].mean()
        center_lon = df_konsumen["lon"].mean()

    # =======================
    # BUILD MAP
    # =======================
    m = build_map(
        heat_points,
        kantor_points,
        center_lat,
        center_lon
    )

    st.subheader("🗺️ Peta Lokasi")
    st_folium(
        m,
        use_container_width=True,
        height=650,
        returned_objects=[]
    )

    col1, col2 = st.columns(2)
    col1.metric("Jumlah Konsumen", len(df_konsumen))

except Exception as e:
    st.error(f"Terjadi error: {e}")







