# syntax=docker/dockerfile:1

ARG ONVIF_SERVER_COMMIT=7aa2c541b67b1a2760887a1706d7a5e45e5ae1a4

FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS onvif-server
ARG ONVIF_SERVER_COMMIT
RUN apk add --no-cache git \
    && git clone https://github.com/daniela-hase/onvif-server.git /build/onvif-server \
    && git -C /build/onvif-server checkout "${ONVIF_SERVER_COMMIT}" \
    && cd /build/onvif-server \
    && npm install --omit=dev --save-exact xml2js@0.6.2 yaml@2.9.0 \
    && npm cache clean --force \
    && rm -rf /build/onvif-server/.git

FROM alexxit/go2rtc:1.9.14@sha256:675c318b23c06fd862a61d262240c9a63436b4050d177ffc68a32710d9e05bae

ARG ONVIF_SERVER_COMMIT
LABEL org.opencontainers.image.title="Bambu Protect Overlay" \
      org.opencontainers.image.description="Bambu printer video overlays exposed as virtual ONVIF cameras" \
      org.opencontainers.image.source="https://github.com/mtnears/bambu-protect-overlay" \
      org.opencontainers.image.licenses="MIT" \
      io.bambu-protect-overlay.go2rtc.version="1.9.14" \
      io.bambu-protect-overlay.onvif-server.commit="${ONVIF_SERVER_COMMIT}"

RUN apk add --no-cache nodejs iproute2 tzdata \
    && python -m venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/config/config.yaml \
    OUTPUT_DIR=/data/overlay \
    RUNTIME_DIR=/run/bambu-protect-overlay

COPY requirements-container.txt /tmp/requirements-container.txt
RUN pip install --no-cache-dir -r /tmp/requirements-container.txt \
    && rm /tmp/requirements-container.txt

COPY --from=onvif-server /build/onvif-server /opt/onvif-server
COPY bambu-overlay/bambu_overlay.py /app/bambu_overlay.py
COPY bpo_runtime /app/bpo_runtime
COPY container/supervisord.conf /etc/supervisord.conf
COPY container/entrypoint.sh /usr/local/bin/bpo-entrypoint
COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/licenses/bambu-protect-overlay/

RUN chmod 0755 /usr/local/bin/bpo-entrypoint \
    && mkdir -p /config /data/overlay /run/bambu-protect-overlay

WORKDIR /app
VOLUME ["/config"]
EXPOSE 1984 8554
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["python", "-m", "bpo_runtime.healthcheck"]
ENTRYPOINT ["/usr/local/bin/bpo-entrypoint"]
CMD []
