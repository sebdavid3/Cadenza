#!/usr/bin/env bash
set -e

echo '[1/4] Agregando llave y repositorio de NVIDIA...'
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null

echo '[2/4] Actualizando apt e instalando nvidia-container-toolkit...'
apt-get update
apt-get install -y nvidia-container-toolkit

echo '[3/4] Configurando Docker runtime...'
nvidia-ctk runtime configure --runtime=docker

echo '[4/4] Reiniciando servicio de Docker...'
systemctl restart docker

echo '>> NVIDIA Container Toolkit configurado exitosamente!'
