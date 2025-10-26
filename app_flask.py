from flask import Flask, jsonify, render_template, request, session
import os, math, time, secrets, requests
try:
    import googlemaps
except Exception:
    googlemaps = None

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(16))

def build_client():
    key = request.args.get("api_key") or session.get("api_key") or os.getenv("GOOGLE_MAPS_API_KEY","")
    if not key: raise RuntimeError("Missing API key")
    if googlemaps is None: raise RuntimeError("pip install googlemaps")
    session["api_key"] = key
    return googlemaps.Client(key=key)

def geocode_zip(client, zip_code):
    try:
        res = client.geocode(zip_code)
        if not res: return None
        loc = res[0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])    
    except Exception: return None

def reverse_postal(client, lat, lng):
    try:
        res = client.reverse_geocode((lat,lng), result_type=["postal_code"]) 
        if not res: return ""
        for c in res[0].get("address_components", []):
            if "postal_code" in c.get("types", []):
                return c.get("long_name", "") or ""
        return ""
    except Exception: return ""

def haversine_m(lat1, lon1, lat2, lon2):
    R, p = 6371000.0, math.pi/180
    dlat, dlon = (lat2-lat1)*p, (lon2-lon1)*p
    a = math.sin(dlat/2)**2 + math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2
    return 2*R*math.atan2(math.sqrt(a), math.sqrt(1-a))

def nearby_zips(client, center, base_zip, max_count=12):
    lat, lng = center
    seen = set([base_zip]) if base_zip else set()
    candidates = {}
    for miles in (5.0, 10.0):
        dlat = miles/69.0
        dlon = miles/(69.0*max(math.cos(lat*math.pi/180), 0.0001))
        for la, lo in [(lat+dlat,lng),(lat-dlat,lng),(lat,lng+dlon),(lat,lng-dlon),
                       (lat+dlat,lng+dlon),(lat+dlat,lng-dlon),(lat-dlat,lng+dlon),(lat-dlat,lng-dlon)]:
            z = reverse_postal(client, la, lo)
            if not z: continue
            d = haversine_m(lat,lng,la,lo)
            if z not in candidates or d < candidates[z]:
                candidates[z] = d
    ordered = [z for z,_ in sorted(candidates.items(), key=lambda kv: kv[1])]
    return ([base_zip] if base_zip else []) + [z for z in ordered if z not in seen][:max_count]

def places_nearby_pages(client, *, location, radius, open_now, keyword, max_results=60):
    out, token = [], None
    try:
        resp = client.places_nearby(location=location, radius=radius, type="restaurant", open_now=open_now, keyword=keyword)
        out.extend(resp.get("results", [])); token = resp.get("next_page_token")
        while token and len(out) < max_results:
            time.sleep(2); resp = client.places_nearby(page_token=token)
            out.extend(resp.get("results", [])); token = resp.get("next_page_token")
    except Exception as e:
        app.logger.warning("places error: %s", e)
    return out[:max_results]

def filter_unique_with_rating(rows, min_rating):
    by_id = {}
    for r in rows:
        pid = r.get("place_id"); rating = float(r.get("rating") or 0)
        if not pid or rating < min_rating: continue
        by_id[pid] = r
    return list(by_id.values())

@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/start")
def api_start():
    args = request.args
    zip_code = (args.get("zip") or "").strip()
    radius = int(args.get("radius") or 5000)
    min_rating = float(args.get("min_rating") or 0.0)
    open_now = args.get("open_now") == "true"
    keyword = args.get("keyword") or None
    client = build_client()
    loc = geocode_zip(client, zip_code)
    if not loc:
        return jsonify({"error":"invalid_zip"}), 400
    rows = places_nearby_pages(client, location=loc, radius=radius, open_now=open_now or None, keyword=keyword, max_results=60)
    rows = filter_unique_with_rating(rows, min_rating)
    zips = nearby_zips(client, loc, zip_code, max_count=16)
    session.update({
        "deck": rows, "idx": 0, "suggested": set(), "likes": [],
        "zip": zip_code, "zip_queue": zips[1:], "tried_zips": [],
        "radius": radius, "min_rating": min_rating, "open_now": open_now, "keyword": keyword,
    })
    return jsonify({"ok": True})

@app.get("/api/next")
def api_next():
    # If deck exhausted, try auto-advance to next ZIP
    def refill_from_next_zip():
        tried = set(session.get("tried_zips", [])) | {session.get("zip")}
        queue = [z for z in session.get("zip_queue", []) if z not in tried]
        if not queue:
            # try recomputing once
            client = build_client()
            curr = session.get("zip")
            if curr:
                loc = geocode_zip(client, curr)
                if loc:
                    zips = nearby_zips(client, loc, curr, max_count=16)
                    queue = [z for z in zips[1:] if z not in tried]
        if not queue:
            return False
        nxt = queue[0]
        session["zip_queue"] = queue[1:]
        session["tried_zips"] = list(tried)
        session["zip"] = nxt
        client = build_client()
        loc = geocode_zip(client, nxt)
        if not loc:
            return False
        rows = places_nearby_pages(client, location=loc, radius=int(session.get("radius",5000)), open_now=session.get("open_now") or None, keyword=session.get("keyword"), max_results=60)
        rows = filter_unique_with_rating(rows, float(session.get("min_rating",0)))
        session["deck"] = rows
        session["idx"] = 0
        session["suggested"] = set()
        return True

    deck = session.get("deck", []); idx = int(session.get("idx", 0))
    sugg = set(session.get("suggested", []))
    while idx < len(deck) and (deck[idx].get("place_id") in sugg):
        idx += 1
    if idx >= len(deck):
        if refill_from_next_zip():
            deck = session.get("deck", []); idx = int(session.get("idx", 0))
        else:
            return jsonify({"done": True})
    session["idx"] = idx + 1
    p = deck[idx]
    info = {
        "id": p.get("place_id"), "name": p.get("name"), "rating": p.get("rating"),
        "reviews": p.get("user_ratings_total"), "price": p.get("price_level"),
        "address": p.get("vicinity") or p.get("formatted_address"),
        "photo_ref": (p.get("photos") or [{}])[0].get("photo_reference"),
        "lat": ((p.get("geometry") or {}).get("location") or {}).get("lat"),
        "lng": ((p.get("geometry") or {}).get("location") or {}).get("lng"),
        "zip": session.get("zip"),
    }
    return jsonify(info)

@app.post("/api/swipe")
def api_swipe():
    data = request.get_json(force=True)
    pid = data.get("id"); direction = data.get("dir")  # "left" or "right"
    sugg = set(session.get("suggested", []))
    if pid: sugg.add(pid)
    session["suggested"] = list(sugg)
    if direction == "right":
        likes = list(session.get("likes", []))
        likes.append(pid); session["likes"] = likes
    return jsonify({"ok": True})

@app.get("/api/photo")
def api_photo():
    key = session.get("api_key")
    ref = request.args.get("ref"); width = request.args.get("w","900")
    if not (key and ref): return ("", 404)
    url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={width}&photoreference={ref}&key={key}"
    r = requests.get(url, stream=True, timeout=10)
    return (r.content, r.status_code, {"Content-Type": r.headers.get("Content-Type","image/jpeg")})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
