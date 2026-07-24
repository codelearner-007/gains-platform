# Playwright base image ships Chromium + all system deps, matching the pinned
# playwright version in package.json.
FROM mcr.microsoft.com/playwright:v1.49.0-jammy

WORKDIR /app

# Install dependencies first for better layer caching.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# App source.
COPY schoology-exporter.js ./

# Credentials + config are supplied at runtime via environment variables
# (see .env.example). Never bake secrets into the image.
ENTRYPOINT ["node", "schoology-exporter.js"]
