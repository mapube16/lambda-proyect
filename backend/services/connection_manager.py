"""
connection_manager.py — No-op stub.

WebSocket removed in favour of HTTP polling (/api/runs/{run_id}/status).
Stub kept so cobranza and other modules compile without changes.
"""


class _NoOpManager:
    async def connect(self, websocket=None, user_id: str = "") -> None:
        pass

    def disconnect(self, user_id: str) -> None:
        pass

    async def send_to_user(self, user_id: str, message: dict) -> None:
        pass

    async def broadcast(self, message: dict) -> None:
        pass


manager = _NoOpManager()
