"""Message bus / store abstraction.

Default backend is **Redis Streams** — a durable, replayable log with consumer
groups and at-least-once delivery (the Kafka-like guarantees we need) without a
second cluster to operate. A Kafka backend is provided as a drop-in for the
scale/team phase; select it with BUS_BACKEND=kafka.

Why not Kafka by default: at single-user MVP scale a Kafka broker (KRaft +
partitions + ops) is unjustified. Redis Streams covers durability, consumer
groups, pending-entry reclaim and replay. The interface below is identical for
both, so swapping later is config-only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .config import Settings
from . import redis_client


@dataclass
class Message:
    id: str               # bus message id (stream id / offset)
    event: str
    payload: dict
    outbox_id: int | None


class MessageBus(Protocol):
    async def publish(self, *, event: str, payload: dict, outbox_id: int | None = None) -> str: ...
    async def ensure_group(self) -> None: ...
    async def consume(self, *, consumer: str, count: int = 10, block_ms: int = 2000) -> list[Message]: ...
    async def ack(self, message_id: str) -> None: ...
    async def depth(self) -> int: ...


class RedisStreamBus:
    """Redis Streams implementation (XADD / XREADGROUP / XACK)."""

    def __init__(self, settings: Settings) -> None:
        self.stream = settings.bus_stream
        self.group = settings.bus_group

    async def ensure_group(self) -> None:
        r = redis_client.client()
        try:
            # MKSTREAM creates the stream if absent; ignore "BUSYGROUP" on restart.
            await r.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, *, event: str, payload: dict, outbox_id: int | None = None) -> str:
        r = redis_client.client()
        fields = {"event": event, "payload": json.dumps(payload), "outbox_id": str(outbox_id or "")}
        return await r.xadd(self.stream, fields)

    async def consume(self, *, consumer: str, count: int = 10, block_ms: int = 2000) -> list[Message]:
        r = redis_client.client()
        resp = await r.xreadgroup(self.group, consumer, {self.stream: ">"}, count=count, block=block_ms)
        out: list[Message] = []
        for _stream, entries in resp or []:
            for msg_id, fields in entries:
                out.append(Message(
                    id=msg_id,
                    event=fields.get("event", ""),
                    payload=json.loads(fields.get("payload") or "{}"),
                    outbox_id=int(fields["outbox_id"]) if fields.get("outbox_id") else None,
                ))
        return out

    async def ack(self, message_id: str) -> None:
        await redis_client.client().xack(self.stream, self.group, message_id)

    async def depth(self) -> int:
        try:
            return int(await redis_client.client().xlen(self.stream))
        except Exception:
            return 0


class KafkaBus:
    """Kafka drop-in for the scale phase (BUS_BACKEND=kafka).

    Wire aiokafka here when needed; the surrounding code is unchanged.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ensure_group(self) -> None:
        raise NotImplementedError("Kafka backend: add aiokafka producer/consumer (scale phase)")

    async def publish(self, *, event: str, payload: dict, outbox_id: int | None = None) -> str:
        raise NotImplementedError("Kafka backend not wired yet")

    async def consume(self, *, consumer: str, count: int = 10, block_ms: int = 2000) -> list[Message]:
        raise NotImplementedError("Kafka backend not wired yet")

    async def ack(self, message_id: str) -> None:
        raise NotImplementedError("Kafka backend not wired yet")

    async def depth(self) -> int:
        return 0


def get_bus(settings: Settings) -> MessageBus:
    if settings.bus_backend == "kafka":
        return KafkaBus(settings)
    return RedisStreamBus(settings)
