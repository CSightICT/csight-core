FROM node:24.11.0-alpine3.22 AS build

WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29.5-alpine3.23

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /workspace/dist /usr/share/nginx/html

ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d \
    NGINX_ENVSUBST_FILTER=WEB_MAX_UPLOAD_BODY \
    WEB_MAX_UPLOAD_BODY=12m
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/web-health || exit 1
