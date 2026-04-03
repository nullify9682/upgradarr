#!/bin/sh

# Set Timezone
if [ -n "$TZ" ]; then
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
fi

# Adjust PUID/PGID of appuser
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Updating appuser UID to $PUID and GID to $PGID..."
groupmod -o -g "$PGID" appgroup
usermod -o -u "$PUID" appuser

# Ensure /config and /app are owned by the current PUID/PGID
chown -R appuser:appgroup /config /app

# Drop privileges and run the python script
exec gosu appuser python3 upgradarr.py