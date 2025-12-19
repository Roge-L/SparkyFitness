# Stage 1: Build the React application
FROM node:20-slim AS builder
WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm install

# Copy the rest of the application source code
COPY . .

# Build the application
RUN npm run build

# Stage 2: Serve the application with Nginx
FROM nginx:alpine

# Install bash and curl for console access and healthcheck
RUN apk add --no-cache bash curl

# Copy the build output from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy the nginx configuration template
COPY nginx.conf.template /etc/nginx/nginx.conf.template

# Expose port 80
EXPOSE 80

# Healthcheck
HEALTHCHECK --interval=5s --timeout=10s --retries=5 CMD ["curl", "-f", "http://127.0.0.1"]

# Custom entrypoint to substitute only our env vars
CMD envsubst '$SPARKY_FITNESS_SERVER_HOST $SPARKY_FITNESS_SERVER_PORT' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'
