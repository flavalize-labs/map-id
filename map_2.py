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
# LOAD & PREP DATA
# =======================
@st.cache_data(show_spinner=False)
def load_and_prepare_data():
    df_konsumen = pd.read_excel("Data ZipCode.xlsx")
    df_kantor   = pd.read_excel("master_zip.xlsx", sheet_name="kantor")
    df_zip      = pd.read_excel("master_zip.xlsx", sheet_name="Sheet1")

    df_konsumen.columns = df_konsumen.columns.str.strip().str.upper()
    df_kantor.columns   = df_kantor.columns.str.strip().str.upper()
    df_zip.columns      = df_zip.columns.str.strip()

    # Parse tanggal (Indonesia)
    if "REALISASIDATE" in df_konsumen.columns:
        df_konsumen["REALISASIDATE"] = pd.to_datetime(
            df_konsumen["REALISASIDATE"], errors="coerce", dayfirst=True
        )
        df_konsumen = df_konsumen[df_konsumen["REALISASIDATE"].notna()]

    # Normalisasi KodePos
    if "KODEPOS" in df_konsumen.columns:
        df_konsumen["KODEPOS"] = normalize_postal_code(df_konsumen["KODEPOS"])

    if "postal_code" in df_zip.columns:
        df_zip["postal_code"] = normalize_postal_code(df_zip["postal_code"])

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

    # Normalisasi teks
    for col in ["PRODUK", "CABANG", "NAMA KANTOR"]:
        if col in df_konsumen.columns:
            df_konsumen[col] = df_konsumen[col].astype(str).str.strip().str.upper()
        if col in df_kantor.columns:
            df_kantor[col] = df_kantor[col].astype(str).str.strip().str.upper()

    return df_konsumen, df_kantor

# =======================
# BUILD MAP
# =======================
def build_map(heat_points, kantor_points, center_lat, center_lon, zoom):
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
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
# APP
# =======================
st.set_page_config(page_title="Peta Konsumen BCAF", layout="wide")
st.title("📍 Visualisasi Sebaran Konsumen BCAF")

try:
    df_konsumen_all, df_kantor_all = load_and_prepare_data()

    # =======================
    # FREEZE SCHEMA – KONSUMEN
    # =======================
    required_konsumen_cols = {
        "PRODUK",
        "CABANG",
        "KODEPOS",
        "lat",
        "lon"
    }

    missing_konsumen = required_konsumen_cols - set(df_konsumen_all.columns)

    if missing_konsumen:
        st.error(
            "❌ Struktur Data ZipCode.xlsx berubah.\n\n"
            f"Kolom wajib hilang: {', '.join(sorted(missing_konsumen))}"
        )
        st.stop()

    # =======================
    # FREEZE SCHEMA – KANTOR
    # =======================
    required_kantor_cols = {
        "NAMA KANTOR",
        "CABANG",
        "lat",
        "lon"
    }

    missing_kantor = required_kantor_cols - set(df_kantor_all.columns)

    if missing_kantor:
        st.error(
            "❌ Struktur sheet 'kantor' (master_zip.xlsx) berubah.\n\n"
            f"Kolom wajib hilang: {', '.join(sorted(missing_kantor))}"
        )
        st.stop()

    # =======================
    # SIDEBAR FILTER
    # =======================
    st.sidebar.header("🔎 Filter Data")

    # 1) PRODUK (filter konsumen)
    produk_opsi = ["ALL"] + sorted(df_konsumen_all["PRODUK"].dropna().unique())
    selected_produk = st.sidebar.selectbox("Pilih Produk", produk_opsi)

    df_konsumen = df_konsumen_all.copy()
    if selected_produk != "ALL":
        df_konsumen = df_konsumen[df_konsumen["PRODUK"] == selected_produk]

    # CABANG valid berdasar konsumen setelah filter produk
    cabang_valid_dari_konsumen = set(df_konsumen["CABANG"].dropna().unique().tolist()) if "CABANG" in df_konsumen.columns else set()

    # Kantor valid = kantor yang punya CABANG yg ada di konsumen (setelah filter produk)
    df_kantor_base = df_kantor_all.copy()
    if selected_produk != "ALL" and cabang_valid_dari_konsumen:
        df_kantor_base = df_kantor_base[df_kantor_base["CABANG"].isin(cabang_valid_dari_konsumen)]

    # 2) NAMA KANTOR (opsi hanya yang valid setelah produk)
    kantor_opsi = ["ALL"] + sorted(df_kantor_base["NAMA KANTOR"].dropna().unique())
    selected_kantor = st.sidebar.selectbox("Pilih Nama Kantor", kantor_opsi)

    df_kantor_lvl2 = df_kantor_base.copy()
    if selected_kantor != "ALL":
        df_kantor_lvl2 = df_kantor_lvl2[df_kantor_lvl2["NAMA KANTOR"] == selected_kantor]

        # ketika kantor dipilih, konsumen ikut dibatasi ke cabang kantor tsb
        cabang_kantor = df_kantor_lvl2["CABANG"].dropna().unique().tolist()
        if cabang_kantor:
            df_konsumen = df_konsumen[df_konsumen["CABANG"].isin(cabang_kantor)]

    # 3) CABANG (opsi hanya yang valid dari kantor terpilih & (kalau produk≠ALL) dari konsumen)
    cabang_opsi = ["ALL"] + sorted(df_kantor_lvl2["CABANG"].dropna().unique())
    selected_cabang = st.sidebar.selectbox(
        "Pilih Cabang",
        cabang_opsi,
        disabled=(selected_kantor == "ALL")
    )

    df_kantor_final = df_kantor_lvl2.copy()
    if selected_cabang != "ALL":
        df_kantor_final = df_kantor_final[df_kantor_final["CABANG"] == selected_cabang]
        df_konsumen = df_konsumen[df_konsumen["CABANG"] == selected_cabang]

    # =======================
    # SIDEBAR INFO
    # =======================
    st.sidebar.markdown("---")
    st.sidebar.metric("📌 Konsumen", f"{len(df_konsumen):,}")
    st.sidebar.metric("🏢 Kantor", f"{len(df_kantor_final):,}")

    # =======================
    # VALIDASI
    # =======================
    if df_konsumen.empty and df_kantor_final.empty:
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
        {"loc": [row["lat"], row["lon"]], "popup": row.get("NAMA KANTOR", "Kantor")}
        for _, row in df_kantor_final.iterrows()
    ]

    # =======================
    # AUTO CENTER & ZOOM
    # =======================
    if selected_cabang != "ALL" and not df_kantor_final.empty:
        center_lat = df_kantor_final["lat"].mean()
        center_lon = df_kantor_final["lon"].mean()
        zoom = 13
    elif selected_kantor != "ALL" and not df_kantor_lvl2.empty:
        center_lat = df_kantor_lvl2["lat"].mean()
        center_lon = df_kantor_lvl2["lon"].mean()
        zoom = 11
    else:
        center_lat = df_konsumen["lat"].mean()
        center_lon = df_konsumen["lon"].mean()
        zoom = 6

    # =======================
    # BUILD MAP
    # =======================
    m = build_map(heat_points, kantor_points, center_lat, center_lon, zoom)

    st.subheader("🗺️ Peta Lokasi")
    st_folium(
        m,
        use_container_width=True,
        height=650,
        returned_objects=[]
    )

except Exception as e:
    st.error(f"Terjadi error: {e}")










