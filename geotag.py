import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# 1. Baca file
df = pd.read_csv('alamat_geocode_ready.csv')

# 2. Siapkan geocoder
geolocator = Nominatim(user_agent="geo_app")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

# 3. Lakukan geocoding
def get_coordinates(address):
    try:
        location = geocode(address)
        if location:
            return pd.Series([location.latitude, location.longitude])
    except:
        pass
    return pd.Series([None, None])

# 4. Terapkan ke setiap alamat
df[['lat', 'lon']] = df['full_address'].apply(get_coordinates)

# 5. Simpan hasilnya
df.to_csv('alamat_dengan_koordinat.csv', index=False)

print("Selesai! File disimpan sebagai 'alamat_dengan_koordinat.csv'")
