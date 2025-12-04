FROM python:3.11-slim

# Install basic tools the agent will likely need
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    openssh-client \
    build-essential \
    curl \
    ca-certificates \
    nodejs \
    npm \
 && rm -rf /var/lib/apt/lists/*

# Pre-install wrangler to avoid npx interactive prompts
RUN npm install -g wrangler@latest

# Ensure writable config/cache locations for the non-root user
RUN mkdir -p /tmp/.config /tmp/.npm-cache && chmod 1777 /tmp/.config /tmp/.npm-cache
ENV XDG_CONFIG_HOME=/tmp/.config

# Create an unprivileged user to avoid running as root
ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} \
    && mkdir -p /home/${USERNAME}/.ssh \
    && chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}

# Work in the project root (this will be the mounted directory)
WORKDIR /workspace

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Default to an interactive shell as non-root
USER ${USERNAME}
ENV HOME /home/${USERNAME}
CMD ["bash"]
