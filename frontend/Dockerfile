FROM node:20-alpine

WORKDIR /app

# Copiar archivos de dependencias
COPY package.json ./

# Instalar dependencias
RUN npm install

# Copiar código fuente
COPY . .

# Argumento para URL de la API del backend (por defecto vacío para proxy inverso relativo)
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

# Compilar aplicación para producción
RUN npm run build

# Exponer puerto de Vite
EXPOSE 5173

# Servir con vite preview
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
