# Consume the exact prebuilt production bundle; install Linux runtime dependencies.
FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force
COPY --chown=node:node frontend/.next-public/ ./.next/
COPY --chown=node:node frontend/public/ ./public/
COPY --chown=node:node next.config.js ./next.config.js
USER node
EXPOSE 3000
CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
