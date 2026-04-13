import asyncio
import logging
from functools import lru_cache

from supabase import Client, create_client

from llm_lawyer.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_storage_client() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_key)


def _upload_sync(path: str, data: bytes, content_type: str) -> str:
    s = get_settings()
    client = get_storage_client()
    client.storage.from_(s.supabase_storage_bucket).upload(
        path=path,
        file=data,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return path


async def upload_bytes(path: str, data: bytes, content_type: str) -> str:
    """Upload to Supabase Storage. Returns the stored path."""
    return await asyncio.to_thread(_upload_sync, path, data, content_type)


def signed_url(path: str, expires_in: int = 3600) -> str:
    """Fast call — no network blocking on initial check; run synchronously."""
    s = get_settings()
    client = get_storage_client()
    try:
        resp = client.storage.from_(s.supabase_storage_bucket).create_signed_url(
            path, expires_in
        )
        return resp.get("signedURL") or resp.get("signed_url") or ""
    except Exception as e:
        logger.warning("signed_url failed for %s: %s", path, e)
        return ""


async def delete_object(path: str) -> None:
    """Best-effort delete — used to roll back a storage upload when the
    corresponding DB commit fails."""
    s = get_settings()
    client = get_storage_client()
    try:
        await asyncio.to_thread(
            client.storage.from_(s.supabase_storage_bucket).remove, [path]
        )
    except Exception as e:
        logger.warning("delete_object %s failed: %s", path, e)


def _ensure_bucket_sync() -> None:
    s = get_settings()
    client = get_storage_client()
    try:
        buckets = client.storage.list_buckets()
        names = {b.name if hasattr(b, "name") else b.get("name") for b in buckets}
        if s.supabase_storage_bucket not in names:
            client.storage.create_bucket(
                s.supabase_storage_bucket, options={"public": False}
            )
    except Exception as e:
        logger.warning("ensure_bucket skipped: %s", e)


async def ensure_bucket() -> None:
    await asyncio.to_thread(_ensure_bucket_sync)
