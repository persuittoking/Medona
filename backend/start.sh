#!/usr/bin/env bash
# Container entrypoint (Railway / docker run). Runs from backend/. Never prints secret values.
set -euo pipefail

missing=()
for name in JWT_SECRET PINFL_HASH_SECRET FERNET_KEY; do
  if [ -z "${!name:-}" ]; then missing+=("$name"); fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: required secret(s) not set: ${missing[*]}" >&2
  echo "Set them as service variables (see docs/DEPLOY.md for how to generate each one)." >&2
  exit 1
fi

export DEMO_MODE="${DEMO_MODE:-true}"  # hosted copy = synthetic demo data only

# Persistent Railway volume mounted at /data -> keep the DB there; otherwise a fresh DB per deploy.
if [ -z "${DATABASE_URL:-}" ]; then
  if [ -d /data ]; then
    export DATABASE_URL="sqlite:////data/onaradar.db"
  else
    export DATABASE_URL="sqlite:///./onaradar.db"
  fi
fi

# Seed synthetic demo data only when the SQLite file does not exist yet. The model is NOT trained here:
# the committed ml/artifacts/model.joblib is used.
case "$DATABASE_URL" in
  sqlite:///*)
    db_file="${DATABASE_URL#sqlite:///}"   # sqlite:////data/x.db -> /data/x.db ; sqlite:///./x.db -> ./x.db
    if [ ! -f "$db_file" ]; then
      echo "Database $db_file not found - seeding synthetic demo data..."
      if ! python -m app.seed; then
        rm -f "$db_file"  # never leave a half-seeded DB that would skip seeding next time
        echo "ERROR: seeding failed" >&2
        exit 1
      fi
    else
      echo "Database $db_file exists - not re-seeding."
    fi
    ;;
  *)
    echo "Non-SQLite DATABASE_URL - skipping automatic seeding."
    ;;
esac

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
