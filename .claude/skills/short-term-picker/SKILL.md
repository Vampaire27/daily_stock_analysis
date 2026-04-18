---
name: "short-term-picker"
description: >
  推荐一只适合短期（10 个交易日内）买入的股票。
  当用户要求推荐股票、选股、找买点、短线机会、黄金买点、今日好股时调用。
  适用于：用户想找一只大概率短期上涨的股票，或者问"今天买什么好"、"推荐一个短线买点"、
  "哪只股票现在位置好"、"AI板块有买入机会吗"、"电力股能买吗"等场景。
  也适用于用户问"帮我选一只股票"、"有什么短线机会"、"找出最佳买点"等情况。
  注意：本技能只针对 A 股，不涉及港股和美股。
  如果用户明确要求推荐多只股票或做市场分析，请使用 stock-analyzer 技能代替。
  **每次推荐后自动保存记录，下次推荐时自动复盘历史表现，持续学习提高准确率。**
---

# 短线买点推荐器

从长线向好行业中自动扫描热门板块，逐一分析后推荐 **1 支** 最可能在未来 10 个交易日上涨的股票。

## 迭代学习机制

本技能会持续从推荐表现中学习：

1. 每次推荐后保存完整记录（代码、价格、逻辑、原因）
2. 下次推荐前复盘过去一个月的表现
3. 分析成功/失败模式，调整筛选偏好
4. 将经验教训写入 SKILL.md 和本地笔记

**当前已知经验**：（随着推荐积累，这里会持续更新，完整记录见 `data/recommendations_daily_log.md`）

> *截至 2026-04-16，共 2 条推荐记录（002475立讯精密 84分 / 688981中芯国际 65分），尚未达到 5+ 条模式分析阈值。*
>
> **初步观察**：
> - 行业集中度：两次推荐均为 AI芯片/半导体 方向，反映当前板块景气度高，但需警惕过度集中风险
> - 评分差异：追涨型(强烈看多)评分 84 vs 横盘突破型评分 65，哪种短线胜率更高待复盘验证
> - 数据源问题：akshare/东方财富连接频繁失败，需依赖内置行业龙头降级策略
> - 待验证假设：高评分(>80)+高置信度 vs 中等评分(60-70)+中置信度，哪个表现更好？

## 筛选标准

本技能推荐股票严格遵循以下三个维度：

1. **长期趋势向好**：所属行业中长期景气（AI、电力、半导体、新能源、机器人等）
2. **当前处于好买点**：技术分析显示价格位置合适（回踩企稳、底部放量、突破回踩等）
3. **短期上涨概率高**：AI 分析判断短期内（1-2 周）大概率上涨，且置信度较大

## 工作流程

### Step 1: 确认环境

```bash
cd D:\claude\daily_stock_analysis
.venv/Scripts/python.exe -c "from analyzer_service import analyze_stock; print('OK')"
```

如果导入失败，告知用户并停止。

### Step 2: 复盘历史推荐（如有数据）

```bash
.venv/Scripts/python.exe scripts/review_recommendations.py --days 30
```

**触发条件**：`data/recommendations_history.json` 中有 > 3 条可评估记录时才执行。

如果记录不足或网络无法获取价格，跳过此步（不要报错，继续推荐）。

**如果有复盘报告**：
1. 读取 `data/review_report.json` 的 `lessons` 字段
2. 关注高成功率的行业/趋势形态、失败案例的共同特征
3. 在推荐输出中加入"复盘经验"部分

### Step 3: 获取候选股票

```bash
.venv/Scripts/python.exe scripts/get_hot_sector_stocks.py --max-stocks 30 > data/candidates.json 2>/dev/null
```

脚本内置双重策略：
- **优先**：akshare 实时获取概念板块成分股
- **降级**：网络不可用时使用内置行业龙头列表（这是正常行为，不需要修复）

**可选**：用户指定行业时传 `--target-sectors` 参数。

### Step 4: 分析并评分

```bash
.venv/Scripts/python.exe scripts/screen_short_term_opportunity.py --stocks-code-file data/candidates.json --top-n 3 --max-analyze 15
```

评分逻辑：
- **趋势分（40%）**：sentiment_score + trend_prediction
- **买点分（35%）**：operation_advice + decision_type
- **短期概率（25%）**：short_term_outlook + confidence_level

**耗时提醒**：每只股票约 2-5 分钟（调用 LLM API），提前告知用户。

### Step 5: 保存推荐记录（必做）

```bash
.venv/Scripts/python.exe scripts/save_recommendation.py \
  --code "股票代码" --name "股票名称" --score 评分 --price 现价 \
  --sector "行业" --trend "趋势" --advice "建议" --confidence "置信度" \
  --support "支撑" --resistance "压力" --stop-loss "止损" --take-profit "止盈" \
  --buy-range "买入区间" --position "仓位" --short-outlook "展望" \
  --risk "风险提示" --reason-text "推荐理由摘要"
```

所有字段从 Step 4 分析结果中获取。

### Step 6: 呈现推荐结果

```markdown
# 短线买点推荐

**推荐日期**: YYYY-MM-DD
**推荐股票**: <code> <name>
**综合评分**: <score>

## 为什么推荐

### 长期趋势
- 所属行业：<sector>
- 行业景气度：<bullish_bearish>
- 长期趋势判断：<trend_description>

### 当前买点位置
- 现价：<price>
- 趋势状态：<trend_status>
- 买入信号：<buy_signal>
- 技术形态：<pattern>

### 短期上涨概率
- 10日展望：<short_term_outlook>
- 置信度：<confidence>
- 支撑位：<support>
- 压力位：<resistance>

## 操作计划

- **建议买入价位**：<buy_price_range>
- **止损位**：<stop_loss>
- **第一止盈位**：<take_profit_1>
- **第二止盈位**：<take_profit_2>
- **建议仓位**：<position_size>
- **持有周期**：5-10个交易日

## 风险提示

<risk_warning>

## 复盘经验

<如有历史推荐数据，在此总结成功/失败模式和关键教训>

---
*以上推荐基于技术分析和AI模型判断，不构成投资建议。股市有风险，入市需谨慎。*
```

## 重要约束

- **只推荐 1 支** 股票
- **必须基于实际分析结果**，不能凭空编造
- **必须包含风险提示和止损位**
- **每次推荐后必须保存记录**
- 分析全部失败时明确告知用户
- 提前告知用户 LLM API 调用耗时

## 快速模式

```bash
.venv/Scripts/python.exe scripts/screen_short_term_opportunity.py --stocks-code "300750,688981,601985,002594,600519,000001" --top-n 3
```

## 相关文件

- 板块扫描：[`scripts/get_hot_sector_stocks.py`](../../scripts/get_hot_sector_stocks.py)
- 筛选评分：[`scripts/screen_short_term_opportunity.py`](../../scripts/screen_short_term_opportunity.py)
- 分析服务：[`analyzer_service.py`](../../analyzer_service.py)
- 保存推荐：[`scripts/save_recommendation.py`](../../scripts/save_recommendation.py)
- 复盘总结：[`scripts/review_recommendations.py`](../../scripts/review_recommendations.py)
- 推荐历史：[`data/recommendations_history.json`](../../data/recommendations_history.json)
- 复盘报告：[`data/review_report.json`](../../data/review_report.json)
