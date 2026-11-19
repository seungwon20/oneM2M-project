import asyncio
import json
import uuid


class DemoPLCClient:

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9001,
    ):
        self.host = host
        self.port = port

        self.reader = None
        self.writer = None

        self.lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return (
            self.writer is not None
            and not self.writer.is_closing()
        )

    async def connect(self):
        if self.connected:
            return

        self.reader, self.writer = await asyncio.open_connection(
            self.host,
            self.port
        )

        print("[AI APPLICATION] PLC TCP connected")

    async def close(self):
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()

        self.reader = None
        self.writer = None

    async def request_stop(self) -> dict:
        if not self.connected:
            return {
                "success": False,
                "error": "PLC TCP connection unavailable"
            }

        async with self.lock:
            command_id = str(uuid.uuid4())

            message = {
                "type": "COMMAND",
                "command_id": command_id,
                "command": "STOP",
                "risk_level": "CRITICAL"
            }

            try:
                # Send STOP over the existing TCP connection.
                self.writer.write(
                    json.dumps(message).encode("utf-8") + b"\n"
                )
                await self.writer.drain()

                # Receive command acknowledgment.
                ack_data = await asyncio.wait_for(
                    self.reader.readline(),
                    timeout=1.0
                )

                if not ack_data:
                    raise ConnectionError("PLC disconnected")

                ack = json.loads(ack_data.decode("utf-8"))

                # Receive simulated stop status.
                status_data = await asyncio.wait_for(
                    self.reader.readline(),
                    timeout=1.0
                )

                if not status_data:
                    raise ConnectionError("PLC status unavailable")

                status = json.loads(status_data.decode("utf-8"))

                success = (
                    ack.get("command_id") == command_id
                    and ack.get("status") == "STOP_ACCEPTED"
                    and status.get("command_id") == command_id
                    and status.get("status") == "STOPPED"
                )

                return {
                    "success": success,
                    "command_id": command_id,
                    "ack": ack,
                    "status": status
                }

            except (
                asyncio.TimeoutError,
                ConnectionError,
                OSError,
                json.JSONDecodeError
            ) as exc:
                return {
                    "success": False,
                    "command_id": command_id,
                    "error": str(exc)
                }