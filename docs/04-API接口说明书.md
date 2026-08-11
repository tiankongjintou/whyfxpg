# API接口说明书

> 基于 2026-08-05 代码审计；Phase 1（P02 起）新增 FastAPI REST API

## 一、系统架构说明

- **Phase 0（现状）**：无 REST API，所有功能通过 Streamlit Web UI 页面操作。
- **Phase 1（P02 起）**：引入 **FastAPI REST API**（`whyfxpg_api/` 包），
  与 Web UI 并存。API 面向企业客户（多租户 API Key 认证），
  Web UI 面向内部运营。
- REST API 端点、认证规范与错误格式见文末附录
  「Phase 1 REST API（FastAPI）」。

---

## 二、Web UI 页面级接口

### 2.1 页面导航结构

系统通过 Streamlit 的侧边栏 radio 组件实现页面导航，URL 路径由 Streamlit 内部管理。

| 页面名称 | 侧边栏标签 | 路由机制 | 核心操作 |
|----------|-----------|---------|---------|
| 风险总览 | 📊 风险总览 | Streamlit 内部路由 | 仪表盘筛选、下钻详情 |
| 风险态势大屏 | 🖥️ 风险态势大屏 | Streamlit 内部路由 | 全屏大屏、导出 Excel |
| 风险事件列表 | 📋 风险事件 | Streamlit 内部路由 | 多维筛选、事件详情 |
| 人工复核 | ✅ 人工复核 | Streamlit 内部路由 | 评分修正、提交复核 |
| 预警中心 | 🔔 预警中心 | Streamlit 内部路由 | 确认/忽略/转发预警 |
| 通知中心 | 🔔 通知中心 | Streamlit 内部路由 | 查看/标记已读通知 |
| 报告中心 | 📄 报告中心 | Streamlit 内部路由 | 报告生成与下载 |
| 因果知识图谱 | 🔗 因果知识图谱 | Streamlit 内部路由 | 图谱可视化、节点查询 |
| 数据源监控 | 🌐 数据源监控 | Streamlit 内部路由 | 采集状态、健康评分 |
| 数据源管理 | ⚙️ 数据源管理 | Streamlit 内部路由 | 数据源 CRUD |
| 预警规则管理 | ⚙️ 预警规则管理 | Streamlit 内部路由 | 规则 CRUD |
| 风险模型管理 | ⚙️ 风险模型管理 | Streamlit 内部路由 | 模型参数编辑 |
| 风险维度管理 | ⚙️ 风险维度管理 | Streamlit 内部路由 | 维度权重配置 |
| 分类法管理 | ⚙️ 分类法管理 | Streamlit 内部路由 | HS 分类维护 |

### 2.2 管理面核心操作

#### 数据源管理页面（/admin/source）

| 操作 | 说明 |
|------|------|
| 查看数据源列表 | 显示所有配置的数据源及其状态 |
| 新增数据源 | 添加新的监控数据源（URL、轮询间隔、类型） |
| 编辑数据源 | 修改现有数据源配置 |
| 禁用/启用数据源 | 控制采集开关 |
| 手动触发采集 | 立即执行一次数据采集 |
| 查看采集历史 | 查看 crawl_logs 中的历史采集记录 |

#### 预警规则管理页面（/admin/rule）

| 操作 | 说明 |
|------|------|
| 查看规则列表 | 显示所有预警规则及其状态 |
| 新增规则 | 通过表单添加新规则 |
| 编辑规则 | 修改规则条件、优先级、动作 |
| 启用/禁用规则 | 控制规则是否生效 |
| 规则沙箱测试 | 使用 sandbox 接口验证规则逻辑 |
| 规则版本回滚 | 从 config_versions 恢复历史版本 |

#### 风险模型管理页面（/admin/model）

| 操作 | 说明 |
|------|------|
| 查看当前模型配置 | 显示 risk_model.yaml 中的所有参数 |
| 编辑模型参数 | 修改严重度量表、概率量表、系数 |
| 发布新版本 | 将修改后的配置保存为新版本 |
| 版本回滚 | 恢复到之前的配置版本 |
| 查看配置差异 | 对比两个版本的参数变化 |

#### 风险维度管理页面（/admin/dimension）

| 操作 | 说明 |
|------|------|
| 查看维度列表 | 显示所有评分维度及其权重 |
| 调整维度权重 | 修改各维度的相对重要性 |
| 查看维度统计 | 各维度的得分分布 |

#### 分类法管理页面（/admin/taxonomy）

| 操作 | 说明 |
|------|------|
| 查看分类法列表 | 显示 HS 分类体系 |
| 新增分类 | 添加新的产品分类 |
| 编辑分类映射 | 设置关键词到分类的映射规则 |

### 2.3 业务操作面核心操作

#### 风险总览页面

| 操作 | 说明 |
|------|------|
| 按时间筛选 | 选择日期范围 |
| 按品类筛选 | 选择产品类别 |
| 按国别筛选 | 选择来源国 |
| 下钻查看详情 | 点击汇总指标进入明细 |
| 刷新数据 | 重新查询数据库 |

#### 风险事件列表页面

| 操作 | 说明 |
|------|------|
| 多维条件筛选 | source_id / country / manufacturer / rs_level / review_status |
| 查看事件详情 | 展开事件完整信息 |
| 提交人工复核 | 将事件标记为待复核 |
| 导出事件列表 | 下载为 CSV/Excel |

#### 人工复核页面

| 操作 | 说明 |
|------|------|
| 查看待复核事件 | 列表展示待处理事件 |
| 调整评分 | 修改 ss_score / ps_score |
| 调整风险等级 | 修改 rs_level |
| 填写修正原因 | 记录修正依据 |
| 批量复核 | 批量确认事件 |

#### 预警中心页面

| 操作 | 说明 |
|------|------|
| 查看待处理预警 | 列表展示 pending 预警 |
| 确认预警 | 标记为 confirmed |
| 忽略预警 | 标记为 dismissed |
| 转发预警 | 转发给其他用户 |
| 升级预警 | 将低级别预警升级 |

---

## 三、数据库直接访问说明

由于无 REST API，外部系统如需访问数据，需通过以下方式：

1. **SQLite 直连**：直接连接 `whyfxpg/data/whyfxpg.db` 进行查询
2. **Python 模块调用**：通过导入 `whyfxpg` 包调用内部服务

---

## 四、待实现的 REST API 设计建议

如未来需要对外提供 API，建议以下接口设计：

### 4.1 风险事件接口

```
GET  /api/v1/events              # 查询风险事件列表（分页、筛选）
GET  /api/v1/events/{event_id}   # 获取事件详情
POST /api/v1/events/{event_id}/review  # 提交人工复核
```

### 4.2 预警接口

```
GET  /api/v1/alerts              # 查询预警列表
GET  /api/v1/alerts/{alert_id}  # 获取预警详情
PUT  /api/v1/alerts/{alert_id}  # 更新预警状态（confirm/dismiss）
```

### 4.3 数据源接口

```
GET  /api/v1/sources             # 获取数据源列表
POST /api/v1/sources             # 新增数据源
PUT  /api/v1/sources/{source_id} # 更新数据源
POST /api/v1/sources/{source_id}/trigger  # 手动触发采集
```

### 4.4 规则接口

```
GET  /api/v1/rules               # 获取规则列表
POST /api/v1/rules               # 新增规则
PUT  /api/v1/rules/{rule_id}     # 更新规则
DELETE /api/v1/rules/{rule_id}   # 删除规则
POST /api/v1/rules/{rule_id}/test  # 沙箱测试规则
```

### 4.5 评分接口

```
POST /api/v1/score               # 对单个事件进行评分
POST /api/v1/score/batch         # 批量评分
```

### 4.6 图谱接口

```
GET  /api/v1/causal/nodes        # 查询因果节点
GET  /api/v1/causal/nodes/{node_id}  # 获取节点详情
GET  /api/v1/causal/edges        # 查询因果边
POST /api/v1/causal/nodes        # 新增节点
POST /api/v1/causal/edges        # 新增边
GET  /api/v1/causal/chains/{event_id}  # 查询事件的因果链
```

> ⚠️ 以上接口设计为待实现状态，当前版本不支持 REST API 访问。

---

## 附录：Phase 1 REST API（FastAPI，P02）

> 包：`whyfxpg_api/`（`uvicorn whyfxpg_api.main:app --reload` 启动）
> OpenAPI 3.0：启动后访问 `/docs`（Swagger UI）自动生成。

### 1. 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/health` | 公开 | 健康检查，返回 `{"status": "ok", "service": "whyfxpg-api", "version": "..."}` |
| GET | `/api/v1/me` | 需 API Key | 当前账户信息（account_id/company_name/plan_type/monthly_quota/status） |
| GET | `/api/v1/events` | 需 API Key | 分页查询风险事件（page/per_page + manufacturer/country/hazard_type 筛选，P03） |
| GET | `/api/v1/events/{event_id}` | 需 API Key | 事件详情（P03） |
| POST | `/api/v1/events/assess` | 需 API Key | 实时评分，返回总分/等级/breakdown（P03） |
| POST | `/api/v1/events/batch-assess` | 需 API Key | 批量评分 ≤100 条（P03） |
| GET | `/api/v1/companies/{name}/profile` | 需 API Key | 企业风险画像（事件数/均分/等级分布/最近事件，P03） |
| GET | `/api/v1/alerts` | 需 API Key | 预警列表（分页 + status 筛选，P03） |
| GET | `/api/v1/alerts/{alert_id}` | 需 API Key | 预警详情（P03） |
| GET | `/docs`、`/redoc`、`/openapi.json` | 公开 | OpenAPI 文档 |

### 1.1 统一成功响应格式（P03）

```json
{"success": true, "data": {...}, "meta": {"request_id": "...", "quota_used": 0, "quota_remaining": null}, "error": null}
```

- 分页响应：`data` 含 `items` / `total` / `page` / `per_page`。
- 所有查询端点按当前账户 `account_id` 过滤（**租户隔离**）。

### 2. 认证规范（多租户 API Key）

- 请求头 `X-API-Key: <api_key>`（明文 Key）。
- 服务端对 Key 做 **sha256 哈希**后与 `accounts.api_key_hash` 比对
  （P01 的 accounts 表，经 `AccountPort` → `PgAccountAdapter` 查询）。
- 除公开端点（`/health`、`/docs`、`/openapi.json`）外，**所有端点默认要求
  API Key**（`AuthMiddleware`）；认证通过后注入 `request.state.account`。
- 账户状态非 `active` 或 Key 无效 → 403。

### 3. 统一错误格式

```json
{"success": false, "error": "错误描述", "request_id": "请求ID"}
```

- `request_id` 由中间件生成（缺失时），响应头 `X-Request-ID` 与之对应，
  便于日志追踪。
- 参数校验错误（422）同样使用该格式。

### 4. 目录结构（P02）

```
whyfxpg_api/
├── main.py          # create_app() 应用工厂 + OpenAPI 配置
├── dependencies.py  # get_current_account / get_account_service
├── middleware.py    # RequestIDMiddleware + AuthMiddleware
├── routes/          # health.py（公开）、me.py（受保护）
├── models/          # 内部模型
└── schemas/         # AccountOut / ErrorResponse
```

配套服务：`whyfxpg/services/account_service.py`（Key 哈希 + 校验）、
`whyfxpg/ports/account_port.py`（Port）、
`whyfxpg/adapters/accounts/`（Pg / InMemory 双适配器）。
