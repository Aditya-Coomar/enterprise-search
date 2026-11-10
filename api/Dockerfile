# syntax = docker/dockerfile:1

# Adjust NODE_VERSION as desired
ARG NODE_VERSION=20.18.0
FROM node:${NODE_VERSION} AS base

LABEL fly_launch_runtime="Node.js"

# Node.js app lives here
WORKDIR /app

# Set production environment
ENV NODE_ENV="production"

# Install packages needed for node modules and app dependencies
RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    build-essential \
    node-gyp \
    pkg-config \
    python-is-python3 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Throw-away build stage to reduce size of final image
FROM base AS build

# Copy package files
COPY package*.json ./

# Install all dependencies (including dev dependencies for build)
RUN npm ci --include=dev --frozen-lockfile

# Copy source code
COPY . .

# Prisma generate
RUN npx prisma generate

# Build the TypeScript application
RUN npm run build

# Remove development dependencies to reduce image size
# RUN npm prune --omit=dev --omit=optional

# Final stage for app image
FROM node:${NODE_VERSION} AS production

# Install dumb-init for proper signal handling
RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    dumb-init \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app directory
WORKDIR /app

# Create non-root user for security
RUN groupadd --gid 1001 --system nodejs && \
    useradd --uid 1001 --system --gid nodejs --create-home --shell /bin/false nodejs

# Copy built application from build stage
COPY --from=build --chown=nodejs:nodejs /app/dist ./dist
COPY --from=build --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=build --chown=nodejs:nodejs /app/package*.json ./
COPY --from=build --chown=nodejs:nodejs /app/prisma ./prisma

# Copy Prisma client from build stage
COPY --from=build --chown=nodejs:nodejs /app/node_modules/@prisma/client ./node_modules/@prisma/client
RUN npx prisma generate
# Switch to non-root user
USER nodejs

# Expose the port that your app runs on
EXPOSE 8080

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Use dumb-init to handle signals properly
ENTRYPOINT ["dumb-init", "--"]

# Start the server
CMD ["npm", "run", "start"]