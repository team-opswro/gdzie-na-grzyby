#!/usr/bin/env bash
# Pobiera przypięte wersje bibliotek frontendu do web/vendor/ (wynik jest commitowany).
# Nazwy plików zawierają wersję: nginx serwuje /vendor/ jako immutable (rok), więc nowa wersja musi mieć
# nowy adres — po zmianie wersji zaktualizuj odwołania w web/index.html i SHELL_FILES w web/sw-core.js.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p web/vendor
MAPLIBRE=5.24.0
PMTILES=3.2.1
curl -fsSL "https://unpkg.com/maplibre-gl@${MAPLIBRE}/dist/maplibre-gl.js" -o "web/vendor/maplibre-gl-${MAPLIBRE}.js"
curl -fsSL "https://unpkg.com/maplibre-gl@${MAPLIBRE}/dist/maplibre-gl.css" -o "web/vendor/maplibre-gl-${MAPLIBRE}.css"
curl -fsSL "https://unpkg.com/pmtiles@${PMTILES}/dist/pmtiles.js" -o "web/vendor/pmtiles-${PMTILES}.js"
ls -l web/vendor
