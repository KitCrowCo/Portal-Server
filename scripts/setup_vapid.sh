#!/bin/sh
# Auto-generate VAPID keys if not already set.
# Writes to /app/data/vapid.env which is sourced by the entrypoint.
# Admin can override by setting VAPID_PRIVATE_KEY in docker-compose.yml environment.

VAPID_FILE="/app/data/vapid.env"

if [ -n "$VAPID_PRIVATE_KEY" ]; then
    echo "✓ VAPID keys already set in environment."
    exit 0
fi

if [ -f "$VAPID_FILE" ]; then
    echo "✓ Loading existing VAPID keys from $VAPID_FILE"
    . "$VAPID_FILE"
    export VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY
    exit 0
fi

echo "⚙ Generating VAPID keys for push notifications..."
python3 - << 'PYEOF'
import os
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
priv = v.private_key
pub  = v.public_key
with open("/app/data/vapid.env", "w") as f:
    f.write(f"VAPID_PRIVATE_KEY={priv}\n")
    f.write(f"VAPID_PUBLIC_KEY={pub}\n")
    f.write(f'VAPID_CLAIMS_SUB=mailto:admin@localhost\n')
print(f"✓ VAPID keys generated and saved to /app/data/vapid.env")
print(f"  Public key: {pub}")
print(f"  Keys are stored outside the container image in your data volume.")
print(f"  To use a custom key, set VAPID_PRIVATE_KEY in your docker-compose.yml")
PYEOF
. "$VAPID_FILE"
export VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY VAPID_CLAIMS_SUB