FROM python:3.12-slim

# Install system dependencies for dynamic UID/GID and TZ support
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    passwd \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Create the user and group with default IDs
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m appuser

# Create config folder at root
RUN mkdir /config

WORKDIR /app
COPY upgradarr.py .
COPY requirements.txt .
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# Make entrypoint executable
RUN chmod +x /usr/local/bin/entrypoint.sh
RUN pip install --no-cache-dir -r requirements.txt

HEALTHCHECK --interval=1m --timeout=10s --start-period=30s --retries=3 \
  CMD test $(find /tmp/healthy -mmin -10) || exit 1

# Start as root to allow entrypoint.sh to change IDs
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]