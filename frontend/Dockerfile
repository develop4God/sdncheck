# SDNCheck Frontend Dockerfile
# Multi-stage build for optimized production image

# Stage 1: Build React app
FROM node:18-alpine as builder

WORKDIR /app


# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY public/ ./public/
COPY src/ ./src/

# Build production bundle
ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

# Stage 2: Production image with nginx
FROM nginx:alpine

# Copy nginx configuration template
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Copy built assets from builder
COPY --from=builder /app/build /usr/share/nginx/html

# Railway provides PORT env var - default to 8080 for Railway
ENV PORT=8080

# Expose port 8080 (Railway default)
EXPOSE 8080

# Use envsubst to replace PORT in nginx config at runtime
CMD sh -c "envsubst '\$PORT' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"
