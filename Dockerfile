FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/core_files:/app \
    PORT=8000 \
    MODULES_PATH="/app/modules" \
    ADMIN_USER="admin" \
    ADMIN_PASS="admin" \
    SERVER_TITLE="Dashboard" \
    TZ="UTC"
# TZ: the server's time zone ("today" in Finance, Muninn, Huginn) - override in docker-compose, e.g. TZ=America/Los_Angeles

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl git netcat-openbsd sqlite3 ca-certificates build-essential libglib2.0-0 graphviz tzdata && rm -rf /var/lib/apt/lists/*

# Git globals: safe.directory=* (no "dubious ownership" for mounted folders owned by the host user), default branch main.
# No commit identity here: Git Manager's sync commits as the portal user who pushes (users in data/git_manager/sync.json).
RUN git config --global safe.directory "*" && git config --global init.defaultBranch main

# Secure user context and file permissions
RUN useradd --create-home --shell /bin/bash portal && mkdir -p /app/data /app/modules /app/core_files
#&& chown -R portal:portal /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip &&  pip install --no-cache-dir -r requirements.txt

# App code
COPY . .
COPY core_files/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Fix permissions for the portal user
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
#&& chown -R portal:portal /app/core_files /app/modules

# Drop root privileges
USER portal

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]

# Note: only the LAST CMD runs. Setup scripts should be called from start.sh or entrypoint.
# Tee to /tmp/server.log so the Dev Studio debug panel can read it.
#CMD ["sh", "-c", ". /app/scripts/setup_vapid.sh 2>/dev/null || true; uvicorn core_files.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee /tmp/server.log"]

# The commands after --reload are for giving docker logs a pipe to view remotely
# --reload-dir: only the code folders restart the portal. Without it every .py file written anywhere under /app restarts it - a git pull of code checkouts under data/ (Kimi, Git Manager), an upload - cutting off running passes and making drawn file trees stale.
CMD ["sh", "-c", "uvicorn core_files.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir core_files --reload-dir modules --reload-dir tools 2>&1 | tee /tmp/server.log"]