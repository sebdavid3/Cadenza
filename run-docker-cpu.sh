#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "      Levantando Cadenza OMR en Docker en Modo CPU        "
echo "=========================================================="

# Verificar docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_CMD="docker-compose"
else
    DOCKER_CMD="docker compose"
fi

$DOCKER_CMD -f docker-compose.cpu.yml up --build
