# Dashboard web (React + Vite, tarea 4.18). Contexto de build: raiz del repositorio.
# Se compila con Node y se sirve con nginx, que ademas reenvia /api a la API.
FROM node:22.14.0-alpine AS build
WORKDIR /dashboard
COPY ["Fase 2/Evidencias Proyecto/src/dashboard/package.json", "Fase 2/Evidencias Proyecto/src/dashboard/package-lock.json", "./"]
RUN npm ci --no-audit --no-fund
COPY ["Fase 2/Evidencias Proyecto/src/dashboard", "./"]
RUN npm run build

FROM nginx:1.27.5-alpine
COPY ["Fase 2/Evidencias Proyecto/docker/dashboard/nginx.conf", "/etc/nginx/conf.d/default.conf"]
COPY --from=build /dashboard/dist /usr/share/nginx/html
EXPOSE 80
