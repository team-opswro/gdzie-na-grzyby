FROM python:3.12-slim

ARG TIPPECANOE_TAG=2.79.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential git ca-certificates libsqlite3-dev zlib1g-dev \
 && git clone --depth 1 --branch ${TIPPECANOE_TAG} https://github.com/felt/tippecanoe.git /tmp/tippecanoe \
 && make -C /tmp/tippecanoe -j"$(nproc)" \
 && make -C /tmp/tippecanoe install \
 && rm -rf /tmp/tippecanoe \
 && apt-get purge -y --auto-remove build-essential git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /w
COPY forecast/requirements.txt /tmp/forecast-requirements.txt
COPY pipeline/requirements.txt /tmp/pipeline-requirements.txt
RUN sed -i 's#^-r ../forecast/#-r /tmp/forecast-#' /tmp/pipeline-requirements.txt \
 && pip install --no-cache-dir -r /tmp/pipeline-requirements.txt
