"""
数据源采集模块 (M2)

功能：
- 读取 monitor_sources 配置和数据库状态
- 对启用信息源进行采集
- 变更检测：对比内容哈希，只保存新内容
- 写入 raw_pages 和 crawl_logs

输入：monitor_sources（由配置初始化脚本填充）
输出：raw_pages, crawl_logs

说明：
- 本模块是采集 orchestrator：负责读取配置、调度 SourcePort、使用 Store 写入结果。
- 具体 HTTP 请求由 whyfxpg.adapters.sources.HttpSourceAdapter 处理；
  测试可注入 whyfxpg.adapters.sources.InMemorySourceAdapter，无需 mock requests。
- 只要遵守 raw_pages 表契约即可。
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from whyfxpg.adapters.sources.http_source_adapter import HttpSourceAdapter
from whyfxpg.config.models import SourcesConfig
from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR, ConfigLoader
from whyfxpg.core.stores import (
    MonitorSourceStore,
    RawPageStore,
    UnitOfWork,
)
from whyfxpg.ports.source_port import FetchedPage, SourcePort


class Fetcher:
    """数据源采集器（orchestrator）。"""

    def __init__(
        self,
        config_dir: str | None = None,
        db_path: str | None = None,
        source_port: SourcePort | None = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.db_path = db_path
        self.loader = ConfigLoader(str(self.config_dir))
        self.sources_cfg: SourcesConfig = self.loader.typed_sources
        self.source_port = source_port or HttpSourceAdapter()

    def init_monitor_sources(self) -> None:
        """
        根据 sources.yaml 初始化 monitor_sources 表。
        仅插入不存在的 source_id。
        """
        sources = {sid: cfg.to_dict() for sid, cfg in self.sources_cfg.sources.items()}
        with UnitOfWork(self.db_path) as uow:
            MonitorSourceStore(uow).ensure_sources(sources)

    def fetch_source(self, source_id: str, cfg_dict: dict[str, Any]) -> dict[str, Any]:
        """
        采集单个来源并写入数据库。
        返回结果字典，包含成功/失败状态、内容、哈希等。
        """
        request_started_at = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        page = self.source_port.fetch(source_id, cfg_dict)
        page.request_started_at = page.request_started_at or request_started_at
        with UnitOfWork(self.db_path) as uow:
            return self._process_page(uow, page)

    def _process_page(self, uow: UnitOfWork, page: FetchedPage) -> dict[str, Any]:
        source_id = page.source_id
        result: dict[str, Any] = {
            "source_id": source_id,
            "url": page.url,
            "success": page.success,
            "page_id": None,
            "new": False,
            "content_hash": page.content_hash,
            "error": page.error_msg if not page.success else None,
            "latency_ms": page.latency_ms,
            "content_length": page.content_length,
        }


        monitor_store = MonitorSourceStore(uow)
        raw_page_store = RawPageStore(uow)

        if not page.success:
            monitor_store.record_check(
                source_id, "", "error", page.error_msg, page.content_length
            )
            monitor_store.record_crawl_log(
                source_id, "error", 0, 0, page.error_msg,
                latency_ms=page.latency_ms,
                content_length=page.content_length,
                request_started_at=page.request_started_at,
            )
            return result

        existing_page_id = raw_page_store.find_existing_by_hash(
            source_id, page.content_hash
        )
        if existing_page_id:
            result["page_id"] = existing_page_id
            monitor_store.record_check(
                source_id, page.content_hash, "ok", None, page.content_length
            )
            monitor_store.record_crawl_log(
                source_id, "ok", 1, 0, None,
                latency_ms=page.latency_ms,
                content_length=page.content_length,
                request_started_at=page.request_started_at,
            )
        else:
            page_id = f"{source_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            raw_page_store.insert_page(
                page_id=page_id,
                source_id=source_id,
                url=page.url,
                content_type=page.content_type,
                content_hash=page.content_hash,
                content=page.content,
                status="fetched",
            )
            result["page_id"] = page_id
            result["new"] = True
            monitor_store.record_check(
                source_id, page.content_hash, "ok", None, page.content_length
            )
            monitor_store.record_crawl_log(
                source_id, "ok", 1, 1, None,
                latency_ms=page.latency_ms,
                content_length=page.content_length,
                request_started_at=page.request_started_at,
            )

        return result

    def run(self) -> dict[str, Any]:
        """模块主入口"""
        self.init_monitor_sources()

        results: list[dict[str, Any]] = []
        total_new = 0
        errors: list[str] = []

        with UnitOfWork(self.db_path) as uow:
            for source in self.sources_cfg.enabled_sources():
                source_id = source.source_id
                cfg_dict = source.to_dict()
                # 简单限速
                time.sleep(source.delay)

                request_started_at = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                page = self.source_port.fetch(source_id, cfg_dict)
                page.request_started_at = page.request_started_at or request_started_at
                res = self._process_page(uow, page)
                results.append(res)

                if res["success"]:
                    if res["new"]:
                        total_new += 1
                else:
                    errors.append(f"{source_id}: {res.get('error', '')}")

        return {
            "module": "fetcher",
            "status": "success" if not errors else "partial",
            "records_processed": len(results),
            "records_created": total_new,
            "errors": errors,
            "message": f"采集 {len(results)} 个来源，新增 {total_new} 条原始内容",
        }


if __name__ == "__main__":
    from .db import init_db

    init_db()
    fetcher = Fetcher()
    print(fetcher.run())
