#!/bin/sh
# Despliegue continuo del homelab (#337, ADR-0062, docs/infra/operacion_backend.md §2.2): el
# servidor tira de la rama publicada (main por defecto) y, si hay un commit nuevo cuya CI terminó en
# verde, hace una copia verificada, avanza en fast-forward, reconstruye y espera a /api/health. Si
# la API no responde, vuelve al commit anterior y no reintenta el fallido. Pensado para el cron del
# servidor (gh vive en ~/.local/bin):
#
#   */5 * * * * PATH=$HOME/.local/bin:/usr/bin:/bin /bin/sh /opt/docker/cadenza/deploy/despliegue-continuo.sh >> /opt/docker/cadenza/backups/despliegue.log 2>&1
#
# Sin cambios, con la CI en curso o en pausa no escribe nada, para no llenar el log cada 5 minutos.
# Pausar: crear el archivo «pausado» en el directorio de estado. Probar sin tocar nada: --simular.
set -eu
cd "$(dirname "$0")/.."

# El puerto de la web vive en el .env del despliegue, que el cron no carga.
puerto="${CADENZA_WEB_PORT:-$(sed -n 's/^CADENZA_WEB_PORT=//p' .env 2>/dev/null | tail -n 1)}"
rama="${CADENZA_DESPLIEGUE_RAMA:-main}"
repo="${CADENZA_DESPLIEGUE_REPO:-sebdavid3/Cadenza}"
flujo="${CADENZA_DESPLIEGUE_FLUJO:-CI}"
estado="${CADENZA_DESPLIEGUE_ESTADO:-$HOME/.local/state/cadenza-despliegue}"
salud="${CADENZA_DESPLIEGUE_SALUD:-http://127.0.0.1:${puerto:-8380}/api/health}"
espera="${CADENZA_DESPLIEGUE_ESPERA:-300}"
intervalo="${CADENZA_DESPLIEGUE_INTERVALO:-10}"
aviso_cmd="${CADENZA_DESPLIEGUE_AVISO:-}"
dc="docker compose -f docker-compose.prod.yml --env-file .env"

simular=0
case "${1:-}" in
    --simular) simular=1 ;;
    "") ;;
    *) echo "uso: $0 [--simular]" >&2; exit 2 ;;
esac

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(stamp) $*"; }
# Lo que pasa en cada pasada sin novedad solo se ve al simular.
nota() { [ "$simular" -eq 0 ] || log "$*"; }
# Avisa fuera del log si hay un comando configurado (por ejemplo, un curl a un servicio de avisos).
avisar() {
    [ -z "$aviso_cmd" ] || sh -c "$aviso_cmd \"\$1\"" aviso "Cadenza: $*" || log "el aviso falló"
}
# Algo que se repetiría en cada pasada se registra una vez. Al simular solo se muestra, para no
# callar el registro de la pasada real.
una_vez() {
    if [ "$simular" -eq 1 ]; then
        log "$*"
    elif [ "$(cat "$estado/ultimo-error" 2>/dev/null || true)" != "$*" ]; then
        log "$*"
        echo "$*" > "$estado/ultimo-error"
    fi
}
error_unico() {
    una_vez "ERROR: $*"
    exit 1
}
# Un fallo que necesita a una persona: se avisa, se pausa y no se insiste cada 5 minutos.
detener() {
    log "ERROR: $*; despliegue continuo en pausa hasta revisar ($estado/pausado)"
    avisar "$*"
    echo "$*" > "$estado/pausado"
    exit 1
}

mkdir -p "$estado"
touch "$estado/rechazados"

# Una sola pasada a la vez: un despliegue puede durar más que el intervalo del cron.
exec 9> "$estado/lock"
if ! flock -n 9; then
    nota "otra pasada en curso"
    exit 0
fi

if [ -e "$estado/pausado" ]; then
    nota "en pausa ($estado/pausado)"
    exit 0
fi

git fetch -q origin "$rama" || error_unico "no se pudo traer origin/$rama"
objetivo="$(git rev-parse "origin/$rama")"
actual="$(git rev-parse HEAD)"
corto="$(git rev-parse --short "$objetivo")"

if [ "$objetivo" = "$actual" ]; then
    rm -f "$estado/ultimo-error"
    nota "al día en $corto"
    exit 0
fi
if grep -qx "$objetivo" "$estado/rechazados"; then
    nota "$corto ya se descartó (quitarlo de $estado/rechazados para reintentarlo)"
    exit 0
fi
if ! git diff --quiet HEAD --; then
    error_unico "el árbol tiene cambios sin comitear; no se despliega $corto"
fi
# Un archivo sin seguimiento que el commit nuevo sí trae haría fallar el checkout tras la copia.
git ls-files --others --exclude-standard | sort > "$estado/sueltos"
choques="$(git ls-tree -r --name-only "$objetivo" | sort | comm -12 - "$estado/sueltos")"
if [ -n "$choques" ]; then
    error_unico "archivos sin seguimiento que $corto trae: $(echo "$choques" | tr '\n' ' ')"
fi
if ! git merge-base --is-ancestor "$actual" "$objetivo"; then
    error_unico "origin/$rama ($corto) no avanza en fast-forward desde $(git rev-parse --short HEAD)"
fi

# La ejecución más reciente del flujo de CI para ese commit, lanzada por el push a la rama. Una
# ejecución terminada sin éxito no se apunta como descartada: si se relanza y pasa, se despliega.
ci="$(gh api "repos/$repo/actions/runs?head_sha=$objetivo&event=push&per_page=100" --jq "
    [.workflow_runs[] | select(.name == \"$flujo\" and .head_branch == \"$rama\")]
    | sort_by(.created_at, .run_attempt) | last
    | if . == null then \"pendiente\"
      elif .status != \"completed\" then \"pendiente\"
      elif .conclusion == \"success\" then \"verde\"
      else \"roja:\" + .conclusion end")" || error_unico "no se pudo consultar la CI de $corto"

case "$ci" in
    pendiente)
        nota "la CI de $corto sigue en curso o no ha empezado"
        exit 0
        ;;
    verde) ;;
    *)
        una_vez "la CI de $corto no pasó (${ci#roja:}); no se despliega"
        exit 0
        ;;
esac

if [ "$simular" -eq 1 ]; then
    log "desplegaría $(git rev-parse --short HEAD) -> $corto (CI en verde)"
    exit 0
fi

sano() {
    limite=$(($(date +%s) + espera))
    while :; do
        if curl -fsS -m 10 "$salud" 2>/dev/null | grep -q '"database":"connected"'; then
            return 0
        fi
        [ "$(date +%s)" -lt "$limite" ] || return 1
        sleep "$intervalo"
    done
}
# Tras «up» la imagen de copias se reconstruye aparte; si falla, el despliegue sigue bien.
imagen_copias() {
    $dc --profile backup build backup || log "AVISO: no se reconstruyó la imagen de copias"
}

log "desplegando $(git rev-parse --short HEAD) -> $corto"
copia="cadenza-$(date -u +%Y-%m-%d-%H%M)-antes-$corto.tar.gz"
$dc --profile backup run --rm -T backup backup --output "/backups/$copia" ||
    detener "la copia previa $copia falló"
$dc --profile backup run --rm -T backup verify --archive "/backups/$copia" ||
    detener "la copia previa $copia no se pudo verificar"
log "copia $copia verificada"

git checkout -q -B "$rama" "$objetivo" || detener "no se pudo pasar a $corto"
if $dc up -d --build && sano; then
    rm -f "$estado/ultimo-error"
    log "desplegado $corto"
    imagen_copias
    sh deploy/limpieza-docker.sh || log "AVISO: la limpieza de Docker falló"
    exit 0
fi

# La API aplica las migraciones al arrancar: si la versión nueva ya migró la base, puede que la
# anterior tampoco arranque. Entonces toca restaurar la copia a mano (§4.2).
previo="$(git rev-parse --short "$actual")"
log "ERROR: $corto no quedó sano en ${espera}s; vuelvo a $previo"
echo "$objetivo" >> "$estado/rechazados"
git checkout -q -B "$rama" "$actual"
if $dc up -d --build && sano; then
    log "vuelto a $previo; $corto queda descartado"
    avisar "$corto no arrancó; producción sigue en $previo"
    exit 1
fi
detener "ERROR GRAVE: tampoco arranca $previo; restaurar la copia $copia (§4.2)"
