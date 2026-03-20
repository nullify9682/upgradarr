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

## ⚙️ Environment Variables

You must configure the script using the following environment variables:

| Variable | Description | Required | Default |
| :--- | :--- | :---: | :--- |
| `RADARR_URL` | The full URL to your Radarr instance (e.g., `http://192.168.1.10:7878`). | **Yes** | `http://localhost:7878` |
| `RADARR_API_KEY` | Your Radarr API Key (found in Settings > General). | **Yes** | None |
| `SONARR_URL` | The full URL to your Sonarr instance (e.g., `http://192.168.1.10:8989`). | **Yes** | `http://localhost:8989` |
| `SONARR_API_KEY` | Your Sonarr API Key (found in Settings > General). | **Yes** | None |
| `SLEEP_TIME` | Time in seconds to pause between each search. | No | `300` (5 mins) |
| `CACHE_DURATION` | Time in seconds before refreshing the library list from the APIs. | No | `86400` (24h) |

---

## 🚀 Usage

You can run Upgradarr easily using Docker or Docker Compose. 

### Option 1: Docker Compose (Recommended)

Create a `docker-compose.yml` file and run `docker-compose up -d`:

```yaml
services:
  upgradarr:
    image: nullify9682
    container_name: upgradarr
    restart: unless-stopped
    environment:
      - RADARR_URL=[http://192.168.1.100:7878](http://192.168.1.100:7878)
      - RADARR_API_KEY=your_radarr_api_key_here
      - SONARR_URL=[http://192.168.1.100:8989](http://192.168.1.100:8989)
      - SONARR_API_KEY=your_sonarr_api_key_here
      - SLEEP_TIME=300
