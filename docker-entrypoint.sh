#!/bin/bash
set -e

# 1. Auto-generate .env with SECRET_KEY if missing
ENV_FILE="/app/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "[INFO] No .env file found. Generating default secret key..."
    GENERATED_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
    cat <<EOF > "$ENV_FILE"
SECRET_KEY=${GENERATED_SECRET}
ALGORITHM=HS256
APP_ROOT=/app
DATABASE_URL=sqlite:////app/data/server.db
EOF
    echo "[INFO] Created .env with auto-generated SECRET_KEY."
fi

# Load environment variables from .env
export $(grep -v '^#' "$ENV_FILE" | xargs)

# 2. Ensure runtime data folders exist
mkdir -p /app/data /app/modules /app/tools

# 3. Handle Permission Adjustments for Mounted Volumes
# (Fixes permission errors when local host users map volumes)
chmod -R 775 /app/data /app/modules /app/tools || true

# Execute the main container command (Uvicorn)
exec "$@"