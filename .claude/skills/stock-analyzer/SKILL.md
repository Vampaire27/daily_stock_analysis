# Stock Analyzer

分析股票和市场。支持单股分析、批量分析和大盘复盘，直接在本地调用 Python 分析流程，无需启动 API 服务。

**Repository**: https://github.com/ZhuLinsen/daily_stock_analysis

## Usage

```text
/stock-analyzer <stock_codes>                # 单股或批量分析（逗号分隔）
/stock-analyzer --market-review              # 大盘复盘
/stock-analyzer --market-review <stock_codes> # 复盘 + 个股分析
```

示例：

```text
/stock-analyzer 600519
/stock-analyzer 600519,hk00700,AAPL
/stock-analyzer --market-review
/stock-analyzer --market-review 300750,TSLA
```

## Instructions

分析时优先遵循仓库根目录 `AGENTS.md`。工作目录必须在项目根目录下。

### Step 1: 解析参数

从用户输入中识别：

- **股票代码**：逗号分隔的代码列表（可选）
- **`--market-review` 标志**：是否执行大盘复盘（可选）
- 至少需要提供股票代码或 `--market-review` 之一

校验股票代码格式：

| 类型 | 格式 | 示例 |
|------|------|------|
| A 股 | 6 位数字 | `600519`、`000001`、`300750` |
| 北交所 | 8/4/92 开头 6 位 | `920748`、`838163` |
| 港股 | hk + 5 位数字 | `hk00700`、`hk09988` |
| 美股 | 1-5 字母（可选 .X 后缀） | `AAPL`、`TSLA`、`BRK.B` |
| 美股指数 | SPX/DJI/IXIC 等 | `SPX`、`DJI`、`VIX` |

若用户提供了中文名称（如「茅台」），提示其提供股票代码，或使用常见映射辅助转换。

### Step 2: 环境检查

确认分析环境可用：

```bash
python -c "from analyzer_service import analyze_stock; print('OK')"
```

若导入失败，检查：
- 当前目录是否为项目根目录
- 依赖是否已安装（`pip install -r requirements.txt`）

检查 `.env` 是否存在且包含 LLM 配置（至少需要一个 LLM 通道配置，如 `GEMINI_API_KEY` 或 `LLM_CHANNELS`）：

```bash
test -f .env && grep -qE "GEMINI_API_KEY|LLM_CHANNELS|OPENAI_API_KEY|DEEPSEEK_API_KEY" .env && echo "LLM config found" || echo "WARNING: No LLM config in .env"
```

若缺少 LLM 配置，警告用户分析将无法调用 AI 模型。可用 `--dry-run` 模式仅抓取数据。

### Step 3: 执行分析

根据解析结果选择执行路径。优先使用 `main.py` CLI 入口（输出更完整、支持通知和报告生成），必要时回退到 `analyzer_service.py` 直接调用。

**单股分析：**

```bash
python main.py --stocks <stock_code> --force-run
```

**批量分析：**

```bash
python main.py --stocks <code1>,<code2>,<code3> --force-run
```

**大盘复盘：**

```bash
python main.py --market-review --force-run
```

**复盘 + 个股：**

```bash
python main.py --market-review --stocks <codes> --force-run
```

**仅抓取数据（无 LLM 配置时的降级方案）：**

```bash
python main.py --stocks <codes> --dry-run --force-run
```

说明：
- `--force-run` 跳过交易日检查，确保非交易日也能执行
- 分析耗时约 2-5 分钟/只，取决于 LLM 响应速度和数据源可用性
- 批量分析时股票按顺序逐只执行，已分析的股票自动跳过（断点续传）

### Step 4: 呈现结果

分析完成后，从输出中提取关键信息，以结构化格式呈现给用户：

**个股分析结果应包含：**
- 股票名称和代码
- 核心结论（一句话总结）
- 信号类型和操作建议
- 趋势状态和价格位置
- 狙击点（买入/卖出目标价位）
- 风险提示

**大盘复盘结果应包含：**
- 市场整体走势总结
- 板块表现
- 资金流向
- 后市展望

若分析过程产生了报告文件（默认存储在 `reports/` 目录），告知用户报告路径。

### Step 5: 保存分析产物

将本次分析的摘要保存到 `.claude/reviews/analysis/` 目录：

- 文件名格式：`analysis-<stock_code>-<YYYY-MM-DD>.md` 或 `market-review-<YYYY-MM-DD>.md`
- 内容为 Step 4 中结构化呈现的结果摘要

## Output Document Format

```markdown
# Stock Analysis: <stock_code> <stock_name>

**Date**: YYYY-MM-DD
**Mode**: 单股分析 / 批量分析 / 大盘复盘

## Core Conclusion

- 核心结论：
- 信号类型：
- 操作建议：

## Data Perspective

- 趋势状态：
- 价格位置：
- 量能分析：
- 筹码结构：

## Intelligence

- 关键新闻：
- 风险警报：
- 积极催化剂：

## Battle Plan

- 狙击点（买入目标）：
- 止损价位：
- 止盈目标：
- 仓位策略：

## Execution Details

- 执行命令：
- 耗时：
- 报告文件路径：
- 数据源：
```

## Allowed Auto-Actions (No Confirmation Needed)

- 读取项目文件、配置和代码
- 检查 `.env` 中是否存在 LLM 配置项（仅检查 key 名称是否存在，不读取 key 值）
- 执行 `python main.py --stocks ... --force-run` 运行分析
- 执行 `python main.py --market-review --force-run` 运行大盘复盘
- 执行 `python main.py --dry-run` 仅抓取数据
- 在 `.claude/reviews/analysis/` 目录下生成分析摘要文档

## Actions Requiring Confirmation

执行以下动作前，先询问用户：

1. 修改 `.env` 配置文件
2. 安装或更新 Python 依赖
3. 执行带 `--schedule` 的定时模式
4. 执行带 `--serve` 的 API 服务模式
5. 执行任何 `git` 操作
6. 发送通知（默认 `main.py` 会根据 `.env` 配置自动发送通知，若用户不希望发送，应追加 `--no-notify`）
