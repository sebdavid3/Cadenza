#!/bin/sh
# Despliegue manual de dev en el homelab en un comando (#382, docs/infra/operacion_backend.md §2.2,
# «Actualizar»): copia verificada, pull en fast-forward hasta el commit esperado, reconstrucción,
# imagen de copias, limpieza y espera a /api/health. Desde un equipo con el repositorio:
#
#   git fetch origin && ssh r2d2-cf "sh -s $(git rev-parse origin/dev)" < deploy/desplegar.sh
#
# El commit esperado es obligatorio: si origin/dev en el servidor no es ese (otro merge entretanto),
# no hace nada. Tampoco si el árbol del servidor tiene cambios sin comitear. Si la API no queda sana,
# lo dice y sale con 2, sin volver atrás: la vuelta atrás, a mano, con la copia (§4.2).
set -eu

esperado="${1:-}"
if [ -z "$esperado" ]; then
    echo "uso: desplegar.sh <commit esperado de origin/dev>" >&2
    exit 64
fi
cd "${CADENZA_DESPLIEGUE_DIR:-/opt/docker/cadenza}"

# El puerto de la web vive en el .env del despliegue.
puerto="${CADENZA_WEB_PORT:-$(sed -n 's/^CADENZA_WEB_PORT=//p' .env 2>/dev/null | tail -n 1)}"
rama="${CADENZA_DESPLIEGUE_RAMA:-dev}"
salud="${CADENZA_DESPLIEGUE_SALUD:-http://127.0.0.1:${puerto:-8380}/api/health}"
espera="${CADENZA_DESPLIEGUE_ESPERA:-300}"
intervalo="${CADENZA_DESPLIEGUE_INTERVALO:-5}"
DC="docker compose -f docker-compose.prod.yml --env-file .env"

echo "== estado"
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "el árbol del servidor tiene cambios sin comitear: no se despliega"
    git status --short
    exit 1
fi
antes=$(git rev-parse --short HEAD)
git fetch -q origin
remoto=$(git rev-parse "origin/$rama")
case "$remoto" in
    "$esperado"*) ;;
    *)
        echo "origin/$rama es $remoto, no $esperado: no se despliega"
        exit 1
        ;;
esac
echo "producción en $antes; se despliega $(git rev-parse --short "origin/$rama")"

echo "== copia previa"
copia="cadenza-$(date +%F-%H%M)-antes-$antes.tar.gz"
$DC --profile backup run --rm backup backup --output "/backups/$copia"
$DC --profile backup run --rm backup verify --archive "/backups/$copia"

echo "== código"
git merge -q --ff-only "origin/$rama"
git log --oneline -1

echo "== construir y arrancar"
$DC up -d --build
$DC --profile backup build backup
sh deploy/limpieza-docker.sh

echo "== salud"
inicio=$(date +%s)
while :; do
    cuerpo=$(curl -fsS "$salud" 2>/dev/null || true)
    case "$cuerpo" in
        *'"database":"connected"'*)
            echo "sana tras $(($(date +%s) - inicio)) s: $cuerpo"
            break
            ;;
    esac
    if [ $(($(date +%s) - inicio)) -ge "$espera" ]; then
        echo "ERROR: $salud no responde sana en $espera s; la copia previa es $copia"
        $DC ps || true
        $DC logs --tail 80 api || true
        exit 2
    fi
    sleep "$intervalo"
done
$DC ps
