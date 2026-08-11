"""Pydantic 配置加载器（P07）。

统一入口：YAML → 环境变量覆盖 → Pydantic 校验 → 配置模型。

- **AC-2 拒绝启动**：结构性错误（必填关键字段缺失、整体无法解析）抛出
  ``ConfigValidationError``，错误信息包含具体字段路径与期望类型。
- **AC-3 环境变量覆盖**：``RISK_MODEL__<FIELD>`` 覆盖顶层字段，
  嵌套路径用 ``__`` 分隔（如 ``RISK_MODEL__HISTORY_FACTOR__MAX=1.8``）。
  值优先按 JSON 解析（数字/布尔/列表/字典），失败时按字符串处理。
- **AC-4 降级策略**：单字段校验失败时回退到该字段的默认值，
  不影响整体启动（仅警告，不抛错）。
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from whyfxpg.config.pydantic_models import RiskModelConfig


class ConfigValidationError(ValueError):
    """配置校验失败（拒绝启动）。"""


def load_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件为 dict。"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_env_value(value: str) -> Any:
    """把环境变量值解析为 JSON 类型，失败时按字符串处理。"""
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _match_key(mapping: dict[str, Any], key: str) -> str:
    """在 dict 中查找 key：精确匹配优先，否则 case-insensitive；不存在时返回小写（与模型字段惯例一致）。"""
    if key in mapping:
        return key
    lowered = key.lower()
    for existing in mapping:
        if existing.lower() == lowered:
            return existing
    return lowered


def apply_env_overrides(raw: dict[str, Any], prefix: str = "RISK_MODEL") -> dict[str, Any]:
    """把 ``<PREFIX>__<PATH>`` 环境变量合并进配置 dict（嵌套路径用 __ 分隔）。"""
    result: dict[str, Any] = copy.deepcopy(raw)
    for key, value in os.environ.items():
        if not key.startswith(prefix + "__"):
            continue
        path = key[len(prefix) + 2 :].split("__")
        node = result
        for part in path[:-1]:
            actual = _match_key(node, part)
            child = node.get(actual)
            if not isinstance(child, dict):
                child = {}
                node[actual] = child
            node = child
        node[_match_key(node, path[-1])] = _parse_env_value(value)
    return result


def _collect_field_errors(exc: ValidationError) -> list[str]:
    """提取校验错误的顶层字段名。"""
    fields: list[str] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        if loc:
            fields.append(str(loc[0]))
    return fields


def load_risk_model(path: Path, env_prefix: str = "RISK_MODEL") -> RiskModelConfig:
    """加载并校验 risk_model 配置（AC-2/3/4）。

    Args:
        path: YAML 配置文件路径。
        env_prefix: 环境变量覆盖前缀，默认 ``RISK_MODEL``。

    Raises:
        ConfigValidationError: 结构性错误（关键字段缺失/整体无法解析）时抛出。

    Returns:
        通过校验的 ``RiskModelConfig``（Pydantic 模型）。
    """
    raw = load_yaml(path)
    raw = apply_env_overrides(raw, env_prefix)

    # 单字段校验失败 → 降级用默认值（AC-4），结构性错误 → 拒绝启动（AC-2）
    try:
        model = RiskModelConfig.model_validate(raw)
    except ValidationError as exc:
        fallback = RiskModelConfig.model_construct()  # 全默认实例（不触发校验）
        downgraded = False
        for field in _collect_field_errors(exc):
            if hasattr(fallback, field):
                raw[field] = getattr(fallback, field)
                downgraded = True
        if not downgraded:
            raise ConfigValidationError(
                f"risk_model 配置校验失败，拒绝启动: {exc}"
            ) from exc
        try:
            model = RiskModelConfig.model_validate(raw)
        except ValidationError as exc2:
            # 关键字段（如 severity_levels）缺失会在这里触发 model_validator
            raise ConfigValidationError(
                f"risk_model 配置校验失败，拒绝启动: {exc2}"
            ) from exc2
    return model
