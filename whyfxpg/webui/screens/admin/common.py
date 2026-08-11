"""Shared admin CRUD renderer for configuration objects."""

import json
from datetime import datetime
from typing import Any

import streamlit as st

from whyfxpg.services.admin.configuration_admin_service import (
    ConfigDraft,
    ConfigRecord,
    ConfigurationAdminService,
    default_configuration_admin_service,
)

_TYPE_LABELS: dict[str, str] = {
    "source": "数据源",
    "rule": "预警规则",
    "model": "风险模型",
    "dimension": "风险维度",
    "taxonomy": "产品分类法",
}

_DEFAULT_PAYLOADS: dict[str, dict[str, Any]] = {
    "source": {
        "name": "新数据源",
        "url": "https://example.com",
        "source_type": "web",
        "enabled": True,
        "priority": 1,
        "check_interval": "1d",
        "fetch_method": "static",
        "parser": "html_list",
        "keywords_ref": "default",
        "delay": 2,
    },
    "rule": {
        "name": "新规则",
        "enabled": True,
        "description": "",
        "severity": "medium",
        "condition": {"type": "threshold", "field": "total_score", "operator": ">=", "value": 80},
        "action": ["dashboard"],
    },
    "model": {
        "version": "1.0",
        "model_name": "new_model",
        "description": "",
        "severity_levels": {},
        "probability_levels": {},
        "risk_matrix": {"columns": [], "rows": {}},
        "country_factors": {},
        "product_factors": {},
        "product_category_keywords": {},
        "history_factor": {"formula": "1", "max": 1.0, "min": 1.0},
        "evidence_factors": {},
        "risk_level_thresholds": {},
        "score_formula": "base",
    },
    "dimension": {
        "name": "新维度",
        "description": "",
        "dimension_type": "categorical",
        "source_field": "",
        "weight": 1.0,
        "aggregation": "count",
    },
    "taxonomy": {
        "node_id": "",
        "name": "新分类节点",
        "parent_id": None,
        "aliases": [],
        "keywords": [],
    },
}


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计


def _service() -> ConfigurationAdminService:
    return default_configuration_admin_service()


def _format_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_payload(text: str) -> dict[str, Any]:
    return json.loads(text)


def _record_summary(record: ConfigRecord) -> str:
    name = record.payload.get("name") or record.payload.get("model_name") or record.object_id
    return f"{name} ({record.status} · {record.version_id})"


def _confirm_delete(object_type: str, object_id: str, service: ConfigurationAdminService) -> None:
    """Called by the delete button to perform deletion and trigger rerun."""
    try:
        service.delete(object_type, object_id)
        st.session_state["_delete_success"] = True
    except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
        st.session_state["_delete_error"] = str(e)


def render_object_type(object_type: str) -> None:
    label = _TYPE_LABELS.get(object_type, object_type)
    st.title(f"⚙️ {label}管理")

    # ── 页面指引 ─────────────────────────────────────────────
    _ADMIN_GUIDES = {
        "source": ("数据源管理", "配置和管理风险数据的外部采集来源，包括各监管机构、召回数据库等。", [
            "「浏览/编辑」表格中，每行有查看详情、编辑、删除三个操作按钮",
            "编辑完成后必须点击「💾 保存」再点「🚀 发布」才能生效",
            "「新增」Tab 可创建新数据源；「版本/回滚」Tab 可查看历史版本并回退",
        ]),
        "rule": ("预警规则管理", "配置风险预警触发的规则条件，满足条件时自动产生预警事件。", [
            "规则由条件（condition）和动作（action）组成；条件支持阈值、表达式等多种类型",
            "编辑完成后必须点击「💾 保存」再点「🚀 发布」才能生效",
            "启用的规则会实时参与事件评分，建议先在测试环境验证再发布",
        ]),
        "model": ("风险模型管理", "配置风险评分模型的结构、参数和阈值，影响最终风险等级的判定。", [
            "风险模型包含严重度等级定义、概率等级、风险矩阵等多层参数",
            "编辑完成后必须点击「💾 保存」再点「🚀 发布」才能生效",
            "建议保留旧版本后再发布新版本，以便出问题随时回滚",
        ]),
        "dimension": ("风险维度管理", "定义风险评估的各个维度及其权重，影响多维度综合评分的计算方式。", [
            "维度分为 categorical（分类）和 numerical（数值）两种类型",
            "每个维度有对应权重，权重越高该维度对最终评分影响越大",
            "编辑完成后必须点击「💾 保存」再点「🚀 发布」才能生效",
        ]),
        "taxonomy": ("产品分类法管理", "维护产品的分类体系结构，用于将采集的事件正确归类到产品类别。", [
            "分类法为树形结构，支持多级父子节点，可设置别名和关键词便于匹配",
            "编辑完成后必须点击「💾 保存」再点「🚀 发布」才能生效",
            "建议先建立完整分类树，再逐步添加关键词提升匹配精度",
        ]),
    }
    title_text, desc, tips = _ADMIN_GUIDES.get(object_type, (f"{label}管理", "", []))
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(title_text, desc, tips)

    service = _service()
    records = service.list(object_type)

    tab_list, tab_create, tab_versions = st.tabs(["浏览/编辑", "新增", "版本/回滚"])

    with tab_list:
        _render_list_tab(object_type, service, records)

    with tab_create:
        _render_create_tab(object_type, service)

    with tab_versions:
        _render_versions_tab(object_type, service, records)


# ─── Field schemas for type-specific form rendering ─────────────────────────

_SOURCE_FIELDS: list[dict[str, Any]] = [
    {"key": "name",        "label": "名称",          "type": "text",  "placeholder": "数据源名称"},
    {"key": "url",         "label": "主 URL",        "type": "text",  "placeholder": "https://..."},
    {"key": "fallback_url","label": "备用 URL",      "type": "text",  "placeholder": "file://... 或空"},
    {"key": "source_type", "label": "来源类型",      "type": "select", "options": ["web", "api", "rss"]},
    {"key": "enabled",     "label": "启用",          "type": "checkbox"},
    {"key": "priority",    "label": "优先级",        "type": "number", "min": 1, "max": 10},
    {"key": "check_interval","label": "检查周期",    "type": "text",  "placeholder": "1d / 6h / 30m"},
    {"key": "fetch_method","label": "抓取方式",      "type": "select", "options": ["static", "dynamic"]},
    {"key": "parser",      "label": "解析器",        "type": "select", "options": ["html_list", "html_table", "json", "xml"]},
    {"key": "keywords_ref","label": "关键词方案",    "type": "text",  "placeholder": "default / international"},
    {"key": "delay",       "label": "抓取延迟(秒)",  "type": "number", "min": 0, "max": 60},
]

# ─── Per-row action modes ────────────────────────────────────────────────────
_MODE_VIEW = "view"
_MODE_EDIT = "edit"


def _payload_from_form(fields: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    payload = {}
    for f in fields:
        key = f["key"]
        widget_key = f"{prefix}_{key}"
        ft = f["type"]
        if ft == "checkbox":
            payload[key] = bool(st.session_state.get(widget_key, False))
        elif ft == "number":
            payload[key] = st.session_state.get(widget_key, f.get("default", 0))
        elif ft == "select":
            payload[key] = st.session_state.get(widget_key, f.get("options", [])[0] if f.get("options") else "")
        else:
            payload[key] = st.session_state.get(widget_key, f.get("default", ""))
    return payload


def _render_list_tab(object_type: str, service: ConfigurationAdminService, records: list[ConfigRecord]) -> None:
    if not records:
        st.info("暂无配置对象")
        return

    # Determine which record is in view/edit mode
    default_key = f"_mode_{object_type}"
    if default_key not in st.session_state:
        st.session_state[default_key] = (_MODE_VIEW, None)   # (mode, object_id)

    current_mode, current_oid = st.session_state[default_key]

    # ── INDEX TABLE: one card per record ─────────────────────────────────────
    for r in records:
        name   = r.payload.get("name") or r.payload.get("model_name") or r.object_id
        status = r.status
        ver    = r.version_id
        ts     = r.created_at.strftime("%Y-%m-%d %H:%M")

        is_active = (current_oid == r.object_id)
        accent    = "🟢" if status == "published" else "🟡"

        col_id, col_name, col_status, col_ver, col_ts, colActs = st.columns(
            [2, 3, 1, 1, 1, 3], gap="small"
        )

        with col_id:
            st.markdown(f"`{r.object_id}`")
        with col_name:
            st.write(f"**{name}**" if is_active else name)
        with col_status:
            st.write(f"{accent} {status}")
        with col_ver:
            st.write(ver)
        with col_ts:
            st.write(ts)

        with colActs:
            bcol1, bcol2, bcol3 = st.columns(3, gap="small")
            with bcol1:
                label = "📋 详情" if current_mode != _MODE_VIEW or current_oid != r.object_id else "🔙 收起"
                if st.button(label, key=f"view_{r.object_id}", width='stretch'):
                    if current_mode == _MODE_VIEW and current_oid == r.object_id:
                        st.session_state[default_key] = (_MODE_VIEW, None)
                    else:
                        st.session_state[default_key] = (_MODE_VIEW, r.object_id)
                    st.rerun()
            with bcol2:
                if st.button("✏️ 编辑", key=f"edit_{r.object_id}", width='stretch'):
                    st.session_state[default_key] = (_MODE_EDIT, r.object_id)
                    st.rerun()
            with bcol3:
                st.button("🗑️ 删除", key=f"del_{r.object_id}", width='stretch',
                         on_click=_do_delete, args=(object_type, r.object_id, service))

        # ── EXPANDED DETAIL / EDIT FORM ────────────────────────────────────
        if is_active:
            record = r
            with st.container():
                st.markdown("---")

                if current_mode == _MODE_VIEW:
                    _render_view_panel(record)
                else:  # _MODE_EDIT
                    _render_edit_form(object_type, record, service)

                st.markdown("---")

    # ── BULK ACTION BAR ──────────────────────────────────────────────────────
    st.divider()
    if st.button("➕ 新增一条配置", type="primary"):
        st.session_state[default_key] = (_MODE_EDIT, None)  # signal create
        st.rerun()


def _do_delete(object_type: str, object_id: str, service: ConfigurationAdminService) -> None:
    try:
        service.delete(object_type, object_id)
        st.session_state[f"_mode_{object_type}"] = (_MODE_VIEW, None)
        st.success(f"已删除: {object_id}")
    except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
        st.error(f"删除失败: {e}")


def _render_view_panel(record: ConfigRecord) -> None:
    """Read-only field display with pretty formatting."""
    payload = record.payload

    # Two-column meta
    m1, m2, m3, m4 = st.columns(4)
    m1.markdown("**对象ID**");   m1.code(record.object_id)
    m2.markdown("**状态**");    m2.code(record.status)
    m3.markdown("**版本**");    m3.code(record.version_id)
    m4.markdown("**创建时间**"); m4.code(record.created_at.strftime("%Y-%m-%d %H:%M"))

    st.markdown("##### 配置详情")

    if record.object_type == "source":
        # Show fields in a clean grid instead of JSON
        left, right = st.columns(2, gap="large")
        for idx, f in enumerate(_SOURCE_FIELDS):
            key = f["key"]
            val = payload.get(key, "")
            col = left if idx % 2 == 0 else right
            with col:
                if f["type"] == "checkbox":
                    st.checkbox(f["label"], value=bool(val), disabled=True,
                                key=f"_view_{record.object_id}_{key}")
                elif f["type"] == "select":
                    st.selectbox(f["label"], options=f.get("options", []),
                                 index=f.get("options", []).index(val) if val in f.get("options", []) else 0,
                                 disabled=True, key=f"_view_{record.object_id}_{key}")
                else:
                    st.text_input(f["label"], value=str(val) if val else "",
                                  disabled=True, key=f"_view_{record.object_id}_{key}")

        # Expandable advanced sections
        with st.expander("🔧 headers（请求头）"):
            st.json(payload.get("headers") or {})
        with st.expander("🔍 selector（CSS选择器）"):
            st.json(payload.get("selector") or {})
    else:
        st.json(payload)


def _render_edit_form(object_type: str, record: ConfigRecord, service: ConfigurationAdminService) -> None:
    """Field-based edit form (source type) or JSON editor (other types)."""
    payload = record.payload
    prefix  = f"_edit_{object_type}_{record.object_id}"

    if object_type == "source":
        left, right = st.columns(2, gap="large")
        submitted = False  # noqa: F841 — 刻意用法(见 TD03)

        for idx, f in enumerate(_SOURCE_FIELDS):
            key  = f["key"]
            wkey = f"{prefix}_{key}"
            col  = left if idx % 2 == 0 else right

            with col:
                if f["type"] == "checkbox":
                    st.checkbox(f["label"], value=bool(payload.get(key, False)), key=wkey)
                elif f["type"] == "select":
                    opts = f.get("options", [])
                    cur  = payload.get(key, opts[0] if opts else "")
                    st.selectbox(f["label"], options=opts, index=opts.index(cur) if cur in opts else 0, key=wkey)
                elif f["type"] == "number":
                    default_val = float(payload.get(key, f.get("default", 0)))
                    st.number_input(f["label"],
                                   value=default_val,
                                   min_value=float(f.get("min", 0)),
                                   max_value=float(f.get("max", 9999)),
                                   key=wkey)
                else:
                    st.text_input(f["label"],
                                  value=str(payload.get(key, "")),
                                  placeholder=f.get("placeholder", ""),
                                  key=wkey)

        # Advanced sections as expandable JSON (edit as raw)
        for sect in ["headers", "selector"]:
            with st.expander(f"🔧 {sect}（JSON）"):
                st.text_area(f"{sect} (JSON)",
                              value=json.dumps(payload.get(sect) or {}, ensure_ascii=False, indent=2),
                              height=150, key=f"{prefix}_{sect}", label_visibility="collapsed")

        action_cols = st.columns([1, 1, 2])
        with action_cols[0]:
            if st.button("💾 保存", type="primary", width='stretch',
                         key=f"{prefix}_save"):
                try:
                    updated = _payload_from_form(_SOURCE_FIELDS, prefix)
                    # Merge back advanced sections
                    for sect in ["headers", "selector"]:
                        raw = st.session_state.get(f"{prefix}_{sect}", "{}")
                        try:
                            updated[sect] = json.loads(raw)
                        except Exception:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                            updated[sect] = {}
                    service.update(object_type, record.object_id, updated)
                    st.success("已保存")
                    st.rerun()
                except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                    st.error(f"保存失败: {e}")
        with action_cols[1]:
            if st.button("🚀 发布", width='stretch', key=f"{prefix}_publish"):
                try:
                    service.publish(object_type, record.object_id)
                    st.success("已发布")
                    st.rerun()
                except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                    st.error(f"发布失败: {e}")
        with action_cols[2]:
            if st.button("✏️ 改回 JSON 编辑", width='stretch',
                         key=f"{prefix}_json_mode"):
                st.session_state[f"_json_fallback_{object_type}_{record.object_id}"] = True
                st.rerun()
    else:
        # Non-source types: fall back to JSON editor
        st.text_area("配置内容 (JSON)",
                      value=json.dumps(payload, ensure_ascii=False, indent=2),
                      height=300, key=f"{prefix}_json")
        action_cols = st.columns(2)
        with action_cols[0]:
            if st.button("💾 保存", type="primary", width='stretch',
                         key=f"{prefix}_save"):
                try:
                    updated = json.loads(st.session_state[f"{prefix}_json"])
                    service.update(object_type, record.object_id, updated)
                    st.success("已保存")
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"JSON 格式错误: {e}")
                except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                    st.error(f"保存失败: {e}")
        with action_cols[1]:
            if st.button("🚀 发布", width='stretch', key=f"{prefix}_publish"):
                try:
                    service.publish(object_type, record.object_id)
                    st.success("已发布")
                    st.rerun()
                except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                    st.error(f"发布失败: {e}")


def _render_create_tab(object_type: str, service: ConfigurationAdminService) -> None:
    object_id = st.text_input("对象 ID", key=f"create_id_{object_type}")
    payload_text = st.text_area(
        "初始配置 (JSON)",
        value=_format_payload(_DEFAULT_PAYLOADS.get(object_type, {})),
        height=320,
        key=f"create_payload_{object_type}",
    )
    if st.button("➕ 创建", key=f"create_{object_type}"):
        if not object_id:
            st.error("对象 ID 不能为空")
            return
        try:
            payload = _parse_payload(payload_text)
            draft = ConfigDraft(
                object_type=object_type,
                object_id=object_id,
                payload=payload,
            )
            service.create(draft)
            st.success("已创建")
            st.rerun()
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            st.error(f"创建失败: {e}")


def _render_versions_tab(
    object_type: str,
    service: ConfigurationAdminService,
    records: list[ConfigRecord],
) -> None:
    if not records:
        st.info("暂无配置对象")
        return

    options = {r.object_id: r for r in records}
    selected_id = st.selectbox(
        "选择对象",
        options=list(options.keys()),
        format_func=lambda oid: _record_summary(options[oid]),
        key=f"version_select_{object_type}",
    )

    versions = service.versions(object_type, selected_id)
    if not versions:
        st.info("暂无历史版本")
        return

    version_options = {v.version_id: v for v in versions}
    selected_version_id = st.selectbox(
        "历史版本",
        options=list(version_options.keys()),
        format_func=lambda vid: f"{vid} ({version_options[vid].status} · {version_options[vid].created_at.strftime('%Y-%m-%d %H:%M:%S')})",
    )
    version = version_options[selected_version_id]

    st.json(version.payload)
    if st.button("↩️ 回滚到该版本", key=f"rollback_{selected_version_id}"):
        try:
            service.rollback(object_type, selected_id, selected_version_id)
            st.success("已回滚为草稿，请发布生效")
            st.rerun()
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            st.error(f"回滚失败: {e}")
