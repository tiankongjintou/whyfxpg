"""风险维度管理页面。"""

from whyfxpg.webui.screens.admin.common import render_object_type


def render() -> None:
    render_object_type("dimension")
