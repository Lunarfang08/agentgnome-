FROM node:24.14.1-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
COPY apps/dashboard ./apps/dashboard
COPY sdk/typescript/package.json ./sdk/typescript/package.json
RUN npm ci && npm run build --workspace apps/dashboard

FROM node:24.14.1-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/apps/dashboard/.next/standalone ./
COPY --from=build --chown=node:node /app/apps/dashboard/.next/static ./apps/dashboard/.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD node -e "fetch('http://127.0.0.1:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/dashboard/server.js"]
