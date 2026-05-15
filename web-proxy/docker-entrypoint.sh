#!/bin/sh
set -e

CERT=/etc/nginx/certs/cert.pem
KEY=/etc/nginx/certs/key.pem

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    echo "[entrypoint] TLS certs not found — generating self-signed cert for local dev..."
    mkdir -p /etc/nginx/certs
    openssl req -x509 -nodes -days 3650 \
        -newkey rsa:2048 \
        -keyout "$KEY" \
        -out "$CERT" \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
        2>/dev/null
    echo "[entrypoint] Self-signed cert generated."
fi

exec nginx -g "daemon off;"
