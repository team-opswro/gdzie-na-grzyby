FROM python:3.12-slim

ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.33
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
 && ARCH="${TARGETARCH:-}" \
 && if [ -z "$ARCH" ]; then case "$(uname -m)" in aarch64|arm64) ARCH=arm64 ;; *) ARCH=amd64 ;; esac; fi \
 && curl -fsSL -o /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${ARCH}" \
 && chmod +x /usr/local/bin/supercronic \
 && apt-get purge -y --auto-remove curl \
 && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Warsaw \
    STATE_DIR=/state \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY forecast/requirements.txt forecast/requirements.txt
RUN pip install --no-cache-dir -r forecast/requirements.txt

COPY species.yaml species.yaml
COPY schema schema
COPY forecast forecast
RUN chmod +x forecast/entrypoint.sh && mkdir -p /state

HEALTHCHECK --interval=1h --timeout=10s --start-period=15m --start-interval=30s --retries=1 \
  CMD python -m forecast.healthcheck
ENTRYPOINT ["/app/forecast/entrypoint.sh"]
