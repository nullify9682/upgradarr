#!/usr/bin/env python3
import requests
import time
import os
import sys
import random
import json
import yaml
from datetime import datetime

# === File Paths (Mapped via Docker Volume) ===
CONFIG_FILE = '/config/config.yml'
HISTORY_FILE = '/config/history.json'

def log(message):
    """Custom print function to include timestamp for Docker logs."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def create_default_config():
    """Generates a default config.yml file if it doesn't exist."""
    default_config = {
        'radarr': {
            'url': 'http://192.168.1.100:7878',
            'api_key': 'YOUR_RADARR_API_KEY_HERE'
        },
        'sonarr': {
            'url': 'http://192.168.1.100:8989',
            'api_key': 'YOUR_SONARR_API_KEY_HERE'
        },
        'settings': {
            'sleep_time': 300,
            'cache_duration': 86400
        }
    }
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(default_config, f, default_flow_style=False)
    log(f"[!] Created default config at {CONFIG_FILE}. Please edit it and restart.")
    sys.exit(0)

def load_config():
    """Loads the YAML configuration file."""
    if not os.path.exists(CONFIG_FILE):
        create_default_config()
        
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def load_history():
    """Loads the history from a JSON file to survive reboots."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('movies', [])), set(data.get('seasons', []))
        except Exception as e:
            log(f"[ERROR] Failed to load history: {e}")
    return set(), set()

def save_history(searched_movies, searched_seasons):
    """Saves the history sets to a JSON file."""
    try:
        data = {
            'movies': list(searched_movies),
            'seasons': list(searched_seasons)
        }
        with open(HISTORY_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log(f"[ERROR] Failed to save history: {e}")

def get_headers(api_key):
    return {'X-Api-Key': api_key}

def fetch_radarr_library(cfg):
    log("[*] Fetching movie library from Radarr...")
    try:
        resp = requests.get(f"{cfg['url']}/api/v3/movie", headers=get_headers(cfg['api_key']), timeout=30)
        resp.raise_for_status()
        movies = resp.json()
        pool = [{'id': m['id'], 'title': m['title']} for m in movies if m.get('monitored', False)]
        return pool
    except Exception as e:
        log(f"[ERROR] Failed to fetch Radarr library: {e}")
        return None # Return None instead of [] to indicate failure

def fetch_sonarr_library(cfg):
    log("[*] Fetching series library from Sonarr...")
    try:
        resp = requests.get(f"{cfg['url']}/api/v3/series", headers=get_headers(cfg['api_key']), timeout=30)
        resp.raise_for_status()
        series_list = resp.json()
        
        pool = []
        for series in series_list:
            if not series.get('monitored', False):
                continue
            for season in series.get('seasons', []):
                if season.get('monitored', False) and season.get('seasonNumber', 0) > 0:
                    pool.append({
                        'uid': f"{series['id']}_S{season['seasonNumber']}",
                        'series_id': series['id'],
                        'title': series['title'],
                        'season_num': season['seasonNumber']
                    })
        return pool
    except Exception as e:
        log(f"[ERROR] Failed to fetch Sonarr library: {e}")
        return None # Return None instead of [] to indicate failure

def trigger_radarr_search(movie, cfg):
    payload = {"name": "MoviesSearch", "movieIds": [movie['id']]}
    try:
        resp = requests.post(f"{cfg['url']}/api/v3/command", json=payload, headers=get_headers(cfg['api_key']), timeout=10)
        resp.raise_for_status()
        log(f"[RADARR] Search triggered for: {movie['title']}")
    except Exception as e:
        log(f"[RADARR-ERROR] Failed to search {movie['title']}: {e}")

def trigger_sonarr_search(season, cfg):
    payload = {"name": "SeasonSearch", "seriesId": season['series_id'], "seasonNumber": season['season_num']}
    try:
        resp = requests.post(f"{cfg['url']}/api/v3/command", json=payload, headers=get_headers(cfg['api_key']), timeout=10)
        resp.raise_for_status()
        log(f"[SONARR] Search triggered for: {season['title']} (Season {season['season_num']})")
    except Exception as e:
        log(f"[SONARR-ERROR] Failed to search {season['title']} S{season['season_num']}: {e}")

def main():
    log("=== Upgradarr: Random Library Searcher Started ===")
    config = load_config()
    
    sleep_time = config['settings'].get('sleep_time', 300)
    cache_duration = config['settings'].get('cache_duration', 86400)
    
    searched_movies, searched_seasons = load_history()
    log(f"[*] Loaded history: {len(searched_movies)} movies and {len(searched_seasons)} seasons previously searched.")
    
    movie_pool = []
    season_pool = []
    
    last_fetch_time = 0
    last_status_time = time.time()

    while True:
        current_time = time.time()
        
        # Hourly Status Update (3600 seconds)
        if current_time - last_status_time >= 3600:
            total_items_left = len(movie_pool) + len(season_pool)
            eta_seconds = total_items_left * sleep_time
            
            days, remainder = divmod(eta_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            
            eta_str = []
            if days > 0: eta_str.append(f"{days}d")
            if hours > 0: eta_str.append(f"{hours}h")
            eta_str.append(f"{minutes}m")
            formatted_eta = " ".join(eta_str) if eta_str else "0m"
            
            log(f"[STATUS] Remaining: {len(movie_pool)} movies | {len(season_pool)} seasons. ETA to finish cycle: ~{formatted_eta}.")
            last_status_time = current_time
        
        # Refresh Logic (Including Startup Check)
        if (current_time - last_fetch_time > cache_duration) or (last_fetch_time == 0):
            live_movies = fetch_radarr_library(config['radarr'])
            live_seasons = fetch_sonarr_library(config['sonarr'])
            
            # FAILSAFE: If either service is down, do not process, sleep and retry
            if live_movies is None or live_seasons is None:
                log("[WARNING] Could not connect to Radarr and/or Sonarr. Waiting 60s before retrying...")
                time.sleep(60)
                continue # Skip the rest of the loop and try again

            last_fetch_time = time.time()
            
            movie_pool = [m for m in live_movies if m['id'] not in searched_movies]
            season_pool = [s for s in live_seasons if s['uid'] not in searched_seasons]
            log(f"[*] Cycle initialized: {len(movie_pool)} movies and {len(season_pool)} seasons to search.")

        # Cycle Reset Logic
        if not movie_pool and not season_pool:
            if searched_movies or searched_seasons:
                log("[!] FULL LIBRARY CYCLE COMPLETED! Clearing history to start over.")
                searched_movies.clear()
                searched_seasons.clear()
                save_history(searched_movies, searched_seasons)
                
                movie_pool = [m for m in live_movies]
                season_pool = [s for s in live_seasons]
            else:
                log("[-] No monitored items available to search. Sleeping...")
                time.sleep(sleep_time)
                continue

        # Search Logic
        available_apps = []
        if movie_pool:
            available_apps.append('radarr')
        if season_pool:
            available_apps.append('sonarr')
            
        if available_apps:
            chosen_app = random.choice(available_apps)
            
            if chosen_app == 'radarr':
                random_index = random.randrange(len(movie_pool))
                selected_movie = movie_pool.pop(random_index)
                trigger_radarr_search(selected_movie, config['radarr'])
                searched_movies.add(selected_movie['id'])
            else:
                random_index = random.randrange(len(season_pool))
                selected_season = season_pool.pop(random_index)
                trigger_sonarr_search(selected_season, config['sonarr'])
                searched_seasons.add(selected_season['uid'])
                
            save_history(searched_movies, searched_seasons)
            
        time.sleep(sleep_time)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n[*] Script manually stopped by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        log(f"\n[CRITICAL ERROR] The script crashed: {e}")
        sys.exit(1)