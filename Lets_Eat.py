#!/usr/bin/env python3
# Demo code — set GOOGLE_MAPS_API_KEY or pass --api-key
import argparse
import math
import os
import random
import time
from typing import List, Optional, Sequence, Tuple

try:
    import googlemaps
    from googlemaps.exceptions import ApiError, TransportError, Timeout
except Exception:
    googlemaps = None  # type: ignore
    ApiError = TransportError = Timeout = Exception  # type: ignore

LatLng = Tuple[float, float]

def build_client(api_key: str) -> "googlemaps.Client":
    if not api_key:
        raise ValueError("Missing API key. Pass --api-key or set GOOGLE_MAPS_API_KEY.")
    if googlemaps is None:
        raise RuntimeError("googlemaps package not installed. Run: pip install googlemaps")
    return googlemaps.Client(key=api_key)

def geocode_zip(gmaps: "googlemaps.Client", zip_code: str) -> Optional[LatLng]:
    try:
        res = gmaps.geocode(zip_code)
        if not res:
            return None
        loc = res[0]["geometry"]["location"]
        return (float(loc["lat"]), float(loc["lng"]))
    except Exception:
        return None

def reverse_postal(gmaps: "googlemaps.Client", lat: float, lng: float) -> str:
    try:
        res = gmaps.reverse_geocode((lat, lng), result_type=["postal_code"]) 
        if not res:
            return ""
        comps = res[0].get("address_components", [])
        for c in comps:
            if "postal_code" in c.get("types", []):
                return c.get("long_name", "") or ""
        return ""
    except Exception:
        return ""

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p = math.pi / 180
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = math.sin(dlat/2)**2 + math.cos(lat1*p) * math.cos(lat2*p) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def nearby_zips(gmaps: "googlemaps.Client", center: LatLng, base_zip: str, max_count: int = 12) -> List[str]:
    lat, lng = center
    out = []
    seen = set([base_zip]) if base_zip else set()
    candidates = {}
    for miles in (5.0, 10.0):
        dlat = miles / 69.0
        dlon = miles / (69.0 * max(math.cos(lat * math.pi/180), 0.0001))
        offsets = [
            (lat + dlat, lng), (lat - dlat, lng),
            (lat, lng + dlon), (lat, lng - dlon),
            (lat + dlat, lng + dlon), (lat + dlat, lng - dlon), (lat - dlat, lng + dlon), (lat - dlat, lng - dlon),
        ]
        for (la, lo) in offsets:
            z = reverse_postal(gmaps, la, lo)
            if not z:
                continue
            d = haversine_m(lat, lng, la, lo)
            if z not in candidates or d < candidates[z]:
                candidates[z] = d
    ranked = sorted(candidates.items(), key=lambda kv: kv[1])
    for z, _ in ranked:
        if z in seen:
            continue
        out.append(z)
        seen.add(z)
        if len(out) >= max_count:
            break
    return ([base_zip] if base_zip else []) + out

def places_nearby_pages(gmaps: "googlemaps.Client", *, location: LatLng, radius: int, open_now: Optional[bool], keyword: Optional[str], max_results: int) -> List[dict]:
    results: List[dict] = []
    token = None
    try:
        resp = gmaps.places_nearby(location=location, radius=radius, type="restaurant", open_now=open_now, keyword=keyword)
        results.extend(resp.get("results", []))
        token = resp.get("next_page_token")
        while token and len(results) < max_results:
            time.sleep(2)
            resp = gmaps.places_nearby(page_token=token)
            results.extend(resp.get("results", []))
            token = resp.get("next_page_token")
            if len(results) >= max_results:
                break
    except (ApiError, TransportError, Timeout) as e:
        print(f"Error fetching restaurants: {e}")
    except Exception as e:
        print(f"Unexpected error fetching restaurants: {e}")
    return results[:max_results]

def filter_unique_with_rating(rows: List[dict], min_rating: float) -> List[dict]:
    by_id = {}
    for r in rows:
        pid = r.get("place_id")
        if not pid:
            continue
        rating = float(r.get("rating") or 0)
        if rating < min_rating:
            continue
        by_id[pid] = r
    return list(by_id.values())

def weighted_choice(restaurants: Sequence[dict]) -> dict:
    weights = []
    for r in restaurants:
        try:
            w = float(r.get("rating") or 1.0)
        except Exception:
            w = 1.0
        weights.append(max(w, 0.1))
    return random.choices(list(restaurants), weights=weights, k=1)[0]

def describe_place(p: dict) -> str:
    name = p.get("name", "<unknown>")
    rating = p.get("rating")
    reviews = p.get("user_ratings_total")
    price = p.get("price_level")
    addr = p.get("vicinity") or p.get("formatted_address") or ""
    price_str = "?" if price is None else "$" * int(price)
    parts = [name]
    if rating is not None: parts.append(f"{rating}★")
    if reviews is not None: parts.append(f"({reviews} reviews)")
    parts.append(price_str)
    if addr: parts.append(addr)
    return " — ".join(parts)

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Find a place to eat; auto-advance to nearby ZIPs when exhausted.")
    p.add_argument("--api-key", default=os.getenv("GOOGLE_MAPS_API_KEY"), help="Google Maps API key")
    p.add_argument("--zip", dest="zip_code", default=None, help="Starting ZIP code")
    p.add_argument("--radius", type=int, default=5000, help="Search radius in meters")
    p.add_argument("--max-results", type=int, default=60, help="Max results to fetch per ZIP")
    p.add_argument("--open-now", action="store_true", help="Only places currently open")
    p.add_argument("--min-rating", type=float, default=0.0, help="Minimum rating filter (0-5)")
    p.add_argument("--keyword", type=str, default=None, help="Optional keyword (e.g., sushi)")
    p.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    p.add_argument("--non-interactive", action="store_true", help="Print a single suggestion and exit")
    return p.parse_args(argv)

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.seed is not None:
        random.seed(args.seed)
    try:
        client = build_client(args.api_key)
    except Exception as e:
        print(f"ERROR: {e}")
        return 2

    base_zip = args.zip_code or input("Enter your ZIP code: ").strip()
    loc = geocode_zip(client, base_zip)
    if not loc:
        print(f"Could not geocode ZIP {base_zip}.")
        return 1

    zip_list = nearby_zips(client, loc, base_zip, max_count=16)
    tried_zips = set()
    suggested_ids = set()

    def load_zip(z: str) -> List[dict]:
        ll = geocode_zip(client, z)
        if not ll:
            return []
        rows = places_nearby_pages(
            client,
            location=ll,
            radius=args.radius,
            open_now=args.open_now or None,
            keyword=args.keyword,
            max_results=args.max_results,
        )
        return filter_unique_with_rating(rows, args.min_rating)

    if args.non_interactive:
        results = load_zip(zip_list[0]) if zip_list else []
        if not results:
            print("No restaurants found.")
            return 1
        print(describe_place(weighted_choice(results)))
        return 0

    zip_idx = 0
    while zip_idx < len(zip_list):
        z = zip_list[zip_idx]
        if z in tried_zips:
            zip_idx += 1
            continue
        tried_zips.add(z)
        restaurants = [r for r in load_zip(z) if r.get("place_id") not in suggested_ids]
        if not restaurants:
            print(f"No restaurants found near ZIP {z}. Trying next closest ZIP...")
            zip_idx += 1
            continue

        remaining = restaurants[:]
        while remaining:
            choice = weighted_choice(remaining)
            print(f"How about: {describe_place(choice)}")
            ans = input("Yes / No / Details / Quit [y/n/d/q]: ").strip().lower()
            if ans in ("y", "yes"):
                print("Great! Enjoy your meal!")
                return 0
            if ans in ("q", "quit"):
                print("Goodbye!")
                return 0
            if ans in ("d", "detail", "details"):
                print(choice)
                continue
            suggested_ids.add(choice.get("place_id"))
            remaining = [r for r in remaining if r.get("place_id") not in suggested_ids]

        print(f"No more suggestions in {z}. Moving to the next closest ZIP...")
        zip_idx += 1

    print("No more nearby ZIP codes to search. Goodbye!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
