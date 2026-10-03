#!/bin/sh
set -u

# Jednorazowy przebieg przy starcie; błąd nie zatrzymuje kontenera.
python -m forecast.run --grid /app/web/data/grid.json --out /out/pogoda.json \
  || echo "forecast.run zakończony błędem (kod $?) - kontynuuję, cron ponowi próbę" >&2

exec /usr/local/bin/supercronic /app/forecast/crontab
