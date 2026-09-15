# Mission Control API image. Backend only - the CLI talks HTTP to whatever
# API instance it's pointed at (FR-18), and the SPA (web/) is a separate
# static build with its own lightweight image (see web/Dockerfile) - neither
# needs to ship inside this one.
#
# Auto-seeds demo data on first start (T11, docker/entrypoint.sh): a fresh
# container with no db file yet runs `python -m scripts.seed` before
# uvicorn starts, so `docker compose up -d` alone gives a populated
# instance - no separate `docker compose exec api python -m scripts.seed`
# step required. Safe across restarts: the entrypoint only ever seeds once,
# the first time the db file doesn't exist yet - see that script for why
# that guard has to live there and not in scripts/seed.py itself.

FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies in their own layer so `pip install` is only re-run
# when requirements.txt actually changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY models/ ./models/
COPY services/ ./services/
COPY scripts/ ./scripts/
COPY main.py .
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Not COPYing cli/ - the CLI is a client, not something this image serves;
# run it from a normal checkout against the container's exposed port instead.

EXPOSE 8000

# sqlite:///./mission_control.db (models/database.py's default) resolves
# relative to the working directory, i.e. /app/mission_control.db inside the
# container - mount a volume at /app (or set MISSION_CONTROL_DATABASE_URL to
# a path under a mounted volume, as docker-compose.yml does) if you want the
# db file - and the demo data seeded into it - to persist across restarts.
ENTRYPOINT ["/entrypoint.sh"]
