# Mission Control SPA image - a static build (FR-21's showcase, §10 #16-18)
# served by nginx. Build-time only: VITE_API_BASE_URL bakes into the static
# JS bundle, so point it at wherever the API image is actually reachable
# from the browser (not from inside this container) at build time:
#   docker build --build-arg VITE_API_BASE_URL=http://localhost:8000 -t mission-control-web .

FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# React Router-free (§10 #16: "no routing depth"), but a plain nginx serves
# index.html for `/` correctly out of the box already - no custom config
# needed for this app's two-screen, useState-driven navigation.
EXPOSE 80
