# syntax=docker/dockerfile:1.6
# Frontend image: Vite build → nginx serves dist/ + reverse-proxy на бэкенд.
# Build-args для VITE_*: подставляются в bundle на этапе сборки.

FROM node:20-alpine AS build

WORKDIR /app

# Build-time env (доступно в bundle через import.meta.env).
ARG VITE_API_BASE=/api/v1
ARG VITE_YANDEX_MAPS_KEY=""
ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_YANDEX_MAPS_KEY=$VITE_YANDEX_MAPS_KEY

COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

# SPA fallback + reverse-proxy на backend:8000.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

# busybox wget (alpine) не знает --spider; 127.0.0.1 — т.к. localhost
# резолвится в IPv6 ::1, а nginx слушает только IPv4.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
