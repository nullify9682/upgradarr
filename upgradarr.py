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

def calculate_eta(movie_count, season_count, sleep_time):
    """Calculates a human-readable ETA string."""
    total_items = movie_count + season_count
    eta_seconds = total_items * sleep_time
    
    days, remainder = divmod(eta_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    
    eta_parts = []
    if days > 0: eta_parts.append(f"{days}d")
    if hours > 0: eta_parts.append(f"{hours}h")
    eta_parts.append(f"{minutes}m")
    
    return " ".join(eta_parts) if eta_parts else "0m"

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
        data = {'movies': list(searched_movies), 'seasons': list(searched_seasons)}
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
        return [{'id': m['id'], 'title': m['title']} for m in movies if m.get('monitored', False)]
    except Exception as e:
        log(f"[ERROR] Failed to fetch Radarr library: {e}")
        return None

def fetch_sonarr_library(cfg):
    log("[*] Fetching series library from Sonarr...")
    try:
        resp = requests.get(f"{cfg['url']}/api/v3/series", headers=get_headers(cfg['api_key']), timeout=30)
        resp.raise_for_status()
        series_list = resp.json()
        pool = []
        for series in series_list:
            if not series.get('monitored', False): continue
            for season in series.get('seasons', []):
                if season.get('monitored', False) and season.get('seasonNumber', 0) > 0:
                    pool.append({'uid': f"{series['id']}_S{season['seasonNumber']}", 'series_id': series['id'], 'title': series['title'], 'season_num': season['seasonNumber']})
        return pool
    except Exception as e:
        log(f"[ERROR] Failed to fetch Sonarr library: {e}")
        return None

def trigger_radarr_search(movie, cfg):
    try:
        requests.post(f"{cfg['url']}/api/v3/command", json={"name": "MoviesSearch", "movieIds": [movie['id']]}, headers=get_headers(cfg['api_key']), timeout=10).raise_for_status()
        log(f"[RADARR] Search triggered for: {movie['title']}")
    except Exception as e:
        log(f"[RADARR-ERROR] Failed to search {movie['title']}: {e}")

def trigger_sonarr_search(season, cfg):
    try:
        requests.post(f"{cfg['url']}/api/v3/command", json={"name": "SeasonSearch", "seriesId": season['series_id'], "seasonNumber": season['season_num']}, headers=get_headers(cfg['api_key']), timeout=10).raise_for_status()
        log(f"[SONARR] Search triggered for: {season['title']} (Season {season['season_num']})")
    except Exception as e:
        log(f"[SONARR-ERROR] Failed to search {season['title']} S{season['season_num']}: {e}")

def main():
    log("=== Upgradarr: Random Library Searcher Started ===")
    config = load_config()
    sleep_time = config['settings'].get('sleep_time', 300)
    cache_duration = config['settings'].get('cache_duration', 86400)
    
    searched_movies, searched_seasons = load_history()
    if searched_movies or searched_seasons:
        log(f"[*] History recovered: {len(searched_movies)} movies and {len(searched_seasons)} seasons already searched in this cycle.")
    else:
        log("[*] No previous history found. Starting a fresh cycle.")
    
    movie_pool, season_pool = [], []
    m_list, s_list = [], []
    last_fetch_time, last_status_time = 0, time.time()

    while True:
        current_time = time.time()
        
        # Hourly Status Update
        if current_time - last_status_time >= 3600:
            eta = calculate_eta(len(movie_pool), len(season_pool), sleep_time)
            log(f"[STATUS] Progress: {len(movie_pool)} movies | {len(season_pool)} seasons left. ETA: ~{eta}")
            last_status_time = current_time

        # Refresh Logic (Including Startup Check)
        if (current_time - last_fetch_time > cache_duration) or (last_fetch_time == 0):
            m_list = fetch_radarr_library(config['radarr'])
            s_list = fetch_sonarr_library(config['sonarr'])
            
            if m_list is None or s_list is None:
                log("[WARNING] API Unreachable. Retrying in 60s...")
                time.sleep(60); continue
                
            last_fetch_time = current_time
            movie_pool = [m for m in m_list if m['id'] not in searched_movies]
            season_pool = [s for s in s_list if s['uid'] not in searched_seasons]
            
            # Initial ETA after sync
            initial_eta = calculate_eta(len(movie_pool), len(season_pool), sleep_time)
            log(f"[*] Sync complete: {len(movie_pool)} items remaining to search.")
            log(f"[*] Estimated time to finish current cycle: ~{initial_eta}")

        # Cycle Reset Logic
        if not movie_pool and not season_pool:
            if searched_movies or searched_seasons:
                log("[!] CYCLE COMPLETE! Resetting history."); searched_movies.clear(); searched_seasons.clear()
                save_history(searched_movies, searched_seasons)
                movie_pool, season_pool = [m for m in m_list], [s for s in s_list]
                reset_eta = calculate_eta(len(movie_pool), len(season_pool), sleep_time)
                log(f"[*] New cycle started. ETA: ~{reset_eta}")
            else:
                log("[-] No monitored items found. Checking again in 60s...")
                time.sleep(60); continue

        # Search Logic
        apps = ([('radarr', movie_pool)] if movie_pool else []) + ([('sonarr', season_pool)] if season_pool else [])
        if apps:
            app_type, pool = random.choice(apps)
            item = pool.pop(random.randrange(len(pool)))
            if app_type == 'radarr': trigger_radarr_search(item, config['radarr']); searched_movies.add(item['id'])
            else: trigger_sonarr_search(item, config['sonarr']); searched_seasons.add(item['uid'])
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