"""
WHYFXPG Web UI 共享数据查询层

把 app.py / bigscreen.py 等页面会用到的数据库查询集中到这里，
避免多页面重复实现，并统一缓存策略。

核心查询逻辑已迁移到 whyfxpg.webui.read_model.DashboardReadModel，
本文件只提供 Streamlit 缓存装饰的薄包装。
"""

import streamlit as st

from whyfxpg.webui.read_model import DashboardReadModel, SourceHealthReadModel

_read_model = DashboardReadModel()
_health_model = SourceHealthReadModel()


@st.cache_data(ttl=300)
def get_events(limit: int = 200):
    """获取风险事件列表"""
    return _read_model.get_events(limit=limit)


@st.cache_data(ttl=300)
def get_alerts():
    """获取预警记录"""
    return _read_model.get_alerts(limit=200)


@st.cache_data(ttl=300)
def get_summary():
    """仪表盘汇总指标"""
    return _read_model.get_summary()


@st.cache_data(ttl=300)
def get_country_summary(limit: int = 20):
    """国别风险汇总"""
    return _read_model.get_country_summary(limit=limit)


@st.cache_data(ttl=300)
def get_trend(days: int = 30):
    """近 N 天风险事件趋势"""
    return _read_model.get_trend(days=days)


@st.cache_data(ttl=300)
def get_hazard_distribution(limit: int = 10):
    """危害类型分布"""
    return _read_model.get_hazard_distribution(limit=limit)


@st.cache_data(ttl=300)
def get_recent_high_risk(limit: int = 15):
    """最新高风险事件"""
    return _read_model.get_recent_high_risk(limit=limit)


@st.cache_data(ttl=300)
def get_source_status():
    """数据源监控状态"""
    return _read_model.get_source_status()


@st.cache_data(ttl=300)
def get_source_health():
    """数据源健康度评分"""
    return _health_model.get_source_health()


@st.cache_data(ttl=300)
def get_source_metrics(source_id: str, window: str = "24h"):
    """单个数据源历史指标"""
    return _health_model.get_source_metrics(source_id, window)


@st.cache_data(ttl=300)
def get_lineage(event_id: str):
    """风险事件血缘追踪"""
    return _health_model.get_lineage(event_id)


@st.cache_data(ttl=300)
def get_health_trend(source_id: str, limit: int = 30):
    """数据源健康趋势"""
    return _health_model.get_health_trend(source_id, limit)
