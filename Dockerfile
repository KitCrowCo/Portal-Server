FROM python:3.11-slim

# System deps — git is required by the Development Studio for repo management
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    netcat-openbsd \
    sqlite3 \
    ca-certificates \
    build-essential \
    libglib2.0-0 \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Configure git globals:
#   safe.directory=* — prevents "dubious ownership" when container runs as root
#                      but volume-mounted files are owned by your host UID
#   identity         — required for commits
#   defaultBranch    — use 'main' not 'master'
RUN git config --global safe.directory "*" \
 && git config --global init.defaultBranch main \
 && git config --global user.email "munin742@gmail.com" \
 && git config --global user.name "joshua"

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Ports: 8000 for FastAPI
ENV PORT=8000
ENV MODULES_PATH="/app/modules"
ENV ADMIN_USER="admin"
ENV ADMIN_PASS="admin"
ENV SERVER_TITLE="Dashboard"

# Make start script executable
# RUN chmod 755 /app/start.sh

EXPOSE 80 443 8000

# Note: only the LAST CMD runs. Setup scripts should be called from start.sh or entrypoint.
# Tee to /tmp/server.log so the Dev Studio debug panel can read it.
#CMD ["sh", "-c", ". /app/scripts/setup_vapid.sh 2>/dev/null || true; uvicorn core_files.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee /tmp/server.log"]


# The commands after --reload are for giving docker logs a pipe to view remotely
CMD ["sh", "-c", "uvicorn core_files.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee /tmp/server.log"]
