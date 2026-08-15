# WHYfxpg API 参考文档

> 本文档为 `whyfxpg` Python 包的公共 API 提供完整参考。

---

## 目录

- [安装](#安装)
- [核心接口](#核心接口)
  - [RiskScorer.assess()](#riskscorerassess---一句话风险评估)
  - [ScoringResult](#scoringresult-评分结果)
- [配置模型](#配置模型)
- [数据模型](#数据模型)
- [异常说明](#异常说明)

---

## 安装

```bash
pip install whyfxpg
```

或从源码构建：

```bash
git clone https://github.com/tiankongjintou/whyfxpg.git
cd whyfxpg
pip install -e .
```

> **Python 版本**：>= 3.10

---

## 核心接口

### `RiskScorer.assess()` — 一句话风险评估

无需启动数据库或 Web 服务，3 行代码完成风险评估。

```python
from whyfxpg import RiskScorer

result = RiskScorer.assess(
    event={
        "severity_level": "严重",
        "country": "美国",
        "product_category": "家用厨房电器",
    },
    historical_counts={
        "country_history_count": 3,
        "product_history_count": 1,
    },
    causal_factor=1.0,
)
print(result.rs_level, result.total_score)  # e.g. S 1234.5
```

**参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `event` | `dict[str, Any]` | ✅ | — | 风险事件字段字典（见下表） |
| `historical_counts` | `dict[str, int]` | ✅ | — | 历史统计计数（见下表） |
| `causal_factor` | `float` | ❌ | `1.0` | 因果传导系数，>1 表示风险传导增强 |
| `config_path` | `str` | ❌ | `"Config/risk_model.yaml"` | 风险模型配置路径 |

**`event` 必填字段**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `severity_level` | `str` | 严重度等级 | `"严重"` / `"中等"` / `"轻微"` / `"灾难性"` |
| `country` | `str` | 国别 | `"美国"` / `"欧盟"` / `"中国"` |
| `product_category` | `str` | 产品类别 | `"家用厨房电器"` / `"工业机械"` |

**`event` 可选字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_id` | `str` | 数据来源标识 |
| `probability_level` | `str` | 概率等级（自动推断时可省略） |
| `publish_date` | `str` | 发布日期 `YYYY-MM-DD` 格式（用于时效衰减计算） |

**`historical_counts` 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `country_history_count` | `int` | 该国别历史事件数（用于概率评分的事件密度） |
| `product_history_count` | `int` | 该产品类别历史事件数（用于历史密度修正） |

**返回值**：`ScoringResult` 对象（见下节）

---

### `ScoringResult` — 评分结果

`assess()` 返回的不可变数据类，包含完整的评分分解。

```python
@dataclass(frozen=True)
class ScoringResult:
    ss_score: int          # 严重度分（0-100）
    ps_score: int          # 概率分（0-100）
    probability_level: str  # 概率等级文本（非常可能/可能/不太可能/几乎不可能）
    country_factor: float  # 国别系数
    product_factor: float  # 产品系数
    history_factor: float  # 历史密度系数
    evidence_factor: float # 证据来源系数
    causal_factor: float   # 因果传导系数
    recency_decay: float  # 时效衰减系数
    total_score: float    # 原始对数总分（0-10000+）
    normalized_score: float # 归一化分（0-100，P1b-03 量纲统一）
    rs_level: str         # 风险等级（S/M/L/A）
```

**风险等级阈值（0-100 量纲，P1b-03）**

| 等级 | 阈值 | 说明 |
|------|------|------|
| `S` | ≥ 85 | 极高风险 |
| `M` | ≥ 70 | 高风险 |
| `L` | ≥ 50 | 中风险 |
| `A` | < 50 | 低风险（可接受） |

**归一化公式**

```
normalized_score = 100 * total_score / (total_score + C)
```

其中 `C = 3000`（默认归一化常数，可通过配置覆盖）。

---

## 配置模型

### `RiskModelConfig`

风险模型配置，由 `Config/risk_model.yaml` 加载。

主要字段：

```python
class RiskModelConfig(BaseModel):
    severity_levels: dict[str, LevelConfig]   # 严重度等级配置（score, label, default）
    probability_levels: dict[str, LevelConfig]  # 概率等级配置
    country_weights: dict[str, float]          # 国别权重
    product_weights: dict[str, float]          # 产品类别权重
    history_decay_base: float                  # 历史密度衰减底数
    evidence_weights: dict[str, float]         # 证据来源权重
    risk_level_thresholds: dict[str, int]      # 风险等级阈值（默认 S≥85/M≥70/L≥50）
    normalization_constant: float               # 归一化常数（默认 3000）
```

---

## 数据模型

### `ScoringResult` 字段详解

#### 严重度分 `ss_score`

根据 `severity_level` 映射：

| 等级 | 默认分 |
|------|--------|
| 灾难性 | 100 |
| 严重 | 80 |
| 中等 | 50 |
| 轻微 | 20 |

#### 概率分 `ps_score`

由 `country_history_count`（事件密度）映射到 0-100 分：

- 首次出现（count=0）→ 低概率
- 历史事件越多 → 概率分越高
- 最高可达 100 分（非常可能）

#### 最终总分 `total_score`

```
total_score = exp(log(ss_score) + log(ps_score)
                  + log(country_factor) + log(product_factor)
                  + log(history_factor) + log(evidence_factor)
                  + log(causal_factor) + log(recency_decay))
```

在**对数域求和**可防止乘法溢出。

#### 时效衰减 `recency_decay`

近期事件（90天内）衰减系数 > 1.0，提升评分；旧事件衰减 < 1.0。

---

## 异常说明

| 异常 | 触发条件 |
|------|----------|
| `ValueError` | `event` 缺少必填字段（severity_level/country/product_category） |
| `FileNotFoundError` | `config_path` 指向的文件不存在 |
| `pydantic.ValidationError` | 配置文件格式错误 |

建议用 `try/except` 包裹：

```python
from whyfxpg import RiskScorer
from pydantic import ValidationError

try:
    result = RiskScorer.assess(event, counts)
except ValidationError as e:
    print(f"配置错误: {e}")
except ValueError as e:
    print(f"参数错误: {e}")
```

---

## 代码示例

### 完整字段评估

```python
from whyfxpg import RiskScorer

r = RiskScorer.assess(
    event={
        "severity_level": "严重",
        "country": "美国",
        "product_category": "家用厨房电器",
        "source_id": "us_cpsc",
        "publish_date": "2025-08-01",
    },
    historical_counts={
        "country_history_count": 5,
        "product_history_count": 2,
    },
    causal_factor=1.5,  # 有因果传导
)
print(f"风险等级: {r.rs_level}")
print(f"原始分: {r.total_score:.2f}")
print(f"归一化分: {r.normalized_score:.2f}")
print(f"时效衰减: {r.recency_decay:.4f}")
```

### 因果传导场景

```python
# 同一供应商多次出问题 → 因果传导系数 > 1.0
r = RiskScorer.assess(
    event={"severity_level": "中等", "country": "中国", "product_category": "工业机械"},
    historical_counts={"country_history_count": 10, "product_history_count": 3},
    causal_factor=2.0,  # 供应商已被标记为高风险
)
```

### 低可信来源自动降权

```python
# 使用非权威来源时 evidence_factor < 1.0
r = RiskScorer.assess(
    event={"severity_level": "严重", "country": "某不知名地区", "product_category": "玩具"},
    historical_counts={"country_history_count": 1, "product_history_count": 0},
    causal_factor=1.0,
)
# evidence_factor 由 source_id 自动映射
```
