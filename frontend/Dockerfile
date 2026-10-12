# syntax=docker/dockerfile:1
FROM node:20-alpine AS build
WORKDIR /src
COPY package.json yarn.lock ./
# Strip Emergent preview-only devDependencies (visual-edit overlay); craco disables them when absent.
RUN node -e "const fs=require('fs');const p=require('./package.json');for(const k of Object.keys(p.devDependencies||{}))if(k.startsWith('@emergentbase/'))delete p.devDependencies[k];fs.writeFileSync('package.json',JSON.stringify(p,null,2))" \
 && yarn install --network-timeout 600000
COPY . .
COPY deploy/index.html public/index.html
ARG REACT_APP_BACKEND_URL=""
ARG REACT_APP_ENV_LABEL=""
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL} REACT_APP_ENV_LABEL=${REACT_APP_ENV_LABEL} GENERATE_SOURCEMAP=false INLINE_RUNTIME_CHUNK=false NODE_ENV=production
RUN yarn build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/build /usr/share/nginx/html
EXPOSE 8080
