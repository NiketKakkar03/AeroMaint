FROM node:22.14.0-alpine

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN npm install --global pnpm@11.9.0

WORKDIR /workspace
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json eslint.config.mjs ./
COPY apps/viewer ./apps/viewer
COPY packages ./packages
RUN pnpm install --frozen-lockfile

EXPOSE 5173
CMD ["pnpm", "--filter", "@aeromaint/viewer", "dev"]
