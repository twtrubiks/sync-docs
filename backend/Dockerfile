FROM python:3.12-slim
LABEL maintainer twtrubiks
ENV PYTHONUNBUFFERED 1

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /sync-docs
WORKDIR /sync-docs
COPY . /sync-docs/

# Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

# Use uv to install packages
RUN uv pip install --no-cache --system -r requirements.txt

# for entry point
RUN chmod +x /sync-docs/entrypoint.sh

# 設定 entrypoint
ENTRYPOINT ["/sync-docs/entrypoint.sh"]