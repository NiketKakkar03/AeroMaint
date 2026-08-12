FROM node:22.14.0-alpine AS build

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN npm install --global pnpm@11.9.0

WORKDIR /workspace
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json eslint.config.mjs ./
COPY apps/viewer ./apps/viewer
COPY packages ./packages
RUN pnpm install --frozen-lockfile

ENV VITE_API_BASE_URL=/api
RUN pnpm --filter @aeromaint/viewer build

FROM nginx:1.30.4-alpine3.24

COPY apps/viewer/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/apps/viewer/dist /usr/share/nginx/html

EXPOSE 5173
