# Frontend Dockerfile - React + nginx
# Multi-stage build: Build React app, serve with nginx

# ========================================
# Stage 1: Build React application
# ========================================
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files for dependency caching
COPY frontend/package.json frontend/package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY frontend/ ./

# Build React application
RUN npm run build

# ========================================
# Stage 2: Serve with nginx
# ========================================
FROM nginx:alpine

# Copy nginx configuration
COPY docker/frontend/nginx.conf /etc/nginx/nginx.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
