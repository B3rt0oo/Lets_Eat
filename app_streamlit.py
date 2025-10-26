import math, os, time
from io import BytesIO
from typing import List, Optional, Sequence, Tuple
import requests, streamlit as st

# Compatibility helper for rerun across Streamlit versions
def _rerun():
    try:
        _rerun()
    except Exception:
        try:
            _rerun()
        except Exception:
            pass


try:
    import googlemaps
except Exception:
    googlemaps = None

LatLng = Tuple[float, float]

def build_client(api_key: str) -> "googlemaps.Client":
    if not api_key: raise ValueError("Missing API key")
    if googlemaps is None: raise RuntimeError("pip install googlemaps")
    return googlemaps.Client(key=api_key)

def geocode_zip(gmaps: "googlemaps.Client", zip_code: str) -> Optional[LatLng]:
    try:
        res = gmaps.geocode(zip_code)
        if not res: return None
        loc = res[0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
    except Exception:
        return None

def reverse_postal(gmaps: "googlemaps.Client", lat: float, lng: float) -> str:
    try:
        res = gmaps.reverse_geocode((lat, lng), result_type=["postal_code"])
        if not res: return ""
        for c in res[0].get("address_components", []):
            if "postal_code" in c.get("types", []):
                return c.get("long_name", "") or ""
        return ""
    except Exception:
        return ""

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R, p = 6371000.0, math.pi/180
    dlat, dlon = (lat2-lat1)*p, (lon2-lon1)*p
    a = math.sin(dlat/2)**2 + math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2
    return 2*R*math.atan2(math.sqrt(a), math.sqrt(1-a))

def nearby_zips(gmaps: "googlemaps.Client", center: LatLng, base_zip: str, max_count: int = 12) -> List[str]:
    lat, lng = center
    seen = set([base_zip]) if base_zip else set()
    candidates = {}
    for miles in (5.0, 10.0):
        dlat = miles/69.0
        dlon = miles/(69.0*max(math.cos(lat*math.pi/180), 0.0001))
        for la, lo in [(lat+dlat,lng),(lat-dlat,lng),(lat,lng+dlon),(lat,lng-dlon),
                       (lat+dlat,lng+dlon),(lat+dlat,lng-dlon),(lat-dlat,lng+dlon),(lat-dlat,lng-dlon)]:
            z = reverse_postal(gmaps, la, lo)
            if not z: continue
            d = haversine_m(lat,lng,la,lo)
            if z not in candidates or d < candidates[z]: candidates[z] = d
    ordered = [z for z,_ in sorted(candidates.items(), key=lambda kv: kv[1])]
    return ([base_zip] if base_zip else []) + [z for z in ordered if z not in seen][:max_count]

def places_nearby_pages(gmaps: "googlemaps.Client", *, location: LatLng, radius: int, open_now: Optional[bool], keyword: Optional[str], max_results: int) -> List[dict]:
    out, token = [], None
    try:
        resp = gmaps.places_nearby(location=location, radius=radius, type="restaurant", open_now=open_now, keyword=keyword)
        out.extend(resp.get("results", [])); token = resp.get("next_page_token")
        while token and len(out) < max_results:
            time.sleep(2); resp = gmaps.places_nearby(page_token=token)
            out.extend(resp.get("results", [])); token = resp.get("next_page_token")
    except Exception as e:
        st.warning(f"Places error: {e}")
    return out[:max_results]

def filter_unique_with_rating(rows: List[dict], min_rating: float) -> List[dict]:
    by_id = {}
    for r in rows:
        pid = r.get("place_id"); rating = float(r.get("rating") or 0)
        if not pid or rating < min_rating: continue
        by_id[pid] = r
    return list(by_id.values())

def weighted_choice(rows: Sequence[dict]) -> dict:
    import random
    ws = []
    for r in rows:
        try: ws.append(max(float(r.get("rating") or 1.0), 0.1))
        except: ws.append(1.0)
    return random.choices(list(rows), weights=ws, k=1)[0]

def photo_bytes(api_key: str, place: dict) -> Optional[bytes]:
    photos = place.get("photos") or []
    if not photos: return None
    ref = photos[0].get("photo_reference")
    if not ref: return None
    url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=900&photoreference={ref}&key={api_key}"
    try:
        r = requests.get(url, timeout=10)
        if r.ok: return r.content
    except Exception: pass
    return None

def static_map_bytes(api_key: str, place: dict) -> Optional[bytes]:
    geo = (place.get("geometry") or {}).get("location") or {}
    lat, lng = geo.get("lat"), geo.get("lng")
    if lat is None or lng is None: return None
    url = ("https://maps.googleapis.com/maps/api/staticmap"
           f"?center={lat},{lng}&zoom=15&size=640x320&scale=2&markers=color:red|{lat},{lng}&key={api_key}")
    try:
        r = requests.get(url, timeout=10)
        if r.ok: return r.content
    except Exception: pass
    return None

def describe_place(p: dict) -> str:
    name = p.get("name","<unknown>"); rating = p.get("rating"); rev = p.get("user_ratings_total")
    price = p.get("price_level"); addr = p.get("vicinity") or p.get("formatted_address") or ""
    price_str = "?" if price is None else "$"*int(price)
    bits = [name]
    if rating is not None: bits.append(f"{rating}★")
    if rev is not None: bits.append(f"({rev} reviews)")
    bits.append(price_str)
    if addr: bits.append(addr)
    return " — ".join(bits)

st.set_page_config(page_title="Let's Eat", page_icon="🍽️", layout="centered")
st.markdown("""
<style>
.fade-enter { animation: fadeIn 250ms ease-in; }
@keyframes fadeIn { from { opacity: .4; transform: translateY(6px) } to { opacity: 1; transform: translateY(0) } }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Let's Eat — Settings")
    api_key = st.text_input("Google Maps API key", type="password", value=getattr(st, "secrets", {}).get("GOOGLE_MAPS_API_KEY", os.environ.get("GOOGLE_MAPS_API_KEY", "")))
    zip_code = st.text_input("Starting ZIP", value=st.session_state.get("zip",""))
    colA, colB = st.columns(2)
    with colA:
        open_now = st.checkbox("Open now", value=st.session_state.get("open_now", False))
        min_rating = st.slider("Min rating", 0.0, 5.0, float(st.session_state.get("min_rating", 0.0)), 0.1)
    with colB:
        radius = st.number_input("Radius (m)", 500, 25000, int(st.session_state.get("radius", 5000)), 500)
        keyword = st.text_input("Keyword", value=st.session_state.get("keyword",""))
    if st.button("Start" if "started" not in st.session_state else "Restart", use_container_width=True):
        try: client = build_client(api_key)
        except Exception as e: st.error(f"API key error: {e}"); st.stop()
        loc = geocode_zip(client, zip_code.strip())
        if not loc: st.error(f"Could not geocode ZIP {zip_code}."); st.stop()
        zips = nearby_zips(client, loc, zip_code.strip(), max_count=16)
        st.session_state.update({
            "started": True, "api_key": api_key, "zip": zip_code.strip(),
            "zip_queue": zips[1:], "tried_zips": [], "suggested_ids": set(), "likes": [],
            "open_now": open_now, "min_rating": float(min_rating),
            "radius": int(radius), "keyword": keyword.strip() or None,
        })
        rows = places_nearby_pages(client, location=loc, radius=int(radius), open_now=open_now or None,
                                   keyword=keyword or None, max_results=60)
        st.session_state["places"] = filter_unique_with_rating(rows, float(min_rating))
        st.session_state["idx"] = 0
        _rerun()

def ensure_client() -> Optional["googlemaps.Client"]:
    key = st.session_state.get("api_key","")
    if not key: return None
    try: return build_client(key)
    except Exception: return None

def advance_zip():
    st.session_state["tried_zips"] = list(set(st.session_state.get("tried_zips",[])) | {st.session_state.get("zip")})
    queue = [z for z in st.session_state.get("zip_queue",[]) if z not in st.session_state["tried_zips"]]
    if not queue:
        client = ensure_client()
        if client and st.session_state.get("zip"):
            loc = geocode_zip(client, st.session_state["zip"])
            if loc:
                zips = nearby_zips(client, loc, st.session_state["zip"], max_count=16)
                queue = [z for z in zips[1:] if z not in st.session_state["tried_zips"]]
    if not queue:
        st.session_state["places"] = []; st.session_state["idx"] = 0; return False
    nxt = queue[0]; st.session_state["zip_queue"] = queue[1:]; st.session_state["zip"] = nxt
    client = ensure_client()
    if client:
        loc = geocode_zip(client, nxt)
        rows = places_nearby_pages(client, location=loc, radius=st.session_state["radius"],
                                   open_now=st.session_state["open_now"] or None,
                                   keyword=st.session_state["keyword"], max_results=60) if loc else []
        rows = filter_unique_with_rating(rows, st.session_state["min_rating"])
    else: rows = []
    st.session_state["places"] = rows; st.session_state["idx"] = 0; return True

st.title("Let's Eat 🍽️")
if not st.session_state.get("started"):
    st.info("Enter your API key and starting ZIP in the sidebar, then click Start."); st.stop()

places = st.session_state.get("places", []); idx = int(st.session_state.get("idx", 0))
likes = st.session_state.get("likes", []); suggested = st.session_state.get("suggested_ids", set())

if idx >= len(places):
    st.warning("No more suggestions in this ZIP.")
    if advance_zip(): st.success(f"Switched to next ZIP: {st.session_state.get('zip')}"); _rerun()
    else: st.error("No more nearby ZIP codes to search."); st.stop()

place = places[idx]; pid = place.get("place_id")
if pid in suggested: st.session_state["idx"] = idx + 1; _rerun()

st.markdown('<div class="fade-enter">', unsafe_allow_html=True)
img = photo_bytes(st.session_state["api_key"], place)
if img: st.image(BytesIO(img), use_container_width=True)
m = static_map_bytes(st.session_state["api_key"], place)
if m: st.image(BytesIO(m), use_container_width=True, caption="Map preview")
st.subheader(place.get("name","")); st.caption(describe_place(place))
col1, col2, col3 = st.columns([1,1,1])
with col1:
    if st.button("👎 Nope", use_container_width=True):
        suggested.add(pid); st.session_state["suggested_ids"] = suggested; st.session_state["idx"] = idx + 1; _rerun()
with col2: st.write(" ")
with col3:
    if st.button("👍 Like", use_container_width=True):
        suggested.add(pid); st.session_state["suggested_ids"] = suggested
        st.session_state["likes"] = likes + [place]; st.session_state["idx"] = idx + 1; _rerun()

with st.expander(f"Liked ({len(likes)})", expanded=False):
    for p in likes: st.write("• " + p.get("name",""))
