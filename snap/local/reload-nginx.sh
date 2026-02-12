#!/bin/sh
set -e

"$SNAP/usr/sbin/nginx" -c "$SNAP_DATA/nginx/nginx.conf" -s reload
