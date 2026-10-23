#Purpose: Background loop that checks local images every 24 hours.

#!/bin/sh

mkdir -p /reports /root/.cache

while true; do
  echo "[$(date)] Starting Synology container scan cycle..."

  docker images --format '{{.Repository}}:{{.Tag}}' | grep -v '<none>' | tr -d '\r' | while read -r img; do
    if [ -n "$img" ]; then
      safe_name=$(echo "$img" | sed 's|/|__|g' | sed 's/:/--/g')
      echo "Scanning $img..."

      trivy image --quiet --timeout 30m --format json --output "/tmp/${safe_name}.tmp" "$img" || {
        echo "Warning: Failed scanning $img. Continuing to next image..."
      }

      if [ -s "/tmp/${safe_name}.tmp" ] && jq -e '.SchemaVersion' "/tmp/${safe_name}.tmp" >/dev/null 2>&1; then
        mv -f "/tmp/${safe_name}.tmp" "/reports/${safe_name}.json"
        echo "Finished $img"
      else
        rm -f "/tmp/${safe_name}.tmp"
      fi
    fi
  done

  echo "[$(date)] Scan complete. Next run in 24 hours."
  sleep 86400
done
