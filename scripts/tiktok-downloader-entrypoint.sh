#!/bin/sh
set -e
if [ -f /app/douyin-collection-server.py ]; then
  python /app/douyin-collection-server.py &
fi
exec python /app/main.py 7
