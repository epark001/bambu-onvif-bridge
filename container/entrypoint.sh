#!/bin/sh
set -eu

python -m bpo_runtime.bootstrap
exec /sbin/tini -- supervisord -c /etc/supervisord.conf
