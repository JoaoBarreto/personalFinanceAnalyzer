FROM docker.io/library/node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM docker.io/nginxinc/nginx-unprivileged:stable-alpine
# template: a imagem substitui ${NGINX_LOCAL_RESOLVERS} no arranque e escreve /etc/nginx/conf.d/default.conf
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
