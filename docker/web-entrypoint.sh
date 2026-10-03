#!/bin/sh
# Uruchamiany przez /docker-entrypoint.sh obrazu nginx (katalog /docker-entrypoint.d/).
# Generuje config.json i (w trybie proxy) fragment konfiguracji nginx z lokalizacją /dane/.
#
# Tryby:
# - brak DATA_BASE_URL          → dataBase "data/" (tryb lokalny), bez proxy;
# - DATA_BASE_URL, DATA_DIRECT≠1 → proxy: nginx przekazuje /dane/ do DATA_BASE_URL, dataBase "/dane/"
#                                  (ta sama domena — bucket nie potrzebuje reguły CORS);
# - DATA_BASE_URL, DATA_DIRECT=1 → przeglądarka czyta bucket wprost (wymaga reguły CORS na buckecie).
set -eu
out="${WEB_CONFIG_PATH:-/usr/share/nginx/html/config.json}"
proxy_conf="${WEB_PROXY_CONF:-/etc/nginx/dane.d/dane.conf}"
resolv_conf="${WEB_RESOLV_CONF:-/etc/resolv.conf}"
url="${DATA_BASE_URL:-}"
direct="${DATA_DIRECT:-}"

die() {
  printf '%s\n' "web-entrypoint: BŁĄD: $*" >&2
  exit 1
}

# Escape JSON: \ i " (znaki sterujące w URL nie występują — usuwamy je).
json_escape() {
  printf '%s' "$1" | tr -d '\000-\037' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

write_config() {
  esc=$(json_escape "$1")
  printf '{"dataBase":"%s"}\n' "$esc" > "$out"
  printf '%s\n' "web-entrypoint: config.json dataBase=$esc"
}

# Restart kontenera zachowuje system plików — usuwamy fragment z poprzedniego startu.
rm -f "$proxy_conf"

if [ -z "$url" ]; then
  write_config "data/"
  exit 0
fi

# Końcowy "/" (frontend też normalizuje).
case "$url" in */) ;; *) url="$url/" ;; esac

if [ "$direct" = "1" ]; then
  # Przeglądarka czyta bucket wprost ze strony HTTPS — tylko https:// (mixed content, javascript: itp.).
  case "$url" in
    https://?*) ;;
    *) die "DATA_BASE_URL przy DATA_DIRECT=1 musi zaczynać się od https:// (jest: $(json_escape "$url"))" ;;
  esac
  write_config "$url"
  exit 0
fi

# Proxy: URL trafia do konfiguracji nginx, więc dopuszczamy tylko bezpieczne znaki.
if ! printf '%s' "$url" | grep -Eq '^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~/-]*)?$' \
  || [ "$(printf '%s' "$url" | wc -l)" -ne 0 ]; then
  die "DATA_BASE_URL musi mieć postać https://host[/ścieżka/] (znaki A-Z a-z 0-9 . _ ~ / -); popraw zmienną albo ustaw DATA_DIRECT=1"
fi
rest="${url#https://}"
host="${rest%%/*}"
path="/${rest#*/}"
case "$host" in ''|.*|*.|*..*) die "DATA_BASE_URL: niepoprawny host" ;; esac

# Resolver DNS: nginx z proxy_pass przez zmienną rozwiązuje nazwę przy żądaniu (z cache valid=300s),
# a nie raz przy starcie — start bez DNS działa, zmiana IP bucketu nie wymaga restartu.
# Serwery nazw z resolv.conf (jak 15-local-resolvers.envsh obrazu nginx; IPv6 w nawiasach), awaryjnie publiczne.
resolvers=""
if [ -r "$resolv_conf" ]; then
  resolvers=$(awk '$1 == "nameserver" && $2 ~ /^[0-9A-Fa-f.:]+$/ {
    if ($2 ~ /:/) printf "[%s] ", $2; else printf "%s ", $2
  }' "$resolv_conf")
  resolvers="${resolvers% }"
fi
[ -n "$resolvers" ] || resolvers="1.1.1.1 8.8.8.8"

mkdir -p "$(dirname "$proxy_conf")"
tmp="$proxy_conf.tmp"
cat > "$tmp" <<EOF
# Wygenerowane przez web-entrypoint z DATA_BASE_URL — nie edytować.
# Dane z bucketu pod tą samą domeną co strona (bez CORS na buckecie).
location ^~ /dane/ {
    limit_except GET { deny all; }
    resolver $resolvers valid=300s ipv6=off;
    resolver_timeout 5s;
    set \$dane_host "$host";
    # /dane/<plik>?<arg> -> https://<host><ścieżka><plik>?<arg> (argumenty zachowane).
    rewrite ^/dane/(.*)\$ $path\$1 break;
    proxy_pass https://\$dane_host;
    proxy_http_version 1.1;
    proxy_set_header Host \$dane_host;
    proxy_set_header Connection "";
    proxy_set_header Cookie "";
    proxy_set_header Authorization "";
    proxy_ssl_server_name on;
    proxy_ssl_name \$dane_host;
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
    proxy_ssl_verify_depth 3;
    proxy_connect_timeout 5s;
    proxy_read_timeout 30s;
    proxy_send_timeout 30s;
    proxy_buffering on;
    # Duże odpowiedzi (lasy.pmtiles bez Range) strumieniowane, nie buforowane na dysk.
    proxy_max_temp_file_size 0;
    proxy_hide_header Set-Cookie;
    proxy_ignore_headers Set-Cookie;
    # JSON w buckecie jest już skompresowany (Content-Encoding: gzip) — bez drugiej kompresji.
    gzip off;
}
EOF
mv "$tmp" "$proxy_conf"
write_config "/dane/"
printf '%s\n' "web-entrypoint: proxy /dane/ -> https://$host$path (resolver: $resolvers)"
