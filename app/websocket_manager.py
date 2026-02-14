"""
WebSocket connection manager for real-time session updates.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket

from app.logging_config import get_logger

logger = get_logger("websocket")


class ConnectionManager:
    """Manages WebSocket connections grouped by session code."""

    def __init__(self):
        # Map of session_code -> set of WebSocket connections
        self.active_connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_code: str):
        """Accept a new WebSocket connection and add to session group."""
        await websocket.accept()
        async with self._lock:
            if session_code not in self.active_connections:
                self.active_connections[session_code] = set()
            self.active_connections[session_code].add(websocket)
            count = len(self.active_connections[session_code])
        logger.info(f"WebSocket connected to session {session_code}, total: {count}")

    async def disconnect(self, websocket: WebSocket, session_code: str):
        """Remove a WebSocket connection from session group."""
        async with self._lock:
            if session_code in self.active_connections:
                self.active_connections[session_code].discard(websocket)
                count = len(self.active_connections[session_code])
                # Clean up empty sessions
                if not self.active_connections[session_code]:
                    del self.active_connections[session_code]
                    count = 0
            else:
                count = 0
        logger.info(
            f"WebSocket disconnected from session {session_code}, remaining: {count}"
        )

    async def broadcast_to_session(self, session_code: str, message: dict):
        """Send a message to all connections in a session."""
        async with self._lock:
            connections = self.active_connections.get(session_code, set()).copy()

        if not connections:
            return

        message_json = json.dumps(message)
        dead_connections = []

        for connection in connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.append(connection)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for conn in dead_connections:
                    if session_code in self.active_connections:
                        self.active_connections[session_code].discard(conn)

    async def notify_session_update(self, session_code: str, update_type: str = "sync"):
        """Notify all clients in a session that data has changed."""
        await self.broadcast_to_session(
            session_code,
            {
                "type": update_type,
                "session_code": session_code,
            },
        )

    def get_connection_count(self, session_code: str) -> int:
        """Get number of active connections for a session."""
        return len(self.active_connections.get(session_code, set()))


# Global connection manager instance
manager = ConnectionManager()
