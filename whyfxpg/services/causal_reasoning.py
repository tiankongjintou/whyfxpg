"""
纯算法模块：因果图推理。

不含任何数据库/网络依赖；只依赖一个实现了 `GraphView` 的对象读取图数据。
这样 `CausalKnowledge` 与 `InMemoryCausalAdapter` 可以复用同一套推理逻辑。
"""

from collections.abc import Sequence
from typing import Any, Protocol


class GraphView(Protocol):
    """推理层所需的最小图视图接口。"""

    def get_node(self, node_id: str) -> dict[str, Any] | None: ...
    def get_causal_chain(
        self,
        start_node: str,
        depth: int = 3,
        edge_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]: ...


class CausalReasoning:
    """
    因果图推理算法。

    提供：
    - factor(event, view)：基于制造商/供应链/危害类型的风险增强因子
    - explain(event, view)：生成因果溯源文本
    - counterfactual(event, intervention, view)：给定干预，计算假设风险变化
    - compute_downstream_risk(node_id, view)：计算某节点的下游传播风险
    """

    def compute_downstream_risk(self, node_id: str, view: GraphView) -> float:
        """计算某节点的向下游传播风险分。"""
        node = view.get_node(node_id)
        if not node:
            return 0.0
        node_risk = node.get("risk_score", 0.5)
        max_propagated = 0.0
        for hop in view.get_causal_chain(node_id, depth=1, edge_types=["causes", "aggravates"]):
            # depth=1 只取直接下游边
            downstream = view.get_node(hop["to"])
            downstream_risk = downstream.get("risk_score", 0.5) if downstream else 0.0
            weight = hop.get("weight", 0.5)
            propagated = node_risk * weight * downstream_risk
            max_propagated = max(max_propagated, propagated)
        return round(min(max_propagated, 1.0), 4)

    def factor(self, event: dict[str, Any], view: GraphView) -> float:
        """
        根据事件的制造商/供应商信息，计算因果增强系数。
        返回 [0.5, 2.0] 范围的系数。
        """
        manufacturer = event.get("manufacturer", "")
        country = event.get("country", "")
        hazard_type = event.get("hazard_type", "")

        factor = 1.0

        # 制造商 → 供应链上游风险
        if manufacturer and manufacturer != "unknown":
            mfr_node_id = f"manufacturer:{manufacturer}"
            if view.get_node(mfr_node_id):
                chain = view.get_causal_chain(mfr_node_id, depth=2, edge_types=["uses", "supplies"])
                for hop in chain:
                    if hop.get("weight", 0.0) > 0.7:
                        factor *= (1 + hop["weight"] * 0.3)

        # 危害类型 → 上游缺陷模式风险
        if hazard_type and hazard_type != "unknown":
            hazard_node_id = f"hazard_category:{hazard_type}"
            if view.get_node(hazard_node_id):
                chain = view.get_causal_chain(hazard_node_id, depth=2, edge_types=["causes", "aggravates"])
                upstream_risk = max((hop.get("weight", 0.0) for hop in chain), default=0.0)
                if upstream_risk > 0.5:
                    factor *= (1 + upstream_risk * 0.2)

        # 国别节点 risk_score
        if country and country != "unknown":
            country_node_id = f"country:{country}"
            country_node = view.get_node(country_node_id)
            if country_node:
                factor *= country_node.get("risk_score", 1.0)

        return round(max(0.5, min(factor, 2.0)), 3)

    def explain(self, event: dict[str, Any], view: GraphView) -> str:
        """生成风险事件的因果解释。"""
        manufacturer = event.get("manufacturer", "")
        hazard_type = event.get("hazard_type", "")
        product_name = event.get("product_name", "未知产品")

        lines = [f"【因果分析】{product_name}风险溯源："]

        if manufacturer and manufacturer != "unknown":
            mfr_node = f"manufacturer:{manufacturer}"
            if view.get_node(mfr_node):
                chain = view.get_causal_chain(mfr_node, depth=3, edge_types=["uses", "supplies", "causes"])
                if chain:
                    lines.append(f"  制造商 '{manufacturer}' 的供应链因果链：")
                    for hop in chain[:4]:
                        lines.append(
                            f"    → {hop['from_name']} --[{hop['edge_type']}×{hop['weight']:.2f}]→ "
                            f"{hop['to_name']}"
                        )
                else:
                    lines.append(f"  制造商 '{manufacturer}' 无显著上游因果风险。")
            else:
                lines.append(f"  制造商 '{manufacturer}' 未在因果知识库中，需人工标注。")

        if hazard_type and hazard_type != "unknown":
            hazard_node = f"hazard_category:{hazard_type}"
            if view.get_node(hazard_node):
                chain = view.get_causal_chain(hazard_node, depth=3, edge_types=["causes", "aggravates"])
                if chain:
                    lines.append(f"  危害类型 '{hazard_type}' 的上游因果链：")
                    for hop in chain[:3]:
                        lines.append(
                            f"    ← {hop['to_name']} --[{hop['edge_type']}×{hop['weight']:.2f}]-- "
                            f"{hop['from_name']}"
                        )

        causal_factor = self.factor(event, view)
        if causal_factor != 1.0:
            direction = "放大" if causal_factor > 1.0 else "缩小"
            lines.append(f"  因果修正系数：{causal_factor:.2f}（整体{direction}风险）")
        else:
            lines.append("  因果修正系数：1.00（无因果修正）")

        return "\n".join(lines)

    def counterfactual(
        self,
        event: dict[str, Any],
        intervention: dict[str, str],
        view: GraphView,
    ) -> dict[str, Any]:
        """反事实推理：给定干预，计算假设风险变化。"""
        original_score = event.get("total_score", 0) or 0
        original_factor = self.factor(event, view)
        base_score = original_score / original_factor if original_factor > 0 else original_score

        # 构造干预后的事件副本
        counterfactual_event = dict(event)
        action = intervention.get("action", "")
        for key, value in intervention.items():
            if key == "action":
                continue
            # 允许直接覆盖事件字段（如 country, manufacturer, hazard_type, component_type）
            counterfactual_event[key] = value

        # 保留旧 action 语义：replace_supplier / upgrade_standard 给出固定折扣
        if action == "replace_supplier":
            counterfactual_event["manufacturer"] = intervention.get("target", counterfactual_event.get("manufacturer", ""))
        elif action == "upgrade_standard":
            counterfactual_event["standard_version"] = intervention.get("to", "IEC")

        counterfactual_factor = self.factor(counterfactual_event, view)

        # 已知 action 的固定折扣语义
        if action == "replace_supplier":
            counterfactual_factor = counterfactual_factor * 0.7
        elif action == "upgrade_standard":
            counterfactual_factor = counterfactual_factor * 0.6

        counterfactual_factor = round(max(0.5, min(counterfactual_factor, 2.0)), 3)
        new_score = base_score * counterfactual_factor

        if action == "replace_supplier":
            explanation = (
                f"若将{event.get('manufacturer', '?')}的供应商替换为认证供应商，"
                f"预计因果风险因子从{original_factor:.2f}降至{counterfactual_factor:.2f}，"
                f"风险分从{original_score:.0f}降至{new_score:.0f}。"
            )
        elif action == "upgrade_standard":
            explanation = (
                f"若该产品符合{intervention.get('to', 'IEC')}标准，"
                f"风险分从{original_score:.0f}降至{new_score:.0f}。"
            )
        else:
            changed_fields = ", ".join(f"{k}={v}" for k, v in intervention.items() if k != "action")
            if changed_fields:
                explanation = (
                    f"若将 {changed_fields} 改为给定值，"
                    f"因果风险因子从{original_factor:.2f}变为{counterfactual_factor:.2f}，"
                    f"风险分从{original_score:.0f}变为{new_score:.0f}。"
                )
            else:
                explanation = "未指定有效干预，无法计算反事实。"

        return {
            "original_score": original_score,
            "counterfactual_score": round(new_score, 2),
            "delta": round(new_score - original_score, 2),
            "original_factor": original_factor,
            "counterfactual_factor": counterfactual_factor,
            "explanation": explanation,
        }
