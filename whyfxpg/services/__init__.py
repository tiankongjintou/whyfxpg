"""
Domain services: business logic that orchestrates ports and adapters.

注意：本包不主动导入任何 service 模块。历史版本在此 eager 导入全部服务，
导致 ``adapters.reports -> ports.report_renderer -> services.report_model``
链路被 ``services/__init__`` 截胡触发循环导入（P1b-03 修复）。需要服务时
请直接 ``from whyfxpg.services.xxx_service import XxxService``。
"""
