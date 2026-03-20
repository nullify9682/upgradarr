#!/usr/bin/env python3
import requests
import time
import os
import sys
import random
from datetime import datetime

# === Configuration ===
RADARR_URL = os.getenv('RADARR_URL', 'http://localhost:7878').rstrip('/')
RADARR_API = os.getenv('RADARR_API_KEY', '')
SONARR_URL = os.getenv('SONARR_URL', 'http://localhost:8989').rstrip('/')
SONARR_API = os.getenv('SONARR_API_KEY', '')

# Pause in seconds between searches to avoid hitting API/indexer limits
SLEEP_TIME = int(os.getenv('SLEEP_TIME', 300)) # Default: 5 minutes
CACHE_DURATION = int(os.getenv('CACHE_DURATION', 24 * 60 * 60)) # 24 hours in seconds

if not all([RADARR_URL, RADARR_API, SONARR_URL, SONARR_API]):
    # Fallback to standard print here since we exit immediately
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Missing required environment variables", flush=True)
    sys.exit(1)

def log(message):
    """Custom print function to include timestamp for Docker logs."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def get_headers(api_key):
    return {'X-Api-Key': api_key}

def fetch_radarr_library():
    """Fetches all monitored movies from Radarr."""
    log("[*] Fetching movie library from Radarr...")
    try:
        resp = requests.get(f"{RADARR_URL}/api/v3/movie", headers=get_headers(RADARR_API), timeout=30)
        resp.raise_for_status()
        movies = resp.json()
        
        # Only keep monitored movies
        pool = [{'id': m['id'], 'title': m['title']} for m in movies if m.get('monitored', False)]
        log(f"[OK] Found {len(pool)} monitored movies in Radarr.")
        return pool
    except Exception as e:
        log(f"[ERROR] Failed to fetch Radarr library: {e}")
        return []

def fetch_sonarr_library():
    """Fetches all monitored series and parses their monitored seasons."""
    log("[*] Fetching series library from Sonarr...")
    try:
        resp = requests.get(f"{SONARR_URL}/api/v3/series", headers=get_headers(SONARR_API), timeout=30)
        resp.raise_for_status()
        series_list = resp.json()
        
        pool = []
        for series in series_list:
            if not series.get('monitored', False):
                continue
                
            # Extract only monitored seasons (excluding specials usually denoted by season 0)
            for season in series.get('seasons', []):
                if season.get('monitored', False) and season.get('seasonNumber', 0) > 0:
                    pool.append({
                        'uid': f"{series['id']}_S{season['seasonNumber']}", # Unique ID for sets
                        'series_id': series['id'],
                        'title': series['title'],
                        'season_num': season['seasonNumber']
                    })
                    
        log(f"[OK] Found {len(pool)} monitored seasons in Sonarr.")
        return pool
    except Exception as e:
        log(f"[ERROR] Failed to fetch Sonarr library: {e}")
        return []

def trigger_radarr_search(movie):
    """Triggers an automatic search for a specific movie in Radarr."""
    log(f"[RADARR] Selected movie: {movie['title']}")
    payload = {"name": "MoviesSearch", "movieIds": [movie['id']]}
    try:
        resp = requests.post(f"{RADARR_URL}/api/v3/command", json=payload, headers=get_headers(RADARR_API), timeout=10)
        resp.raise_for_status()
        log("     -> Search triggered successfully.")
    except Exception as e:
        log(f"     -> [ERROR] Failed to trigger search: {e}")

def trigger_sonarr_search(season):
    """Triggers an automatic search for a specific series season in Sonarr."""
    log(f"[SONARR] Selected series: {season['title']} (Season {season['season_num']})")
    payload = {"name": "SeasonSearch", "seriesId": season['series_id'], "seasonNumber": season['season_num']}
    try:
        resp = requests.post(f"{SONARR_URL}/api/v3/command", json=payload, headers=get_headers(SONARR_API), timeout=10)
        resp.raise_for_status()
        log("     -> Search triggered successfully.")
    except Exception as e:
        log(f"     -> [ERROR] Failed to trigger search: {e}")

def main():
    log("=== Random Library Upgrade Searcher Started ===")
    
    # Pools for the current run
    movie_pool = []
    season_pool = []
    
    # History sets to track what has already been searched in the current cycle
    searched_movies = set()
    searched_seasons = set()
    
    last_fetch_time = 0

    while True:
        current_time = time.time()
        
        # 1. Refresh logic (Every 24h or if pools are empty from the start)
        if (current_time - last_fetch_time > CACHE_DURATION) or (last_fetch_time == 0):
            log("="*50)
            log("[*] 24h timer reached or first run. Fetching updated libraries...")
            
            live_movies = fetch_radarr_library()
            live_seasons = fetch_sonarr_library()
            last_fetch_time = time.time()
            
            # Filter the live library against our history to rebuild the search pools
            movie_pool = [m for m in live_movies if m['id'] not in searched_movies]
            season_pool = [s for s in live_seasons if s['uid'] not in searched_seasons]
            
            log(f"[*] After filtering history: {len(movie_pool)} movies and {len(season_pool)} seasons left to search in this cycle.")
            log("="*50)

        # 2. Cycle Reset Logic
        # If both pools are empty after a refresh (meaning we searched the ENTIRE library over several days/weeks)
        if not movie_pool and not season_pool:
            if searched_movies or searched_seasons:
                log("[!] FULL LIBRARY CYCLE COMPLETED! Clearing history to start a new cycle.")
                searched_movies.clear()
                searched_seasons.clear()
                
                # Refill pools immediately
                movie_pool = [m for m in live_movies]
                season_pool = [s for s in live_seasons]
                log(f"[*] Cycle reset: Re-added {len(movie_pool)} movies and {len(season_pool)} seasons.")
            else:
                log("[-] No monitored items exist in Radarr or Sonarr at all. Sleeping...")
                time.sleep(SLEEP_TIME)
                continue

        # 3. Selection and Search Logic
        available_apps = []
        if movie_pool:
            available_apps.append('radarr')
        if season_pool:
            available_apps.append('sonarr')
            
        chosen_app = random.choice(available_apps)
        
        # Pop randomly, trigger search, and add to history
        if chosen_app == 'radarr':
            random_index = random.randrange(len(movie_pool))
            selected_movie = movie_pool.pop(random_index)
            trigger_radarr_search(selected_movie)
            searched_movies.add(selected_movie['id']) # Add to history
        else:
            random_index = random.randrange(len(season_pool))
            selected_season = season_pool.pop(random_index)
            trigger_sonarr_search(selected_season)
            searched_seasons.add(selected_season['uid']) # Add to history
            
        # log(f"[*] Pools remaining this cycle: {len(movie_pool)} movies, {len(season_pool)} seasons.")
        log(f"[*] Sleeping for {SLEEP_TIME} seconds before the next search...")
        time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n[*] Script manually stopped by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        log(f"\n[CRITICAL ERROR] The script crashed: {e}")
        sys.exit(1)