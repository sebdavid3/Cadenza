#!/bin/sh
# Copia diaria del despliegue público (#174, docs/infra/operacion_backend.md §4.3): hace una copia
# con el servicio backup, la verifica y, solo si es válida, borra las de más de
# CADENZA_BACKUP_KEEP_DAYS días (14 por defecto). Pensado para el cron del servidor:
#
#   15 4 * * * /bin/sh /opt/docker/cadenza/deploy/copia-diaria.sh >> /opt/docker/cadenza/backups/copias.log 2>&1
set -eu
cd "$(dirname "$0")/.."

days="${CADENZA_BACKUP_KEEP_DAYS:-14}"
name="cadenza-$(date -u +%Y-%m-%d-%H%M).tar.gz"
dc="docker compose -f docker-compose.prod.yml --env-file .env --profile backup"

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
trap 'echo "$(stamp) ERROR: la copia $name no se completó"' EXIT

echo "$(stamp) copia $name"
$dc run --rm -T backup backup --output "/backups/$name"
$dc run --rm -T backup verify --archive "/backups/$name"
# Solo con la copia nueva verificada se borran las antiguas.
find backups -maxdepth 1 -name 'cadenza-*.tar.gz' -mtime +"$days" -print -delete

trap - EXIT
echo "$(stamp) copia $name verificada"
