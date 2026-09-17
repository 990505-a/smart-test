"""签名 URL —— 给浏览器直接取用的产物/报告做只读授权。

为什么不能走 `Authorization` 头：`<img src>`、`<iframe>` 里的 trace 查看器、
「在新标签页打开报告」这三种请求都是浏览器自己发起的，带不上前端设置的自定义
头（`X-Auth-Token`）。把签名放进 URL，这些场景就都能工作，而且不必把平台
token 抄进查询串（查询串会进访问日志、Referer、浏览器历史）。

签名格式 `<exp>.<hmac>`：过期时间参与签名，所以攻击者改不了有效期；HMAC 覆盖
调用方给定的全部标识（run_id 等），所以一个 run 的签名换不到另一个 run 的产物。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time

from src.app.core.config import settings

logger = logging.getLogger(__name__)

#: 没配 secret 时的进程内随机密钥：功能可用，但重启后旧链接失效。
_FALLBACK_SECRET = secrets.token_urlsafe(32)
_warned = False


def _secret() -> bytes:
    global _warned
    if settings.share_link_secret:
        return settings.share_link_secret.encode("utf-8")
    if not _warned:
        logger.warning(
            "SHARE_LINK_SECRET 未配置，分享链接用进程内随机密钥签名——"
            "服务重启后此前发出的链接会失效；生产请在 .env 中固定该值。")
        _warned = True
    return _FALLBACK_SECRET.encode("utf-8")


def _digest(expires_at: int, parts: tuple[str, ...]) -> str:
    message = "\n".join((str(expires_at), *parts)).encode("utf-8")
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def sign(*parts: str, ttl_hours: int | None = None) -> str:
    """给一组标识签发带有效期的签名。"""
    hours = settings.web_ui_share_ttl_hours if ttl_hours is None else ttl_hours
    expires_at = int(time.time() + hours * 3600)
    return f"{expires_at}.{_digest(expires_at, parts)}"


def verify(signature: str, *parts: str) -> bool:
    """校验签名是否对给定的标识有效且未过期。"""
    if not signature or "." not in signature:
        return False
    raw_expires, _, digest = signature.partition(".")
    try:
        expires_at = int(raw_expires)
    except ValueError:
        return False
    if expires_at < time.time():
        return False
    return hmac.compare_digest(digest, _digest(expires_at, parts))
