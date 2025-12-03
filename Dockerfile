FROM python:3.11-slim

# Install basic tools the agent will likely need
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    openssh-client \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Work in the project root (this will be the mounted directory)
WORKDIR /workspace

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Default to an interactive shell
CMD ["bash"]
