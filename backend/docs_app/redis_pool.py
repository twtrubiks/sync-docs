"""
統一 Redis 連接池管理

所有需要 Redis 連線的模組都應從此處取得連線，
避免各自建立獨立的連線池，浪費資源。
"""

import logging

import redis.asyncio as aioredis
import redis as sync_redis
from django.conf import settings

logger = logging.getLogger('docs_app')

_async_redis = None
_sync_redis = None


def _get_host_port():
    """取得 Redis 主機與埠號配置"""
    host = getattr(settings, 'REDIS_HOST', 'django-redis')
    port = int(getattr(settings, 'REDIS_PORT', 6379))
    return host, port


async def get_async_redis() -> aioredis.Redis:
    """取得共用的 async Redis 連線（懶加載）"""
    global _async_redis
    if _async_redis is None:
        host, port = _get_host_port()
        _async_redis = aioredis.Redis(
            host=host,
            port=port,
            decode_responses=True
        )
    return _async_redis


def get_sync_redis() -> sync_redis.Redis:
    """取得共用的 sync Redis 連線（懶加載，給非 async 場景用）"""
    global _sync_redis
    if _sync_redis is None:
        host, port = _get_host_port()
        _sync_redis = sync_redis.Redis(
            host=host,
            port=port,
            decode_responses=True
        )
    return _sync_redis


async def close_async_redis():
    """關閉 async Redis 連線（用於 shutdown 清理）"""
    global _async_redis
    if _async_redis is not None:
        await _async_redis.aclose()
        _async_redis = None
        logger.info("Async Redis 連線已關閉")


def close_sync_redis():
    """關閉 sync Redis 連線（用於 shutdown 清理）"""
    global _sync_redis
    if _sync_redis is not None:
        _sync_redis.close()
        _sync_redis = None
        logger.info("Sync Redis 連線已關閉")
