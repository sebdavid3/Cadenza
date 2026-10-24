#!/bin/sh
# Limpieza de Docker en el servidor del despliegue (#205, docs/infra/operacion_backend.md §2.2):
# deja la caché de construcción en CADENZA_BUILD_CACHE_MAX como mucho (10 GB por defecto) y borra
# las imágenes colgantes, las que ya no tienen nombre ni las usa ningún contenedor. No toca
# volúmenes, contenedores ni imágenes con nombre. La usan el procedimiento de actualización y el
# cron del servidor:
#
#   45 4 * * 0 /bin/sh /opt/docker/cadenza/deploy/limpieza-docker.sh >> /opt/docker/cadenza/backups/limpieza-docker.log 2>&1
set -eu

max="${CADENZA_BUILD_CACHE_MAX:-10GB}"

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
usage() { docker system df --format '{{.Type}}: {{.Size}}' | tr '\n' ' '; }
trap 'echo "$(stamp) ERROR: la limpieza no se completó"' EXIT

echo "$(stamp) antes: $(usage)"
# Primero las imágenes: la caché que respalda una imagen colgante solo se libera cuando la imagen
# ya no está.
docker image prune --force >/dev/null
docker builder prune --force --max-used-space "$max" >/dev/null

trap - EXIT
echo "$(stamp) después: $(usage)"
