#!/bin/sh
# Mission Control API container entrypoint (T11).
#
# Auto-seeds demo data on a truly first start, but never on a restart of an
# already-populated container: `python -m scripts.seed` is unconditionally
# destructive (it deletes any existing sqlite file before rebuilding --
# see scripts/seed.py's `_reset_database_file`), so *this* script is what
# has to guard against ever calling it against a database that already
# exists -- a reviewer's own in-progress changes (missions they created,
# assignments they proposed) must survive `docker compose restart`/
# `docker restart`.
#
# POSIX sh only (no bash) -- the base image is python:3.11-slim, which has
# /bin/sh but not necessarily /bin/bash.
set -eu

# Same default models/database.py falls back to (DEFAULT_DATABASE_URL) when
# MISSION_CONTROL_DATABASE_URL isn't set, so this resolves the exact same
# path the app itself will open.
DB_URL="${MISSION_CONTROL_DATABASE_URL:-sqlite:///./mission_control.db}"

case "$DB_URL" in
    sqlite:///*)
        # Strip the "sqlite:///" scheme prefix, same as scripts/seed.py's
        # own `_reset_database_file` -- leaves a relative path
        # ("./mission_control.db") or an absolute one ("/data/..." from
        # docker-compose.yml's "sqlite:////data/...", where the 4th slash
        # is the start of the absolute path).
        DB_PATH="${DB_URL#sqlite:///}"
        if [ -f "$DB_PATH" ]; then
            echo "entrypoint: database file '$DB_PATH' already exists -- skipping seed"
        else
            echo "entrypoint: no database file at '$DB_PATH' yet -- seeding demo data"
            python -m scripts.seed
        fi
        ;;
    *)
        # Not a sqlite:/// URL (nothing in this project actually points
        # MISSION_CONTROL_DATABASE_URL anywhere else today, but if it ever
        # is, there's no local file to check existence of) -- err toward
        # never auto-seeding rather than risking a destructive reseed
        # against a database this script can't safely inspect.
        echo "entrypoint: MISSION_CONTROL_DATABASE_URL is not a sqlite:/// URL -- skipping auto-seed"
        ;;
esac

exec uvicorn main:app --host 0.0.0.0 --port 8000
