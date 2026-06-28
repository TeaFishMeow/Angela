from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass
class Bus:
    ws: WebSocket
    seq: int = 0

    async def send(self, type_: str, data: dict[str, Any] | None = None, ts: float = 0.0) -> None:
        self.seq += 1
        envelope = {
            "type": type_,
            "seq": self.seq,
            "ts": round(ts, 3),
            "data": data or {},
        }
        await self.ws.send_text(json.dumps(envelope, ensure_ascii=False))


def now_ts() -> float:
    return time.time()
