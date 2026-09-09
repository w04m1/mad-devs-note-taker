# syntax=docker/dockerfile:1.7
FROM node:22.13.1-bookworm-slim

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH
RUN npm install --global pnpm@11.21.0
WORKDIR /app

# The frontend workstream owns package.json and pnpm-lock.yaml here. Copying the
# full context supports either src/ at the root or extra generated API files.
COPY . /app
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]
