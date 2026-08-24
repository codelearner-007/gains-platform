FROM python:3.12-slim

WORKDIR /app

# Must match the Postgres major version the target Supabase project is
# actually running (Supabase Dashboard -> Project Settings -> Database) --
# Supabase upgrades this over time, so re-verify before bumping, don't assume
# today's value still holds. Debian's own repo only ships one Postgres client
# major at a time and it may not match, hence pulling from PGDG directly.
ARG PG_MAJOR=17

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg lsb-release && \
    install -d /usr/share/postgresql-common/pgdg && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc && \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client-${PG_MAJOR} && \
    apt-get purge -y --auto-remove curl gnupg lsb-release && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "backup.py"]
