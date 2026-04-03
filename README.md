# Upgradarr: Random Library Upgrade Searcher

Upgradarr is a lightweight Python script designed to slowly and methodically search for better releases (upgrades) across your entire Radarr and Sonarr libraries. 

If you have a massive library (e.g., 3000+ items), triggering a full search can result in API bans from your indexers or trackers. Upgradarr solves this by randomly picking one monitored movie or one monitored TV show season, searching for it, and then going to sleep. It uses a smart "Cycle" algorithm to ensure every single item in your library is checked once before it ever searches the same item again.

---

## ✨ Features

* **Smart Cycle Algorithm:** Keeps an in-memory history of what has already been searched. Once your entire library has been covered, it clears the history and starts a new cycle.
* **Daily Library Sync:** Automatically refreshes its internal list of your libraries every 24 hours to include newly added media and remove deleted ones.
* **Indexer Friendly:** Pauses for a configurable amount of time (default is 5 minutes) between searches to keep your tracker/indexer accounts safe.
* **Docker Ready:** Unbuffered, timestamped logs make it perfect for running in the background via Docker.

---

## ⚙️ Configuration (`config.yml`)

The script requires a `config.yml` file located in the `/config` volume of the container. If the file does not exist, the container will generate a default one and exit so you can fill it out.

### File Structure
```yaml
radarr:
  url: "[http://192.168.1.100:7878](http://192.168.1.100:7878)"  # The full URL to your Radarr instance
  api_key: "YOUR_RADARR_API_KEY"    # Found in Settings > General

sonarr:
  url: "[http://192.168.1.100:8989](http://192.168.1.100:8989)"  # The full URL to your Sonarr instance
  api_key: "YOUR_SONARR_API_KEY"    # Found in Settings > General

settings:
  sleep_time: 300       # Seconds to wait between each search (Default: 5 mins)
  cache_duration: 86400 # Seconds before refreshing the library list (Default: 24h)

---

## 🚀 Usage

You can run Upgradarr easily using Docker or Docker Compose. 

### Option 1: Docker Compose (Recommended)

Create a `docker-compose.yml` file and run `docker-compose up -d`:

```yaml
services:
  upgradarr:
    image: upgradarr:latest
    container_name: upgradarr
    restart: unless-stopped
    volumes:
      - ./config:/config
    environment:
      - PUID=1000         # The UID of the user owning the config folder
      - PGID=1000         # The GID of the user owning the config folder
      - TZ=Europe/Paris   # Sets the correct time for logs
