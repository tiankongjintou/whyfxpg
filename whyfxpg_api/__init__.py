"""WHYFXPG Phase 1 API 服务包。

目录结构（P02）：
- main.py          — FastAPI 应用工厂 + OpenAPI 配置
- dependencies.py  — 依赖注入（API Key 校验、当前账户）
- middleware.py    — RequestID + API Key 认证中间件
- routes/          — 路由模块（health 公开、me 受保护）
- models/          — 内部/响应模型
- schemas/         — 请求/响应 Schema（统一错误格式等）
"""

__version__ = "0.1.0"
