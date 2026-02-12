#!/bin/sh
set -e

# Create writable directories for nginx
mkdir -p "$SNAP_DATA/nginx/body" \
         "$SNAP_DATA/nginx/proxy" \
         "$SNAP_DATA/nginx/fastcgi" \
         "$SNAP_DATA/nginx/uwsgi" \
         "$SNAP_DATA/nginx/scgi"

# Generate config from template if missing (safety net; configure hook normally handles this)
if [ ! -f "$SNAP_DATA/nginx/nginx.conf" ]; then
    PORT="$(snapctl get port)"
    PORT="${PORT:-80}"
    sed -e "s|@PORT@|${PORT}|g" \
        -e "s|@SNAP_DATA@|${SNAP_DATA}|g" \
        "$SNAP/templates/nginx.conf.template" > "$SNAP_DATA/nginx/nginx.conf"
fi

exec "$SNAP/usr/sbin/nginx" -c "$SNAP_DATA/nginx/nginx.conf" -g "daemon off;"
