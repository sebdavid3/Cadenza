#!/bin/sh
# Despliegue manual de dev en el homelab en un comando (#382, docs/infra/operacion_backend.md §2.2,
# «Actualizar»): copia verificada, avance en fast-forward hasta el commit esperado, reconstrucción,
# imagen de copias, limpieza y espera a /api/health. Desde un equipo con el repositorio:
#
#   git fetch origin && ssh r2d2-cf "sh -s $(git rev-parse origin/dev)" < deploy/desplegar.sh
#
# El commit esperado es obligatorio: si origin/dev en el servidor no es ese (otro merge entretanto),
# no hace nada. Tampoco si el árbol del servidor tiene cambios sin comitear o no está en la rama.
# Si la API no queda sana, lo dice y sale con 2, sin volver atrás: la vuelta atrás, a mano, con la
# copia que nombra (§4.2).
#
# Todo va dentro de `main`, que se llama al final con la entrada estándar cerrada: el guion llega
# por esa misma entrada (`sh -s`), así que el shell lo lee entero antes de ejecutar nada y ninguna
# orden (un `docker compose run`) puede comerse el resto. Un envío cortado es un error de sintaxis,
# no medio despliegue.
set -eu

main() {
    esperado="${1:-}"
    case "$esperado" in
        *[!0-9a-f]* | "")
            echo "uso: desplegar.sh <commit esperado de origin/dev, en hexadecimal>" >&2
            exit 64
            ;;
    esac
    if [ "${#esperado}" -lt 7 ]; then
        echo "el commit esperado necesita al menos 7 caracteres: $esperado" >&2
        exit 64
    fi
    cd "${CADENZA_DESPLIEGUE_DIR:-/opt/docker/cadenza}"

    # El puerto de la web vive en el .env del despliegue.
    puerto="${CADENZA_WEB_PORT:-$(sed -n 's/^CADENZA_WEB_PORT=//p' .env 2>/dev/null | tail -n 1)}"
    rama="${CADENZA_DESPLIEGUE_RAMA:-dev}"
    salud="${CADENZA_DESPLIEGUE_SALUD:-http://127.0.0.1:${puerto:-8380}/api/health}"
    espera="${CADENZA_DESPLIEGUE_ESPERA:-300}"
    intervalo="${CADENZA_DESPLIEGUE_INTERVALO:-5}"
    case "$espera" in
        *[!0-9]* | "")
            echo "CADENZA_DESPLIEGUE_ESPERA tiene que ser un número de segundos: $espera" >&2
            exit 64
            ;;
    esac
    DC="docker compose -f docker-compose.prod.yml --env-file .env"

    echo "== estado"
    if [ "$(git symbolic-ref -q --short HEAD || true)" != "$rama" ]; then
        echo "el servidor no está en la rama $rama: no se despliega"
        exit 1
    fi
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
    $DC --profile backup run --rm -T backup backup --output "/backups/$copia"
    $DC --profile backup run --rm -T backup verify --archive "/backups/$copia"

    echo "== código"
    git merge -q --ff-only "origin/$rama"
    git log --oneline -1

    echo "== construir y arrancar"
    if ! $DC up -d --build; then
        echo "ERROR: el código ya está en $(git rev-parse --short HEAD), pero los contenedores no se"
        echo "actualizaron (o a medias); la copia previa es $copia"
        $DC ps || true
        exit 2
    fi
    # Ni la imagen de copias ni la limpieza deciden si la versión nueva funciona: se avisa y sigue.
    $DC --profile backup build backup || echo "AVISO: no se reconstruyó la imagen de copias"
    sh deploy/limpieza-docker.sh || echo "AVISO: la limpieza de Docker no terminó"

    echo "== salud"
    inicio=$(date +%s)
    while :; do
        cuerpo=$(curl -fsS -m 10 "$salud" 2>/dev/null || true)
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
}

main "$@" </dev/null
