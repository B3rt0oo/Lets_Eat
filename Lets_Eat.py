# Demo code only — replace 'Your API KEY Here' with your actual Google Maps API key to run

import random
import time
import googlemaps

# Replace "YOUR_API_KEY_HERE" with your actual Google Maps API key to run
api_key = 'Your API KEY Here'
gmaps = googlemaps.Client(key=api_key)

# Predefined nearby ZIP codes for demo — random locations across the USA
nearby_zip_codes = [
    "10001",  # New York, NY
    "60601",  # Chicago, IL
    "90001",  # Los Angeles, CA
    "73301",  # Austin, TX
    "98101",  # Seattle, WA
]

def geocode_zip(zip_code):
    try:
        geocode_result = gmaps.geocode(zip_code)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return (location['lat'], location['lng'])
        else:
            print(f"Could not find location for ZIP code {zip_code}.")
            return None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None

def get_all_restaurants(location, radius=5000):
    restaurants = []
    next_page_token = None

    try:
        response = gmaps.places_nearby(location=location, radius=radius, type='restaurant')
        restaurants.extend(response.get('results', []))
        next_page_token = response.get('next_page_token')

        while next_page_token:
            time.sleep(2)  # Required delay for next_page_token
            response = gmaps.places_nearby(page_token=next_page_token)
            restaurants.extend(response.get('results', []))
            next_page_token = response.get('next_page_token')

            if len(restaurants) >= 60:  # API limit approx 60 results
                break

        return restaurants
    except Exception as e:
        print(f"Error fetching restaurants: {e}")
        return []

def decide_where_to_eat():
    user_zip = input("Please enter your ZIP code: ").strip()
    tried_zip_codes = set()
    suggested_place_ids = set()

    while True:
        if user_zip in tried_zip_codes:
            # Move to next nearby zip code automatically if available
            remaining_zips = [z for z in nearby_zip_codes if z not in tried_zip_codes]
            if not remaining_zips:
                print("No more nearby ZIP codes to search. Ending program.")
                break
            user_zip = remaining_zips[0]
            print(f"No more suggestions in previous area. Moving to nearby ZIP code: {user_zip}")

        loc = geocode_zip(user_zip)
        if not loc:
            print(f"Cannot get location for ZIP code {user_zip}. Try again.")
            user_zip = input("Please enter your ZIP code: ").strip()
            continue

        restaurants = get_all_restaurants(loc)
        if not restaurants:
            print(f"No restaurants found near ZIP code {user_zip}.")
            tried_zip_codes.add(user_zip)
            continue

        tried_zip_codes.add(user_zip)

        # Filter out already suggested places
        remaining = [r for r in restaurants if r['place_id'] not in suggested_place_ids]

        while remaining:
            choice = random.choice(remaining)
            print(f"How about {choice['name']}?")

            user_answer = input("Yes or No: ").strip().lower()
            if user_answer == "yes":
                print("Great! Enjoy your meal!")
                return
            elif user_answer == "no":
                suggested_place_ids.add(choice['place_id'])
                remaining = [r for r in remaining if r['place_id'] != choice['place_id']]
            else:
                print("Please answer with 'Yes' or 'No'.")

        # No more new suggestions in this zip; loop will automatically try next zip

decide_where_to_eat()
