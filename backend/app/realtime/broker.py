from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from fastapi import WebSocket
from redis.asyncio import Redis

from app.jobs.outbox import CHANNEL


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: str) -> None:
        async with self._lock:
            sockets = tuple(self._connections)
        dead: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(socket)
        if dead:
            async with self._lock:
                self._connections.difference_update(dead)

    async def resync_required(self) -> None:
        now = datetime.now(UTC)
        event_id = uuid.uuid4()
        await self.broadcast(
            json.dumps(
                {
                    "event_id": str(event_id),
                    "type": "resync_required",
                    "occurred_at": now.isoformat(),
                    "entity_id": None,
                    "version": 1,
                    "series_id": None,
                }
            )
        )


async def subscribe(redis_url: str, manager: ConnectionManager) -> None:
    """Reconnect forever; recovery tells clients to refetch authoritative HTTP state."""
    failed = False
    delay = 1.0
    while True:
        client = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(CHANNEL)
            if failed:
                await manager.resync_required()
            failed, delay = False, 1.0
            async for message in pubsub.listen():
                if message.get("type") != "message" or not isinstance(message.get("data"), str):
                    continue
                try:
                    payload = json.loads(message["data"])
                    if (
                        not isinstance(payload, dict)
                        or not isinstance(payload.get("event_id"), str)
                        or not isinstance(payload.get("type"), str)
                    ):
                        continue
                except (json.JSONDecodeError, TypeError):
                    continue
                await manager.broadcast(message["data"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            if not failed:
                await manager.resync_required()
            failed = True
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            await pubsub.aclose()
            await client.aclose()
