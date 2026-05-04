"""kRPC connection management — single shared client across all tools."""

import os

import krpc

_conn: krpc.Client | None = None


def get_connection() -> krpc.Client:
    global _conn
    if _conn is None or not _is_alive(_conn):
        host = os.environ.get("KRPC_HOST", "127.0.0.1")
        rpc_port = int(os.environ.get("KRPC_RPC_PORT", "50000"))
        stream_port = int(os.environ.get("KRPC_STREAM_PORT", "50001"))
        _conn = krpc.connect(
            name="krpc-mcp",
            address=host,
            rpc_port=rpc_port,
            stream_port=stream_port,
        )
    return _conn


def _is_alive(conn: krpc.Client) -> bool:
    try:
        conn.krpc.get_status()
        return True
    except Exception:
        return False


def close_connection() -> None:
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None
