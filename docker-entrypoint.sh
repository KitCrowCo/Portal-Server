#!/bin/bash
set -e

# 1. Settings come from the container's environment (compose env_file / environment - e.g. a .env kept outside the project).
#    /app/.env is only the fallback for a bare `docker run`: it is created, with a random SECRET_KEY, only when neither it nor SECRET_KEY exists,
#    and a value from it never replaces one the environment already set. SECRET_KEY signs logins and derives the key for encrypted stored values,
#    so it must stay the same across container rebuilds - a new one signs everyone out and leaves earlier encrypted values unreadable.
ENV_FILE="/app/.env"
if [ -z "${SECRET_KEY:-}" ] && [ ! -f "$ENV_FILE" ]; then
    echo "[INFO] SECRET_KEY not set and no $ENV_FILE - generating one (it lives only in this container; set SECRET_KEY in the environment to keep logins across rebuilds)"
    echo "SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")" > "$ENV_FILE"
fi
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key value || [ -n "$key" ]; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        [ -z "${!key+x}" ] && export "$key=$value"
    done < "$ENV_FILE"
fi
export ALGORITHM="${ALGORITHM:-HS256}" APP_ROOT="${APP_ROOT:-/app}" DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/server.db}"

# 2. Ensure runtime data folders exist
mkdir -p /app/data /app/modules /app/tools

# 3. Handle Permission Adjustments for Mounted Volumes
# (Fixes permission errors when local host users map volumes)
#chmod -R 775 /app/data /app/modules /app/tools || true

# Execute the main container command (Uvicorn)
exec "$@"
