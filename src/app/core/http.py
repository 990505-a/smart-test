"""访问**本机服务**用的 httpx 客户端。

httpx 默认 ``trust_env=True``，会读系统代理。macOS 上系统代理是经 ``scutil`` 拿到的
（ClashX 之类），所以即使 shell 里没有任何 ``*_proxy`` 环境变量，请求 ``127.0.0.1``
也会被塞进代理。后果不只是多一跳：

* 本机服务**没在跑**时，代理回 ``502`` 而不是连接失败，于是"服务没起"被误判成
  "服务活着但报错"；
* 平台对"有响应"和"连不上"是区别对待的（熔断器只把连不上算失败），误判成 502 后
  熔断永远不触发，每次都要等满超时，用户还看到一句误导的 HTTP 502。

Langfuse 客户端早先单独踩过这个坑（见 ``eval/langfuse_client.py`` 的注释），
这里统一收口：所有指向本机端口的调用都走这个构造函数。
"""

from __future__ import annotations

import httpx


def local_client(**kwargs) -> httpx.AsyncClient:
    """指向 127.0.0.1/localhost 的 AsyncClient（绕过系统代理）。"""
    kwargs.setdefault("trust_env", False)
    return httpx.AsyncClient(**kwargs)
