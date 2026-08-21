FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

COPY 001-citybuddy-extensions.sql /docker-entrypoint-initdb.d/20-citybuddy-extensions.sql
