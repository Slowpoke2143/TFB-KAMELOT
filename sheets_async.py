import time
import asyncio
from typing import Dict, Tuple, List
from config import SHEETS_CACHE_TTL_SECONDS
from sheets import get_sheet_names as _sync_get_sheet_names, get_dishes_by_sheet as _sync_get_dishes_by_sheet

# Простой кэш в памяти
_cache: Dict[Tuple[str, str], Tuple[float, object]] = {}
_lock = asyncio.Lock()

def _is_fresh(ts: float) -> bool:
    return (time.time() - ts) < SHEETS_CACHE_TTL_SECONDS

async def get_sheet_names() -> List[str]:
    """Асинхронно с кэшированием."""
    key = ("sheets", "names")
    async with _lock:
        if key in _cache and _is_fresh(_cache[key][0]):
            return _cache[key][1]
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _sync_get_sheet_names)
    async with _lock:
        _cache[key] = (time.time(), data)
    return data

async def get_dishes_by_sheet(sheet_name: str) -> List[dict]:
    """Асинхронно с кэшированием по имени листа."""
    key = ("sheet", sheet_name)
    async with _lock:
        if key in _cache and _is_fresh(_cache[key][0]):
            return _cache[key][1]
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _sync_get_dishes_by_sheet, sheet_name)
    async with _lock:
        _cache[key] = (time.time(), data)
    return data

async def bust_cache():
    async with _lock:
        _cache.clear()
