ARG OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:2026.9.6
FROM ${OPENCLAW_IMAGE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

USER node
