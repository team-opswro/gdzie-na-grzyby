#!/usr/bin/env bash
# Pobiera przypięte wersje bibliotek frontendu do web/vendor/ (wynik jest commitowany).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p web/vendor
MAPLIBRE=5.24.0
PMTILES=3.2.1
curl -fsSL "https://unpkg.com/maplibre-gl@${MAPLIBRE}/dist/maplibre-gl.js" -o web/vendor/maplibre-gl.js
curl -fsSL "https://unpkg.com/maplibre-gl@${MAPLIBRE}/dist/maplibre-gl.css" -o web/vendor/maplibre-gl.css
curl -fsSL "https://unpkg.com/pmtiles@${PMTILES}/dist/pmtiles.js" -o web/vendor/pmtiles.js
ls -l web/vendor
