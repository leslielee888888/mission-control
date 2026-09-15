# Mission Control API image. Backend only - the CLI talks HTTP to whatever
# API instance it's pointed at (FR-18), and the SPA (web/) is a separate
# static build with its own lightweight image (see web/Dockerfile) - neither
# needs to ship inside this one.
#
# No seed data is baked in: this image starts with an empty database. Run
# the seed script as a separate step against the mounted/persisted db file
# if you want demo data inside a container - see README.md.

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

# Not COPYing cli/ - the CLI is a client, not something this image serves;
# run it from a normal checkout against the container's exposed port instead.

EXPOSE 8000

# sqlite:///./mission_control.db (models/database.py's default) resolves
# relative to the working directory, i.e. /app/mission_control.db inside the
# container - mount a volume at /app if you want the db file to persist
# across restarts, e.g. `-v mission-control-data:/app`.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
