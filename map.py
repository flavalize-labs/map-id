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

def safe_fit_bounds(m, bounds):
    # bounds: [[min_lat, min_lon], [max_lat, max_lon]]
    if not bounds:
        return
    (min_lat, min_lon), (max_lat, max_lon) = bounds
    # Kalau bounds terlalu kecil (hampir titik), jangan fit_bounds (bisa zoom aneh)
    if abs(max_lat - min_lat) < 1e-6 and abs(max_lon - min_lon) < 1e-6:
        return
    m.fit_bounds(bounds, padding=(30, 30))

# =======================
# LOAD DATA (Optimized I/O)
# =======================
@st.cache_data(show_spinner=False)
def load_data():
    # --- Konsumen (baca sekali)
    df_konsumen = pd.read_excel(
        "Data ZipCode.xlsx",
        dtype={"KODEPOS": "string", "CABANG": "string", "PRODUK": "string"},
    )

    # --- Master zip (baca sekali, parse per sheet)
    xls = pd.ExcelFile("master_zip.xlsx")
    df_mapping = xls.parse("mapping", dtype={"CABANG": "string", "KANTOR_ID": "string"})
    df_kantor  = xls.parse("alamat")
    df_zip     = xls.parse("Sheet1", dtype={"postal_code": "string"})

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

    # Konsistensi teks
    for col in ["PRODUK", "CABANG"]:
        if col in df_konsumen.columns:
            df_konsumen[col] = df_konsumen[col].astype(str).str.strip().str.upper()

    if "CABANG" in df_mapping.columns:
        df_mapping["CABANG"] = df_mapping["CABANG"].astype(str).str.strip().str.upper()

    if "KANTOR_ID" in df_mapping.columns:
        df_mapping["KANTOR_ID"] = df_mapping["KANTOR_ID"].astype(str).str.strip()

    if "NAMA KANTOR" in df_kantor.columns:
        df_kantor["NAMA KANTOR"] = df_kantor["NAMA KANTOR"].astype(str).str.strip().str.upper()

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

    # Kantor (parsing koordinat robust)
    for col in ["LATITUDE", "LONGITUDE"]:
        if col in df_kantor.columns:
            df_kantor[col] = (
                df_kantor[col].astype(str)
                .str.strip()
                .str.replace(",", ".", regex=False)
                .str.replace(r"[^0-9\.\-]+", "", regex=True)
            )

    df_kantor["LAT"] = pd.to_numeric(df_kantor.get("LATITUDE"), errors="coerce")
    df_kantor["LON"] = pd.to_numeric(df_kantor.get("LONGITUDE"), errors="coerce")

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
produk_opsi = ["ALL"] + sorted(df_konsumen["PRODUK"].dropna().unique())
selected_produk = st.sidebar.selectbox("Produk", produk_opsi)

if selected_produk != "ALL":
    df_konsumen = df_konsumen[df_konsumen["PRODUK"] == selected_produk]

# ---- KANTOR ----
kantor_opsi = ["ALL"] + sorted(df_kantor["NAMA KANTOR"].dropna().unique())
selected_kantor = st.sidebar.selectbox("Kantor", kantor_opsi)

# =======================
# Optimasi utama: map CABANG -> KANTOR_ID sekali
# =======================
df_map2 = df_mapping[["CABANG", "KANTOR_ID"]].dropna().copy()
df_map2["CABANG"] = df_map2["CABANG"].astype(str).str.strip().str.upper()
df_map2["KANTOR_ID"] = df_map2["KANTOR_ID"].astype(str).str.strip()
df_map2 = df_map2.drop_duplicates(subset=["CABANG"])

df_konsumen = df_konsumen.merge(df_map2, on="CABANG", how="left")

# =======================
# Kantor valid untuk marker & meta (marker "pasti muncul" jika koordinat valid)
# =======================
df_kantor_valid = df_kantor[
    df_kantor["NAMA KANTOR"].notna() &
    df_kantor["LAT"].notna() &
    df_kantor["LON"].notna()
].copy()

# Lookup kantor -> {ID, LAT, LON}
kantor_meta = (
    df_kantor_valid[["NAMA KANTOR", "ID", "LAT", "LON"]]
    .drop_duplicates("NAMA KANTOR")
    .set_index("NAMA KANTOR")
    .to_dict("index")
)

# kantor_id -> nama kantor
kantor_id_to_name = (
    df_kantor_valid[["ID", "NAMA KANTOR"]]
    .assign(ID=lambda d: d["ID"].astype(str))
    .drop_duplicates("ID")
    .set_index("ID")["NAMA KANTOR"]
    .to_dict()
)

# =======================
# Filter konsumen untuk plotting (kalau pilih kantor)
# =======================
selected_kantor_id = None
if selected_kantor != "ALL":
    if selected_kantor in kantor_meta:
        selected_kantor_id = str(kantor_meta[selected_kantor]["ID"])
        df_konsumen_plot = df_konsumen[df_konsumen["KANTOR_ID"].astype(str) == selected_kantor_id]
    else:
        df_konsumen_plot = df_konsumen.iloc[0:0]  # kosong
else:
    df_konsumen_plot = df_konsumen

# =======================
# TOTAL APLIKASI (ikut filter produk + kantor)
# =======================
st.sidebar.markdown("---")
st.sidebar.metric("Total Aplikasi", f"{df_konsumen_plot.shape[0]:,}")

# =======================
# MAP INIT (auto-center & zoom saat pilih kantor)
# =======================
if selected_kantor != "ALL" and selected_kantor in kantor_meta:
    center_lat = float(kantor_meta[selected_kantor]["LAT"])
    center_lon = float(kantor_meta[selected_kantor]["LON"])
    zoom_start = 12
else:
    if not df_konsumen_plot.empty:
        center_lat = float(df_konsumen_plot["lat"].mean())
        center_lon = float(df_konsumen_plot["lon"].mean())
        zoom_start = 6
    else:
        center_lat, center_lon, zoom_start = -2.5, 118.0, 5  # fallback Indonesia

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=zoom_start,
    tiles="CartoDB positron"
)

# =======================
# COLOR MAP PER KANTOR (AUTO) - pakai kantor valid
# =======================
kantor_list = sorted(df_kantor_valid["NAMA KANTOR"].unique())
cmap_n = max(1, len(kantor_list))
cmap = cm.get_cmap("tab20", cmap_n)

warna_kantor = {kantor: mcolors.to_hex(cmap(i)) for i, kantor in enumerate(kantor_list)}

# =======================
# Siapkan nama kantor di konsumen_plot untuk grouping cepat
# =======================
df_konsumen_plot = df_konsumen_plot.copy()
df_konsumen_plot["KANTOR_ID_STR"] = df_konsumen_plot["KANTOR_ID"].astype(str)
df_konsumen_plot["NAMA_KANTOR"] = df_konsumen_plot["KANTOR_ID_STR"].map(kantor_id_to_name)
df_konsumen_plot = df_konsumen_plot[df_konsumen_plot["NAMA_KANTOR"].notna()]

# =======================
# SPEED UP: sampling global saat ALL
# =======================
if selected_kantor == "ALL" and len(df_konsumen_plot) > 30000:
    df_konsumen_plot = df_konsumen_plot.sample(30000, random_state=42)

# =======================
# DRAW KONSUMEN (lebih cepat: groupby kantor, itertuples, sample per kantor)
# =======================
bounds_points = []
has_appid = "APPID" in df_konsumen_plot.columns

for kantor_name, df_kons_k in df_konsumen_plot.groupby("NAMA_KANTOR"):
    if selected_kantor != "ALL" and kantor_name != selected_kantor:
        continue

    if len(df_kons_k) > MAX_POINTS_PER_KANTOR:
        df_kons_k = df_kons_k.sample(MAX_POINTS_PER_KANTOR, random_state=42)

    fg = FeatureGroup(name=kantor_name)
    color = warna_kantor.get(kantor_name, "#3388ff")

    cols = ["lat", "lon", "CABANG"] + (["APPID"] if has_appid else [])
    for r in df_kons_k[cols].itertuples(index=False):
        if has_appid:
            lat, lon, cabang, appid = r
        else:
            lat, lon, cabang = r
            appid = "-"

        CircleMarker(
            location=[lat, lon],
            radius=3,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.6,
            weight=0,
            tooltip=f"Cabang: {cabang}<br>APPID: {appid}"
        ).add_to(fg)

        bounds_points.append((lat, lon))

    fg.add_to(m)

# =======================
# MARKER KANTOR (pasti muncul jika koordinat valid)
# =======================
if selected_kantor != "ALL":
    if selected_kantor in kantor_meta:
        km = kantor_meta[selected_kantor]
        lat0, lon0 = float(km["LAT"]), float(km["LON"])

        folium.Marker(
            location=[lat0, lon0],
            popup=selected_kantor,
            icon=folium.Icon(color="black", icon="building", prefix="fa")
        ).add_to(m)

        # Paksa zoom dekat ke titik kantor (bukan ikut sebaran konsumen)
        delta = 0.45  # kamu bisa adjust: 0.02 lebih dekat, 0.05 lebih jauh
        m.fit_bounds([[lat0 - delta, lon0 - delta], [lat0 + delta, lon0 + delta]])

    else:
        st.warning(f"Koordinat kantor '{selected_kantor}' tidak valid / tidak ditemukan di sheet 'alamat'.")
else:
    # ALL: gambar semua kantor valid
    for _, row in df_kantor_valid.iterrows():
        folium.Marker(
            location=[row["LAT"], row["LON"]],
            popup=row["NAMA KANTOR"],
            icon=folium.Icon(color="black", icon="building", prefix="fa")
        ).add_to(m)

    # Auto zoom hanya untuk mode ALL (fit ke semua titik yang sudah kamu kumpulkan)
    if bounds_points:
        lats = [p[0] for p in bounds_points]
        lons = [p[1] for p in bounds_points]
        safe_fit_bounds(m, [[min(lats), min(lons)], [max(lats), max(lons)]])

    folium.LayerControl(collapsed=True).add_to(m)

# =======================
# RENDER MAP
# =======================
st.subheader("🗺️ Peta Sebaran Konsumen per Kantor")
st_folium(
    m,
    use_container_width=True,
    height=650,
    returned_objects=[],
    key=f"map_{selected_produk}_{selected_kantor}"  # <-- penting: key dinamis
)


# =======================
# SIDEBAR LEGEND (Top N) - cepat (groupby)
# =======================
st.sidebar.markdown("---")
st.sidebar.subheader(f"🎨 (Top {TOP_N_LEGEND})")

if df_konsumen_plot.empty:
    st.sidebar.caption("Tidak ada data untuk ditampilkan.")
else:
    df_counts = (
        df_konsumen_plot.groupby("NAMA_KANTOR")
        .size()
        .reset_index(name="JUMLAH")
        .sort_values("JUMLAH", ascending=False)
    )

    if selected_kantor != "ALL":
        df_counts = df_counts[df_counts["NAMA_KANTOR"] == selected_kantor]

    df_counts["WARNA"] = df_counts["NAMA_KANTOR"].map(lambda k: warna_kantor.get(k, "#3388ff"))
    df_legend = df_counts.head(TOP_N_LEGEND)

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
                        {row['NAMA_KANTOR']}<br>
                        <span style="opacity:0.8;">{int(row['JUMLAH']):,} aplikasi</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )