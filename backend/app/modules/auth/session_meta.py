"""Клиентские метаданные сессии: IP, User-Agent → device_label, geo."""
from __future__ import annotations

import ipaddress
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import httpx
from fastapi import Request

logger = logging.getLogger(__name__)

# ip → (expires_monotonic, label|None)
_GEO_CACHE: Dict[str, Tuple[float, Optional[str]]] = {}
_GEO_CACHE_TTL_SEC = 6 * 60 * 60
_GEO_LOOKUP_TIMEOUT_SEC = 1.5


@dataclass(frozen=True)
class SessionClientMeta:
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    device_label: Optional[str] = None
    geo_label: Optional[str] = None


async def client_meta_from_request(request: Request) -> SessionClientMeta:
    ip = _client_ip(request)
    ua = (request.headers.get("user-agent") or "").strip() or None
    device = device_label_from_ua(ua) if ua else None
    geo = _geo_from_headers(request)
    if not geo:
        geo = await geo_label_from_ip(ip)
    return SessionClientMeta(ip=ip, user_agent=ua, device_label=device, geo_label=geo)


def _client_ip(request: Request) -> Optional[str]:
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        # Берём первый адрес в цепочке прокси.
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:45]
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip[:45]
    if request.client and request.client.host:
        return str(request.client.host)[:45]
    return None


def _geo_from_headers(request: Request) -> Optional[str]:
    """Страна/город из CDN-заголовков, если прокси их уже проставил."""
    country = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-vercel-ip-country")
        or request.headers.get("cloudfront-viewer-country")
        or ""
    ).strip().upper()
    if not country or country in {"XX", "T1", "N/A"}:
        return None
    city = (
        request.headers.get("cf-ipcity")
        or request.headers.get("x-vercel-ip-city")
        or ""
    ).strip()
    if city:
        return f"{city}, {country}"[:255]
    return country[:255]


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


async def geo_label_from_ip(ip: Optional[str]) -> Optional[str]:
    """Город/страна по IP через публичный geo API. Падает мягко, без блокировки логина."""
    if not ip or not _is_public_ip(ip):
        return None

    now = time.monotonic()
    cached = _GEO_CACHE.get(ip)
    if cached is not None and cached[0] > now:
        return cached[1]

    label: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=_GEO_LOOKUP_TIMEOUT_SEC) as client:
            # Бесплатный HTTP endpoint; только поля, которые нам нужны.
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,city,message"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if str(data.get("status") or "").lower() == "success":
                    city = str(data.get("city") or "").strip()
                    country = str(data.get("country") or "").strip()
                    if city and country:
                        label = f"{city}, {country}"[:255]
                    elif country:
                        label = country[:255]
                    elif city:
                        label = city[:255]
    except Exception:
        logger.debug("geo lookup failed ip=%s", ip, exc_info=True)

    _GEO_CACHE[ip] = (now + _GEO_CACHE_TTL_SEC, label)
    if len(_GEO_CACHE) > 2048:
        # Простая уборка протухших записей.
        expired = [k for k, (exp, _) in _GEO_CACHE.items() if exp <= now]
        for k in expired:
            _GEO_CACHE.pop(k, None)
    return label


def device_label_from_ua(ua: str) -> str:
    """Короткий ярлык вроде «Chrome · Windows» без тяжёлых парсеров."""
    lower = ua.lower()
    browser = _browser(lower, ua)
    os_name = _os(lower)
    if browser and os_name:
        return f"{browser} · {os_name}"[:128]
    return (browser or os_name or "Неизвестное устройство")[:128]


def _browser(lower: str, raw: str) -> Optional[str]:
    if "edg/" in lower or "edgios" in lower:
        return "Edge"
    if "opr/" in lower or "opera" in lower:
        return "Opera"
    if "firefox/" in lower or "fxios" in lower:
        return "Firefox"
    if "chrome/" in lower or "crios" in lower:
        return "Chrome"
    if "safari/" in lower and "chrome" not in lower and "chromium" not in lower:
        return "Safari"
    if "yabrowser" in lower:
        return "Яндекс"
    if "samsungbrowser" in lower:
        return "Samsung"
    return None


def _os(lower: str) -> Optional[str]:
    if "iphone" in lower:
        return "iPhone"
    if "ipad" in lower:
        return "iPad"
    if "android" in lower:
        return "Android"
    if "windows" in lower:
        return "Windows"
    if "mac os" in lower or "macintosh" in lower:
        return "macOS"
    if "cros" in lower:
        return "ChromeOS"
    if "linux" in lower:
        return "Linux"
    return None


def mask_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    if ":" in ip:
        parts = [p for p in ip.split(":") if p != ""]
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}:xxxx:xxxx"
        return "xxxx::"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.xxx.xxx"
    return ip
