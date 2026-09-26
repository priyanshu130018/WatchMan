# Multi-stage build for frontend
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package manifests
COPY package*.json ./

# Install dependencies (including devDependencies required for build)
RUN npm install

# Copy application source
COPY . .

# Build arguments for public client configuration (embedded at build time).
# NOTE: .env is excluded by .dockerignore, so Vite does NOT pick these up from a
# file inside the build context — they MUST be passed as build args or the
# bundle falls back to defaults (e.g. auth provider -> 'local').
ARG VITE_API_BASE_URL=/api
ARG VITE_AUTH_PROVIDER=local
ARG VITE_SUPABASE_URL=""
ARG VITE_SUPABASE_PUBLISHABLE_KEY=""

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_AUTH_PROVIDER=$VITE_AUTH_PROVIDER
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY

# Build the Nitro SSR application
RUN npm run build

# Final production runtime stage
FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

# Copy compiled output from builder
COPY --from=builder /app/.output ./.output

# Use non-root node user (UID 1000 built into node:alpine)
USER node

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "require('http').get('http://localhost:' + (process.env.PORT || 3000) + '/', (res) => { if (res.statusCode >= 200 && res.statusCode < 400) process.exit(0); else process.exit(1); }).on('error', () => process.exit(1));"

EXPOSE 3000

CMD ["node", ".output/server/index.mjs"]
