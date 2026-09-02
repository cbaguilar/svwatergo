FROM node:24-bookworm-slim AS build

WORKDIR /src/frontend/svwaternet

COPY frontend/svwaternet/package.json frontend/svwaternet/package-lock.json ./
RUN npm ci

COPY frontend/svwaternet ./
RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/frontend/svwaternet/build /usr/share/nginx/html

EXPOSE 80
