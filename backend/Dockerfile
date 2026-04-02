FROM python:3.13-slim
LABEL maintainer twtrubiks
ENV PYTHONUNBUFFERED=1

# 建立非 root 使用者
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /sync-docs

# 安裝 uv（從官方映像複製靜態二進位檔到共享路徑）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

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