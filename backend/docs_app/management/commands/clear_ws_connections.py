"""
Django management command to clear stale WebSocket connection records.

Usage:
  # List all connection records
  python manage.py clear_ws_connections --list

  # Clear all connections for a specific user
  python manage.py clear_ws_connections --user-id=123

  # Clear all connection records
  python manage.py clear_ws_connections --all
"""

import asyncio

import redis.asyncio as redis
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Clear stale WebSocket connection records from Redis'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Clear connections for a specific user ID'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear ALL connection records (use with caution)'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all connection keys without deleting'
        )

    def handle(self, *args, **options):
        asyncio.run(self._handle_async(**options))

    async def _handle_async(self, **options):
        redis_host = getattr(settings, 'REDIS_HOST', 'django-redis')
        redis_port = int(getattr(settings, 'REDIS_PORT', 6379))

        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )

        try:
            if options['list']:
                await self._list_connections(r)
            elif options['user_id']:
                await self._clear_user(r, options['user_id'])
            elif options['all']:
                await self._clear_all(r)
            else:
                self.stdout.write(self.style.WARNING(
                    'Please specify --user-id, --all, or --list'
                ))
        finally:
            await r.aclose()

    async def _list_connections(self, r):
        """List all connection keys and their members"""
        keys = []
        async for key in r.scan_iter(match='ws:connections:user:*'):
            keys.append(key)

        if not keys:
            self.stdout.write('No connection records found.')
            return

        self.stdout.write(f'\nFound {len(keys)} connection key(s):\n')
        for key in sorted(keys):
            members = await r.smembers(key)
            ttl = await r.ttl(key)
            user_id = key.split(':')[-1]
            self.stdout.write(f'  User {user_id}:')
            self.stdout.write(f'    Connections ({len(members)}): {list(members)}')
            ttl_str = f'{ttl} seconds' if ttl > 0 else 'no expiry' if ttl == -1 else 'expired'
            self.stdout.write(f'    TTL: {ttl_str}')

    async def _clear_user(self, r, user_id):
        """Clear connections for a specific user"""
        key = f'ws:connections:user:{user_id}'
        count = await r.scard(key)
        if count == 0:
            self.stdout.write(f'No connections found for user {user_id}')
            return
        await r.delete(key)
        self.stdout.write(self.style.SUCCESS(
            f'Cleared {count} connection(s) for user {user_id}'
        ))

    async def _clear_all(self, r):
        """Clear all connection records"""
        keys = []
        async for key in r.scan_iter(match='ws:connections:user:*'):
            keys.append(key)

        if not keys:
            self.stdout.write('No connection records to clear.')
            return

        total_connections = 0
        for key in keys:
            count = await r.scard(key)
            total_connections += count
            await r.delete(key)

        self.stdout.write(self.style.SUCCESS(
            f'Cleared {total_connections} connection(s) across {len(keys)} user(s)'
        ))
