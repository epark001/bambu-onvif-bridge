#!/bin/sh
set -eu

image="${1:-bambu-onvif-bridge:test}"
name="bpo-container-smoke"

cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
cleanup

docker run -d \
    --name "$name" \
    --network none \
    --cap-add NET_ADMIN \
    --entrypoint sh \
    -v "$PWD/tests/fixtures/container-smoke.yaml:/config/config.yaml:ro" \
    "$image" \
    -c 'ip link add dummy0 type dummy && ip address add 192.0.2.1/24 dev dummy0 && ip link set dummy0 up && exec /usr/local/bin/bpo-entrypoint' \
    >/dev/null

attempt=0
until docker exec "$name" python -m bpo_runtime.healthcheck >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ] || [ "$(docker inspect -f '{{.State.Running}}' "$name")" != "true" ]; then
        docker logs "$name"
        exit 1
    fi
    sleep 1
done

docker exec "$name" supervisorctl -c /etc/supervisord.conf status
docker exec "$name" ip -j -d address show dev bpo-onvif0
docker stop -t 20 "$name" >/dev/null
docker logs "$name" 2>&1 | grep -q "removed interface bpo-onvif0"
