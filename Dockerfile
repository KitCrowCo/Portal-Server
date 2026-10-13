FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/core_files:/app \
    PORT=8000 \
    MODULES_PATH="/app/modules" \
    ADMIN_USER="admin" \
    ADMIN_PASS="admin" \
    SERVER_TITLE="Dashboard"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git netcat-openbsd sqlite3 ca-certificates build-essential libglib2.0-0 graphviz \
    && rm -rf /var/lib/apt/lists/*

# Configure Git context
RUN git config --global safe.directory "*" \
 && git config --global init.defaultBranch main \
 && git config --global user.email "portal@localhost" \
 && git config --global user.name "Portal Server"

# Secure user context and file permissions
RUN useradd --create-home --shell /bin/bash portal \
 && mkdir -p /app/data /app/modules /app/core_files \
 && chown -R portal:portal /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Download default frictionless modules (Wiki & RP Server)
RUN git clone https://github.com/KitCrowCo/Portal-Server_Module_Wiki.git /app/modules/wiki \
 && git clone https://github.com/KitCrowCo/Portal-Server_Module_Rp_Server.git /app/modules/rp_server \
 && rm -rf /app/modules/*/.git

# Copy base project structure
COPY core_files ./core_files
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Fix permissions for the portal user
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && chown -R portal:portal /app/core_files /app/modules

# Drop root privileges
USER portal

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "core_files.main:app", "--host", "0.0.0.0", "--port", "8000"]