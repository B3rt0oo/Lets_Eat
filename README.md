# Let's Eat — ZIP-based Restaurant Picker

This script helps you decide where to eat by suggesting nearby restaurants from Google Places. It starts from your ZIP code and, when it runs out of suggestions, automatically advances to the next closest ZIP.

## Requirements
- Python 3.9+
- `googlemaps` Python package (`pip install googlemaps`)
- A Google Maps API key with Places and Geocoding APIs enabled

## Quick Start
```bash
# Install dependency
pip install googlemaps

# Provide your API key via env or flag
export GOOGLE_MAPS_API_KEY="<your-key>"

# Run with your ZIP
python Lets_Eat.py --zip 94105
```

## Examples
```bash
# Start from 94105, only open places, min 4.0 rating
python Lets_Eat.py --zip 94105 --open-now --min-rating 4.0

# Non-interactive: print a single suggestion and exit
python Lets_Eat.py --zip 10001 --non-interactive

# Use a keyword filter (e.g., sushi)
python Lets_Eat.py --zip 60601 --keyword sushi
```

## CLI Options
- `--api-key` string: API key (defaults to `$GOOGLE_MAPS_API_KEY`)
- `--zip` string: starting ZIP code (interactive prompt if omitted)
- `--radius` int: search radius in meters (default 5000)
- `--max-results` int: max results to fetch per ZIP (default 60)
- `--open-now`: only show places that are currently open
- `--min-rating` float: minimum rating filter (0–5)
- `--keyword` string: optional keyword (e.g., `sushi`, `tacos`)
- `--seed` int: RNG seed for reproducible choices
- `--non-interactive`: print one suggestion and exit

## How It Works
1. Geocodes your starting ZIP to latitude/longitude.
2. Fetches nearby restaurants via Places Nearby Search (with pagination).
3. Suggests places one by one, avoiding repeats and honoring filters.
4. When a ZIP is exhausted, it computes nearby ZIPs via reverse geocoding and moves to the next closest ZIP automatically.

## Troubleshooting
- Ensure billing is enabled on your Google Cloud project and the Places + Geocoding APIs are enabled.
- If you see no results, try increasing `--radius`, lowering `--min-rating`, or removing `--open-now`.
- Network or quota errors are printed to the console.

## Notes
- This script accesses Google APIs directly from your machine; your API key should be restricted in Google Cloud Console (HTTP referrers or IPs where appropriate).
- For production/mobile use, prefer routing requests through a backend to avoid exposing API keys.
