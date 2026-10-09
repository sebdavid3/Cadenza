FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Instalar dependencias del sistema necesarias para OpenCV, Pillow y procesamiento multimedia
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Actualizar pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copiar requirements.txt e instalar dependencias CPU
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Directorios para cache y temporales
RUN mkdir -p /tmp/homr-proto /root/.cache/torch /root/.cache/homr

# Copiar código fuente
COPY main.py check_gpu.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
