import asyncio
from app.config import LISTEN_HOST, LISTEN_PORT

BANNER = b"\x05\xff"

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        data = await reader.read(262)
        if not data:
            writer.close()
            await writer.wait_closed()
            return
        writer.write(BANNER)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
