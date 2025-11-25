# app/utils_compress.py
"""
Shared compression utilities for end-to-end compressed data flow
- MQTT → Kafka: preserve compressed bytes with headers
- Kafka → WebSocket: forward compressed bytes unchanged
- Frontend: decompress for visualization
- Database: decompress only for row-wise writes
"""

import logging
import zlib

import orjson

try:
    import zstandard as zstd

    HAS_ZSTD = True
except Exception:
    HAS_ZSTD = False

logger = logging.getLogger(__name__)

# Magic headers for compression detection
MAGIC_ZSTD = b"ZSTD\0"  # 5 bytes
MAGIC_ZLIB = b"ZLIB\0"  # 5 bytes


def sniff_codec_from_magic(raw: bytes) -> str | None:
    """Detect compression codec from magic header in raw bytes"""
    if raw.startswith(MAGIC_ZSTD):
        return "zstd"
    if raw.startswith(MAGIC_ZLIB):
        return "zlib"
    return None


def codec_from_mqtt_props(properties) -> str | None:
    """Extract compression codec from MQTT v5 properties"""
    if not properties:
        return None

    up = getattr(properties, "UserProperty", None)
    if isinstance(up, list):
        for k, v in up:
            if k and v and k.lower() == "content-encoding":
                return v.lower()
    elif isinstance(up, tuple) and len(up) == 2 and up[0].lower() == "content-encoding":
        return up[1].lower()
    return None


def maybe_decompress(raw: bytes, codec: str | None = None) -> bytes:
    """
    Decompress raw bytes using specified codec or magic header detection.
    Use only if you *must* decode server-side (e.g., Timescale rows).
    """
    c = (codec or "").lower()

    if c == "zstd":
        if not HAS_ZSTD:
            raise RuntimeError("zstd not installed")
        d = zstd.ZstdDecompressor()
        if raw.startswith(MAGIC_ZSTD):
            raw = raw[len(MAGIC_ZSTD) :]
        return d.decompress(raw)

    if c == "zlib":
        if raw.startswith(MAGIC_ZLIB):
            raw = raw[len(MAGIC_ZLIB) :]
        return zlib.decompress(raw)

    # No codec specified? Try magic sniff:
    if raw.startswith(MAGIC_ZSTD):
        if not HAS_ZSTD:
            raise RuntimeError("zstd not installed")
        return zstd.ZstdDecompressor().decompress(raw[len(MAGIC_ZSTD) :])

    if raw.startswith(MAGIC_ZLIB):
        return zlib.decompress(raw[len(MAGIC_ZLIB) :])

    # No compression detected, return as-is
    return raw


async def safe_json_loads_async(
    raw: bytes, codec: str | None = None, use_executor: bool = True
):
    """
    Async version that offloads CPU-intensive decompression to thread executor.
    Prevents blocking the event loop during large payload processing.

    Args:
        raw: Compressed bytes
        codec: Compression codec (zlib, zstd, or None)
        use_executor: If True, run in thread executor for CPU-bound operations

    Returns:
        Parsed JSON data
    """
    import asyncio

    if use_executor and len(raw) > 10000:  # Only use executor for large payloads
        loop = asyncio.get_event_loop()
        # Offload CPU-intensive decompression to thread
        return await loop.run_in_executor(None, safe_json_loads, raw, codec)
    else:
        # Small payloads - process directly
        return safe_json_loads(raw, codec)


def safe_json_loads(raw: bytes, codec: str | None = None):
    """Safely decompress and parse JSON from compressed bytes"""
    try:
        decompressed = maybe_decompress(raw, codec)
        return orjson.loads(decompressed)
    except Exception as e:
        logger.error(f"Failed to decompress/parse JSON: {e}")
        raise


def compress_bytes(data: bytes, codec: str, level: int = 3) -> bytes:
    """Compress bytes using specified codec with magic header"""
    codec = codec.lower()

    if codec == "zstd":
        if not HAS_ZSTD:
            raise RuntimeError(
                "zstd requested but 'zstandard' package is not installed"
            )
        cctx = zstd.ZstdCompressor(level=level)
        return MAGIC_ZSTD + cctx.compress(data)
    elif codec == "zlib":
        return MAGIC_ZLIB + zlib.compress(data, level=level)
    elif codec == "none":
        return data  # no header
    else:
        raise ValueError(f"Unknown codec: {codec}")


def get_compression_info(raw: bytes) -> dict:
    """Get compression information from raw bytes"""
    codec = sniff_codec_from_magic(raw)
    return {
        "codec": codec,
        "is_compressed": codec is not None,
        "original_size": len(raw),
        "has_magic_header": raw.startswith(MAGIC_ZSTD) or raw.startswith(MAGIC_ZLIB),
    }
