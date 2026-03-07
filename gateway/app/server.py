import asyncio
import socket
import struct
from contextlib import suppress

from app.auth import close_connection as api_close_connection
from app.auth import close_session as api_close_session
from app.auth import open_connection as api_open_connection
from app.auth import open_session as api_open_session
from app.auth import reroute_session as api_reroute_session
from app.auth import resolve_auth, session_state
from app.config import KILL_POLL_INTERVAL, LISTEN_HOST, LISTEN_PORT, UPSTREAM_CONNECT_TIMEOUT
from app.connection_manager import connection_manager
from app.kill_switch import kill_requested
from app.session_manager import session_manager
from app.traffic_meter import traffic_meter

SOCKS_VERSION = 5
NO_ACCEPTABLE = b"\x05\xff"
USERPASS_METHOD = b"\x05\x02"
AUTH_SUCCESS = b"\x01\x00"
AUTH_FAIL = b"\x01\x01"
REPLY_SUCCEEDED = 0x00
REPLY_GENERAL_FAILURE = 0x01
REPLY_COMMAND_NOT_SUPPORTED = 0x07


def _reply(code: int, bind_host: str = "0.0.0.0", bind_port: int = 0) -> bytes:
    return b"\x05" + bytes([code]) + b"\x00\x01" + socket.inet_aton(bind_host) + struct.pack("!H", bind_port)


async def read_exact(reader: asyncio.StreamReader, size: int) -> bytes:
    return await reader.readexactly(size)


async def negotiate_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    head = await read_exact(reader, 2)
    ver, nmethods = head[0], head[1]
    if ver != SOCKS_VERSION:
        raise RuntimeError("unsupported socks version")
    methods = await read_exact(reader, nmethods)
    if 0x02 not in methods:
        writer.write(NO_ACCEPTABLE)
        await writer.drain()
        raise RuntimeError("username/password auth required")
    writer.write(USERPASS_METHOD)
    await writer.drain()


async def authenticate_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, client_ip: str):
    ver = (await read_exact(reader, 1))[0]
    if ver != 0x01:
        writer.write(AUTH_FAIL)
        await writer.drain()
        raise RuntimeError("invalid auth version")
    ulen = (await read_exact(reader, 1))[0]
    username = (await read_exact(reader, ulen)).decode(errors="ignore")
    plen = (await read_exact(reader, 1))[0]
    password = (await read_exact(reader, plen)).decode(errors="ignore")
    result = await resolve_auth(username, password, client_ip)
    if not result.get("ok"):
        writer.write(AUTH_FAIL)
        await writer.drain()
        raise RuntimeError("invalid credentials")
    writer.write(AUTH_SUCCESS)
    await writer.drain()
    return username, result["account"]


async def read_request(reader: asyncio.StreamReader):
    ver, cmd, _rsv, atyp = await read_exact(reader, 4)
    if ver != SOCKS_VERSION:
        raise RuntimeError("invalid request version")
    if atyp == 0x01:
        addr = socket.inet_ntoa(await read_exact(reader, 4))
    elif atyp == 0x03:
        ln = (await read_exact(reader, 1))[0]
        addr = (await read_exact(reader, ln)).decode(errors="ignore")
    elif atyp == 0x04:
        addr = socket.inet_ntop(socket.AF_INET6, await read_exact(reader, 16))
    else:
        raise RuntimeError("unsupported atyp")
    port = struct.unpack("!H", await read_exact(reader, 2))[0]
    return cmd, addr, port


async def open_via_upstream(proxy: dict, target_host: str, target_port: int):
    reader, writer = await asyncio.wait_for(asyncio.open_connection(proxy["host"], proxy["port"]), timeout=UPSTREAM_CONNECT_TIMEOUT)
    methods = [0x00]
    if proxy.get("auth_username"):
        methods = [0x02]
    writer.write(bytes([0x05, len(methods), *methods]))
    await writer.drain()
    resp = await read_exact(reader, 2)
    if resp[1] == 0xFF:
        raise RuntimeError("upstream auth method rejected")
    if resp[1] == 0x02:
        u = proxy.get("auth_username", "").encode()
        p = proxy.get("auth_password", "").encode()
        writer.write(bytes([0x01, len(u)]) + u + bytes([len(p)]) + p)
        await writer.drain()
        auth_resp = await read_exact(reader, 2)
        if auth_resp[1] != 0x00:
            raise RuntimeError("upstream auth failed")
    try:
        raw = socket.inet_aton(target_host)
        atyp = 0x01
        addr = raw
    except OSError:
        atyp = 0x03
        enc = target_host.encode()
        addr = bytes([len(enc)]) + enc
    writer.write(b"\x05\x01\x00" + bytes([atyp]) + addr + struct.pack("!H", target_port))
    await writer.drain()
    resp = await read_exact(reader, 4)
    rep, atyp = resp[1], resp[3]
    if rep != 0x00:
        raise RuntimeError(f"upstream connect failed: {rep}")
    if atyp == 0x01:
        await read_exact(reader, 4)
    elif atyp == 0x03:
        ln = (await read_exact(reader, 1))[0]
        await read_exact(reader, ln)
    elif atyp == 0x04:
        await read_exact(reader, 16)
    await read_exact(reader, 2)
    return reader, writer


async def relay(src: asyncio.StreamReader, dst: asyncio.StreamWriter, session_id: str, connection_id: str, count_incoming: bool):
    total = 0
    last_kill_check = 0.0
    try:
        while True:
            chunk = await src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
            await dst.drain()
            if count_incoming:
                traffic_meter.add_local(connection_id, len(chunk), 0)
            else:
                traffic_meter.add_local(connection_id, 0, len(chunk))
            total += len(chunk)
            await traffic_meter.maybe_flush(session_id, connection_id)
            now = asyncio.get_running_loop().time()
            if now - last_kill_check >= KILL_POLL_INTERVAL:
                last_kill_check = now
                if await kill_requested(session_id):
                    break
    except Exception:
        pass
    return total


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    client_ip = peer[0] if peer else "0.0.0.0"
    session_id = None
    connection_id = None
    upstream_writer = None
    total_in = 0
    total_out = 0
    close_state = 'closed'
    close_reason = 'completed'
    try:
        await negotiate_client(reader, writer)
        username, account = await authenticate_client(reader, writer, client_ip)
        session_resp = await api_open_session(account["id"], client_ip, username)
        session_id = session_resp["session_id"]
        session_manager.set(session_id, session_resp)

        cmd, target_host, target_port = await read_request(reader)
        if cmd != 0x01:
            writer.write(_reply(REPLY_COMMAND_NOT_SUPPORTED))
            await writer.drain()
            close_state = 'failed'
            close_reason = 'command not supported'
            return

        attempted_proxy_ids = []
        for attempt in range(3):
            conn_resp = await api_open_connection(session_id, target_host, target_port)
            proxy = conn_resp.get("proxy")
            connection_id = conn_resp.get("connection_id")
            if not proxy:
                writer.write(_reply(REPLY_GENERAL_FAILURE))
                await writer.drain()
                close_state = 'failed'
                close_reason = 'no upstream proxy available'
                return
            connection_manager.add(connection_id, {"session_id": session_id, "proxy": proxy})
            try:
                upstream_reader, upstream_writer = await open_via_upstream(proxy, target_host, target_port)
                break
            except Exception as exc:
                attempted_proxy_ids.append(proxy.get('id'))
                bytes_in, bytes_out = await traffic_meter.flush_all(session_id, connection_id)
                await api_close_connection(connection_id, bytes_in, bytes_out, 'failed', f'upstream connect failed: {exc}')
                connection_manager.remove(connection_id)
                traffic_meter.clear(connection_id)
                connection_id = None
                if attempt >= 2:
                    raise
                reroute_resp = await api_reroute_session(
                    session_id,
                    reason=f'upstream connect failed for {target_host}:{target_port}',
                    exclude_proxy_ids=[pid for pid in attempted_proxy_ids if pid is not None],
                    prefer_sticky=False,
                )
                if not reroute_resp.get('proxy'):
                    raise RuntimeError(f'no alternate upstream proxy available after failure: {exc}')
        writer.write(_reply(REPLY_SUCCEEDED))
        await writer.drain()

        task1 = asyncio.create_task(relay(reader, upstream_writer, session_id, connection_id, True))
        task2 = asyncio.create_task(relay(upstream_reader, writer, session_id, connection_id, False))
        done, pending = await asyncio.wait({task1, task2}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task is task1 and not task.cancelled():
                total_in += task.result()
            elif task is task2 and not task.cancelled():
                total_out += task.result()

        if task1 in done:
            with suppress(Exception):
                upstream_writer.write_eof()
                await upstream_writer.drain()
        if task2 in done:
            with suppress(Exception):
                writer.write_eof()
                await writer.drain()

        if pending:
            more_done, still_pending = await asyncio.wait(pending, timeout=15)
            for task in more_done:
                if task is task1 and not task.cancelled():
                    total_in += task.result()
                elif task is task2 and not task.cancelled():
                    total_out += task.result()
            for task in still_pending:
                task.cancel()
                with suppress(Exception):
                    await task
        bytes_in, bytes_out = await traffic_meter.flush_all(session_id, connection_id)
        total_in = max(total_in, bytes_in)
        total_out = max(total_out, bytes_out)
        state = await session_state(session_id)
        if state.get('kill_requested'):
            close_state = 'killed'
            close_reason = state.get('kill_reason') or 'killed'
        await api_close_connection(connection_id, total_in, total_out, close_state, close_reason)
    except asyncio.IncompleteReadError:
        close_state = 'failed'
        close_reason = 'client disconnected'
        if connection_id and session_id:
            bytes_in, bytes_out = await traffic_meter.flush_all(session_id, connection_id)
            await api_close_connection(connection_id, bytes_in, bytes_out, close_state, close_reason)
    except Exception as exc:
        close_state = 'failed'
        close_reason = str(exc)
        if connection_id and session_id:
            bytes_in, bytes_out = await traffic_meter.flush_all(session_id, connection_id)
            await api_close_connection(connection_id, bytes_in, bytes_out, close_state, close_reason)
    finally:
        if upstream_writer:
            upstream_writer.close()
            with suppress(Exception):
                await upstream_writer.wait_closed()
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()
        if session_id:
            try:
                state = await session_state(session_id)
                final_status = 'killed' if state.get('kill_requested') else 'closed'
            except Exception:
                final_status = 'closed'
            await api_close_session(session_id, final_status)
            session_manager.delete(session_id)
        if connection_id:
            connection_manager.remove(connection_id)
            traffic_meter.clear(connection_id)


async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
