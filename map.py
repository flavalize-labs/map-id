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
MAX_POINTS_ALL = 30000

# =======================
# HELPER
# =======================
def safe_fit_bounds(m, bounds):
    if not bounds:
        return
    (min_lat, min_lon), (max_lat, max_lon) = bounds
    if abs(max_lat - min_lat) < 1e-6 and abs(max_lon - min_lon) < 1e-6:
        return
    m.fit_bounds(bounds, padding=(30, 30))

def fit_bounds_from_points(m, points, padding=(60, 60), single_delta=0.15):
    # points: list of (lat, lon)
    if not points:
        return False
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # Kalau cuma 1 titik, bikin kotak kecil biar zoom masuk
    if abs(max_lat - min_lat) < 1e-6 and abs(max_lon - min_lon) < 1e-6:
        m.fit_bounds([[min_lat - single_delta, min_lon - single_delta],
                      [max_lat + single_delta, max_lon + single_delta]])
        return True

    m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], padding=padding)
    return True

# =======================
# LOAD DATA
# =======================
@st.cache_data(show_spinner=False)
def load_data():
    df_konsumen = pd.read_parquet("konsumen.parquet")
    df_kantor   = pd.read_parquet("kantor.parquet")
    df_mapping  = pd.read_parquet("mapping.parquet")
    return df_konsumen, df_kantor, df_mapping

# =======================
# INIT SESSION STATE (applied filters)
# =======================
if "applied_produk" not in st.session_state:
    st.session_state.applied_produk = "ALL"
if "applied_kantor_list" not in st.session_state:
    st.session_state.applied_kantor_list = []
if "applied_show_kantor" not in st.session_state:
    st.session_state.applied_show_kantor = True

# =======================
# APP
# =======================
st.set_page_config(page_title="Sebaran Konsumen per Kantor", layout="wide")
st.title("📍 Sebaran Konsumen per Kantor")

df_konsumen, df_kantor, df_mapping = load_data()

# =======================
# PREP OPTIONS
# =======================
produk_opsi = ["ALL"] + sorted(df_konsumen["PRODUK"].dropna().unique())

df_kantor_valid = df_kantor[
    df_kantor["NAMA KANTOR"].notna() &
    df_kantor["LAT"].notna() &
    df_kantor["LON"].notna()
].copy()

kantor_opsi = sorted(df_kantor_valid["NAMA KANTOR"].unique())

# =======================
# SIDEBAR FILTER (APPLY BUTTON VIA FORM)
# =======================
st.sidebar.header("🔎 Filter")

with st.sidebar.form("filter_form", clear_on_submit=False):
    selected_produk = st.selectbox(
        "Produk",
        produk_opsi,
        index=produk_opsi.index(st.session_state.applied_produk)
        if st.session_state.applied_produk in produk_opsi else 0
    )

    selected_kantor_list = st.multiselect(
        "Kantor (bisa pilih >1)",
        kantor_opsi,
        default=st.session_state.applied_kantor_list,
        help="Kosongkan untuk semua kantor"
    )

    show_kantor = st.toggle("Tampilkan titik kantor", value=st.session_state.applied_show_kantor)

    st.markdown("---")
    apply_clicked = st.form_submit_button("✅ Apply Filter")

# Update applied filters hanya saat tombol ditekan
if apply_clicked:
    st.session_state.applied_produk = selected_produk
    st.session_state.applied_kantor_list = selected_kantor_list
    st.session_state.applied_show_kantor = show_kantor

# Pakai yang sudah di-apply
selected_produk = st.session_state.applied_produk
selected_kantor_list = st.session_state.applied_kantor_list
show_kantor = st.session_state.applied_show_kantor

# =======================
# APPLY PRODUK FILTER
# =======================
if selected_produk != "ALL":
    df_konsumen = df_konsumen[df_konsumen["PRODUK"] == selected_produk]

# =======================
# META KANTOR
# =======================
kantor_meta = (
    df_kantor_valid[["NAMA KANTOR", "ID", "LAT", "LON"]]
    .drop_duplicates("NAMA KANTOR")
    .set_index("NAMA KANTOR")
    .to_dict("index")
)

kantor_id_to_name = (
    df_kantor_valid[["ID", "NAMA KANTOR"]]
    .assign(ID=lambda d: d["ID"].astype(str))
    .drop_duplicates("ID")
    .set_index("ID")["NAMA KANTOR"]
    .to_dict()
)

# =======================
# FILTER KONSUMEN (MULTI KANTOR)
# =======================
if selected_kantor_list:
    kantor_ids = [
        str(kantor_meta[k]["ID"])
        for k in selected_kantor_list
        if k in kantor_meta
    ]
    df_konsumen_plot_base = df_konsumen[
        df_konsumen["KANTOR_ID"].astype(str).isin(kantor_ids)
    ]
else:
    df_konsumen_plot_base = df_konsumen

# =======================
# METRIC
# =======================
st.sidebar.markdown("---")
st.sidebar.metric("Total Aplikasi", f"{df_konsumen_plot_base.shape[0]:,}")

# =======================
# MAP INIT (simple default; zoom akan ditentukan fit_bounds)
# =======================
m = folium.Map(
    location=[-2.5, 118.0],
    zoom_start=5,
    tiles="CartoDB positron"
)

# =======================
# COLOR MAP
# =======================
kantor_list = sorted(df_kantor_valid["NAMA KANTOR"].unique())
cmap = cm.get_cmap("tab20", max(1, len(kantor_list)))
warna_kantor = {k: mcolors.to_hex(cmap(i)) for i, k in enumerate(kantor_list)}

# =======================
# PREP DATA
# =======================
df_plot = df_konsumen_plot_base.copy()
df_plot["KANTOR_ID_STR"] = df_plot["KANTOR_ID"].astype(str)
df_plot["NAMA_KANTOR"] = df_plot["KANTOR_ID_STR"].map(kantor_id_to_name)
df_plot = df_plot[df_plot["NAMA_KANTOR"].notna()]

df_full = df_plot
df_map  = df_plot

# Sampling global hanya untuk mode ALL kantor (biar cepat)
if (not selected_kantor_list) and len(df_map) > MAX_POINTS_ALL:
    df_map = df_map.sample(MAX_POINTS_ALL, random_state=42)

# =======================
# DRAW KONSUMEN
# =======================
bounds_points = []
has_appid = "APPID" in df_map.columns

for kantor_name, df_k in df_map.groupby("NAMA_KANTOR"):
    if selected_kantor_list and kantor_name not in selected_kantor_list:
        continue

    # sampling per kantor untuk mode kantor spesifik (biar nggak berat)
    if selected_kantor_list and len(df_k) > MAX_POINTS_PER_KANTOR:
        df_k = df_k.sample(MAX_POINTS_PER_KANTOR, random_state=42)

    fg = FeatureGroup(name=f"📌 {kantor_name}")
    color = warna_kantor.get(kantor_name, "#3388ff")

    cols = ["lat", "lon", "CABANG"] + (["APPID"] if has_appid else [])
    for r in df_k[cols].itertuples(index=False):
        lat, lon, cabang, *appid = r

        CircleMarker(
            location=[lat, lon],
            radius=3,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.6,
            weight=0,
            tooltip=f"Cabang: {cabang}<br>APPID: {appid[0] if appid else '-'}"
        ).add_to(fg)

        bounds_points.append((lat, lon))

    fg.add_to(m)

# =======================
# MARKER KANTOR (SIDEBAR TOGGLE)
# =======================
kantor_points_for_zoom = []

if show_kantor:
    fg_kantor = FeatureGroup(name="🏢 Kantor (marker)", overlay=True, control=False, show=True)
    target_kantor = selected_kantor_list or kantor_opsi

    for k in target_kantor:
        if k in kantor_meta:
            km = kantor_meta[k]
            lat0, lon0 = float(km["LAT"]), float(km["LON"])
            kantor_points_for_zoom.append((lat0, lon0))

            folium.Marker(
                location=[lat0, lon0],
                popup=k,
                icon=folium.Icon(color="black", icon="building", prefix="fa")
            ).add_to(fg_kantor)

    fg_kantor.add_to(m)
else:
    # walaupun kantor disembunyikan, zoom tetap mau berdasarkan kantor yang dipilih
    if selected_kantor_list:
        for k in selected_kantor_list:
            if k in kantor_meta:
                km = kantor_meta[k]
                kantor_points_for_zoom.append((float(km["LAT"]), float(km["LON"])))

# =======================
# ZOOM RULES
# - Jika user pilih kantor -> zoom berdasarkan titik kantor terpilih
# - Jika ALL -> zoom berdasarkan titik konsumen (bounds_points)
# =======================
if selected_kantor_list and kantor_points_for_zoom:
    fit_bounds_from_points(m, kantor_points_for_zoom, padding=(60, 60), single_delta=0.15)
elif bounds_points:
    lats = [p[0] for p in bounds_points]
    lons = [p[1] for p in bounds_points]
    safe_fit_bounds(m, [[min(lats), min(lons)], [max(lats), max(lons)]])

# (Opsional) Layer control tetap boleh dipakai untuk layer konsumen per kantor
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
    key=f"map_{selected_produk}_{'_'.join(selected_kantor_list)}_{int(show_kantor)}"
)

# =======================
# LEGEND (TOP N)
# =======================
st.sidebar.markdown("---")
st.sidebar.subheader(f"🎨 Top {TOP_N_LEGEND} Kantor")

if df_full.empty:
    st.sidebar.caption("Tidak ada data.")
else:
    df_counts = (
        df_full.groupby("NAMA_KANTOR")
        .size()
        .reset_index(name="JUMLAH")
        .sort_values("JUMLAH", ascending=False)
    )

    if selected_kantor_list:
        df_counts = df_counts[df_counts["NAMA_KANTOR"].isin(selected_kantor_list)]

    df_counts["WARNA"] = df_counts["NAMA_KANTOR"].map(lambda k: warna_kantor.get(k, "#3388ff"))
    df_legend = df_counts.head(TOP_N_LEGEND)

    for _, r in df_legend.iterrows():
        st.sidebar.markdown(
            f"""
            <div style="display:flex; align-items:center; margin-bottom:6px;">
                <div style="width:12px;height:12px;background:{r['WARNA']};
                            margin-right:8px;border-radius:2px;"></div>
                <div style="font-size:13px;">
                    {r['NAMA_KANTOR']}<br>
                    <span style="opacity:0.8;">{int(r['JUMLAH']):,} aplikasi</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


