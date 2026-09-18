FROM ubuntu:noble

# Toolchain layer, built ONCE and tagged oneiro-base:latest.
# Kept free of COPY instructions so the layer is cache-stable and
# independent of project file changes.
RUN apt update \
    -o Acquire::Retries=5 \
    && apt install -y --no-install-recommends \
       -o Acquire::Retries=5 \
       sudo tini curl ccache python3 python3-pip python3-venv cmake build-essential ninja-build \
    && rm -rf /var/lib/apt/lists/*
