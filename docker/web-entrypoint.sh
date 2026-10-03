#!/bin/sh
# Uruchamiany przez /docker-entrypoint.sh obrazu nginx (katalog /docker-entrypoint.d/).
# Generuje config.json z DATA_BASE_URL; brak zmiennej → "data/" (tryb lokalny bez bucketu).
set -eu
out="${WEB_CONFIG_PATH:-/usr/share/nginx/html/config.json}"
base="${DATA_BASE_URL:-data/}"
# Końcowy "/" (frontend też normalizuje).
case "$base" in */) ;; *) base="$base/" ;; esac
# Escape JSON: \ i " (znaki sterujące w URL nie występują — usuwamy je).
esc=$(printf '%s' "$base" | tr -d '\000-\037' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
printf '{"dataBase":"%s"}\n' "$esc" > "$out"
echo "web-entrypoint: config.json dataBase=$esc"
