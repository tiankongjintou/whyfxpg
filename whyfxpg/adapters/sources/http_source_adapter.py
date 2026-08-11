"""HTTP 来源适配器：基于 requests 的真实网络采集实现。

支持 ``file://`` 本地文件协议，以及 ``fallback_url`` 配置项：
当主 URL 因网络/DNS 失败且配置中提供了 ``fallback_url`` 时，
自动读取本地样例文件作为兜底，保证流水线在离线/外网不可用
时仍能产出演示数据。
"""

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from whyfxpg.ports.source_port import FetchedPage, SourcePort


class HttpSourceAdapter(SourcePort):
    """使用 requests.Session 抓取远程 URL；支持 file:// 与 fallback。"""

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def _read_file(self, url: str) -> bytes:
        parsed = urlparse(url)
        # 用 url2pathname 把 file:///D:/... 转成当前 OS 的本地路径
        from urllib.request import url2pathname
        local_path = url2pathname(parsed.path)
        path = Path(local_path)
        return path.read_bytes()

    def _try_fetch_url(self, url: str, cfg: dict[str, Any]) -> FetchedPage:
        if url.startswith("file://"):
            started = time.perf_counter()
            content = self._read_file(url)
            latency_ms = int((time.perf_counter() - started) * 1000)
            content_hash = hashlib.sha256(content).hexdigest()
            return FetchedPage(
                source_id="",
                url=url,
                content=content,
                content_type="text/html",
                content_hash=content_hash,
                fetched_at=datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                latency_ms=latency_ms,
                content_length=len(content),
                status="ok",
            )

        headers = cfg.get("headers", {})
        timeout = cfg.get("timeout", 30)
        started = time.perf_counter()
        resp = self.session.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        latency_ms = int((time.perf_counter() - started) * 1000)
        content = resp.content
        content_hash = hashlib.sha256(content).hexdigest()
        return FetchedPage(
            source_id="",
            url=url,
            content=content,
            content_type=resp.headers.get("Content-Type", "unknown"),
            content_hash=content_hash,
            fetched_at=datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            latency_ms=latency_ms,
            content_length=len(content),
            status="ok",
        )

    def fetch(self, source_id: str, cfg: dict[str, Any]) -> FetchedPage:
        url = cfg.get("url", "")
        fallback_url = cfg.get("fallback_url", "")
        request_started_at = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

        try:
            page = self._try_fetch_url(url, cfg)
        except Exception as primary_error:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            # 没有 fallback_url 时直接返回主 URL 错误
            if not fallback_url:
                return FetchedPage(
                    source_id=source_id,
                    url=url,
                    content=b"",
                    content_type="unknown",
                    content_hash="",
                    fetched_at=datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                    request_started_at=request_started_at,
                    latency_ms=None,
                    content_length=None,
                    status="error",
                    error_msg=str(primary_error),
                )
            try:
                page = self._try_fetch_url(fallback_url, cfg)
                page.error_msg = f"primary_failed:{primary_error}; used fallback"
                page.source_id = source_id
                page.request_started_at = request_started_at
                return page
            except Exception as fallback_error:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                return FetchedPage(
                    source_id=source_id,
                    url=url,
                    content=b"",
                    content_type="unknown",
                    content_hash="",
                    fetched_at=datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                    request_started_at=request_started_at,
                    latency_ms=None,
                    content_length=None,
                    status="error",
                    error_msg=f"primary:{primary_error}; fallback:{fallback_error}",
                )

        page.source_id = source_id
        page.request_started_at = request_started_at
        return page
