# Playwright base image ships Chromium + all system deps. The tag MUST track the
# playwright version resolved in package-lock.json, not the `^` range in
# package.json: `npm ci` installs the lockfile exactly, and each Playwright
# release pins its own browser revisions under /ms-playwright. A base image
# built for a different version has no matching revision directory, so
# chromium.launch() dies at RUNTIME with "Executable doesn't exist at
# /ms-playwright/chromium-<rev>" — the build and `npm ci` both succeed, so the
# mismatch only surfaces on the first scrape. Bump BOTH together.
#
# `noble` ships Node 24, which satisfies the `node >= 22` engines constraint that
# @supabase/* declares (verified in-container: node=v24.17.0, chromium=149.0.7827.55).
FROM mcr.microsoft.com/playwright:v1.61.1-noble

WORKDIR /app

# Install dependencies first for better layer caching.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# App source. lib/ MUST be copied: the entrypoint requires ./lib/{logger,paginate,paths,notify}.
# tests/ is deliberately excluded — it is not needed at runtime.
COPY schoology-exporter.js ./
COPY lib ./lib

# Credentials + config are supplied at runtime via environment variables
# (see .env.example). Never bake secrets into the image.
#
# CMD, deliberately NOT ENTRYPOINT. Railway's custom start command replaces CMD,
# but with an ENTRYPOINT set it is APPENDED as arguments instead — producing
# `node schoology-exporter.js node schoology-exporter.js --school X`. That happens
# to work when the args arrive separately, and breaks when the platform wraps them
# in `sh -c` (the flags collapse into one argv string and --school stops matching).
# CMD is unambiguous under both.
#
# Local runs therefore name the script explicitly:
#   docker run --env-file .env <img> node schoology-exporter.js --school Athenian --dry-run
CMD ["node", "schoology-exporter.js"]
