FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git netcat-openbsd sqlite3 ca-certificates build-essential libglib2.0-0 graphviz \
    && rm -rf /var/lib/apt/lists/*

# Configure Git context
RUN git config --global safe.directory "*" \
 && git config --global init.defaultBranch main \
 && git config --global user.email "portal@localhost" \
 && git config --global user.name "Portal Server"

WORKDIR /app

# Install Python packages first (optimizes Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy local files
COPY core_files/ ./core_files/
COPY modules/ ./modules/
COPY tools/ ./tools/

# ----------------------------------------------------------------------
# AUTOMATIC REFERENCE INSTALLER
# Replaces install.sh. If the user hasn't cloned the reference modules 
# locally, Docker fetches them directly during the build phase.
# ----------------------------------------------------------------------
ARG GITEA_BASE="https://git.kitcrowco.com/KitCrowCo"
RUN bash -c ' \
    MODULES=("Portal-Server_Module_Wiki:wiki" "Portal-Server_Module_Rp_Server:rp_server") \
    && TOOLS=("Portal-Server_Tool_Git_Manager:git_manager") \
    && for pair in "${MODULES[@]}"; do \
        IFS=":" read -r repo dest <<< "$pair"; \
        if [ ! -d "modules/$dest/.git" ]; then \
            rm -rf "modules/$dest"; \
            git clone "${GITEA_BASE}/${repo}.git" "modules/${dest}"; \
        fi; \
    done \
    && for pair in "${TOOLS[@]}"; do \
        IFS=":" read -r repo dest <<< "$pair"; \
        if [ ! -d "tools/$dest/.git" ]; then \
            rm -rf "tools/$dest"; \
            git clone "${GITEA_BASE}/${repo}.git" "tools/${dest}"; \
        fi; \
    done \
'

# Secure user context and file permissions
RUN useradd --create-home --shell /bin/bash portal \
 && mkdir -p /app/data \
 && chown -R portal:portal /app

USER portal

ENV PORT=8000
ENV MODULES_PATH="/app/modules"
ENV ADMIN_USER="admin"
ENV ADMIN_PASS="admin"
ENV SERVER_TITLE="Dashboard"

EXPOSE 80 443 8000

CMD ["uvicorn", "core_files.main:app", "--host", "0.0.0.0", "--port", "8000"]