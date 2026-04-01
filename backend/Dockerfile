FROM python:3.13-slim
LABEL maintainer twtrubiks
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 建立非 root 使用者
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /sync-docs

# 安裝 uv（以 root 安裝到全域路徑）
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

# 先複製 requirements.txt 安裝依賴（利用 Docker layer cache）
COPY requirements.txt .
RUN uv pip install --no-cache --system -r requirements.txt

# 再複製其餘程式碼
COPY . .

RUN chmod +x /sync-docs/entrypoint.sh && \
    chown -R appuser:appuser /sync-docs

# 切換為非 root 使用者
USER appuser

ENTRYPOINT ["/sync-docs/entrypoint.sh"]