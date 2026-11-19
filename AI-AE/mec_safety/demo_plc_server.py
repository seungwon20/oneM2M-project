import asyncio
import json


async def handle_client(reader, writer):
    addr = writer.get_extra_info("peername")
    print(f"[MOCK PLC] Connected: {addr}")

    try:
        while True:
            data = await reader.readline()

            if not data:
                break

            try:
                message = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            print(f"[MOCK PLC] Received: {message}")

            if message.get("command") == "STOP":
                print("[MOCK PLC] STOP COMMAND RECEIVED")
                print("[MOCK PLC] Conveyor stopped (simulation)")

                response = {
                    "type": "ACK",
                    "command_id": message["command_id"],
                    "status": "STOP_ACCEPTED"
                }

                writer.write(
                    json.dumps(response).encode("utf-8") + b"\n"
                )
                await writer.drain()

                status = {
                    "type": "STATUS",
                    "command_id": message["command_id"],
                    "status": "STOPPED",
                    "is_rotating": False
                }

                writer.write(
                    json.dumps(status).encode("utf-8") + b"\n"
                )
                await writer.drain()

    finally:
        print("[MOCK PLC] Disconnected")
        writer.close()
        await writer.wait_closed()


async def main():
    server = await asyncio.start_server(
        handle_client,
        "127.0.0.1",
        9001
    )

    print("[MOCK PLC] Listening on 127.0.0.1:9001")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())