"""kRPC connection management — single shared client across all tools."""

import logging
import os

import krpc

logger = logging.getLogger(__name__)

_conn: krpc.Client | None = None


def get_connection() -> krpc.Client:
    global _conn
    if _conn is None:
        _conn = _connect()
    elif not _is_alive(_conn):
        logger.info("kRPC connection lost; reconnecting")
        _conn = _connect()
    return _conn


def _connect() -> krpc.Client:
    host = os.environ.get("KRPC_HOST", "127.0.0.1")
    rpc_port = int(os.environ.get("KRPC_RPC_PORT", "50000"))
    stream_port = int(os.environ.get("KRPC_STREAM_PORT", "50001"))
    logger.info("Connecting to kRPC at %s (rpc=%d, stream=%d)", host, rpc_port, stream_port)
    try:
        conn = krpc.connect(
            name="krpc-mcp",
            address=host,
            rpc_port=rpc_port,
            stream_port=stream_port,
        )
        logger.info("Connected to kRPC at %s", host)
        return conn
    except Exception:
        logger.error("Failed to connect to kRPC at %s (rpc=%d, stream=%d)", host, rpc_port, stream_port, exc_info=True)
        raise


def _is_alive(conn: krpc.Client) -> bool:
    logger.debug("Checking kRPC connection liveness")
    try:
        conn.krpc.get_status()
        return True
    except Exception:
        logger.warning("kRPC connection alive check failed", exc_info=True)
        return False


def close_connection() -> None:
    global _conn
    logger.debug("close_connection called (conn=%s)", "open" if _conn is not None else "None")
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            logger.warning("Exception while closing kRPC connection", exc_info=True)
        _conn = None
