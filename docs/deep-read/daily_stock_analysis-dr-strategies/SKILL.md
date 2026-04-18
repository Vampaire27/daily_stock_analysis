---
name: daily_stock_analysis-dr-strategies
description: Use when working with the strategies module of daily_stock_analysis -- trading pattern YAML definitions
---

# Strategies Module (deep-read)

Comprehensive reference for the `strategies/` module of the daily_stock_analysis project. All 11 built-in trading strategy YAML files, their loader, router, and prompt-injection pipeline are covered below.

---

## 1. Module Purpose & Capabilities

The `strategies/` directory at `D:/claude/daily_stock_analysis/strategies/` stores **natural-language trading strategy definitions** in YAML format. At system startup, `SkillManager` (`src/agent/skills/base.py`) scans this directory, parses each `.yaml` file into a `Skill` dataclass, and makes the strategies available for injection into the LLM agent's system prompt. Each strategy describes a recognizable A-share market pattern (e.g., golden cross, volume breakout, Elliott wave) with entry criteria, scoring adjustments, and risk rules -- all in human-readable text, requiring no Python code to author.

Externally, the module exposes 11 built-in strategies across 4 categories (trend, pattern, reversal, framework). Strategies can be activated by user request, by automatic market-regime detection, or by default fallback. The `SkillRouter` (`src/agent/skills/router.py`) selects which strategies apply to a given analysis context, and the agent prompt builder concatenates their instructions into the final system prompt.

### Strategy Inventory

| File | `name` | `display_name` | `category` | Priority | Market Regime |
|---|---|---|---|---|---|
| `bull_trend.yaml` | `bull_trend` | 默认多头趋势 | trend | 10 | trending_up |
| `ma_golden_cross.yaml` | `ma_golden_cross` | 均线金叉 | trend | 20 | trending_up |
| `volume_breakout.yaml` | `volume_breakout` | 放量突破 | trend | 30 | trending_up |
| `shrink_pullback.yaml` | `shrink_pullback` | 缩量回踩 | trend | 40 | trending_down, sideways |
| `box_oscillation.yaml` | `box_oscillation` | 箱体震荡 | framework | 50 | sideways |
| `bottom_volume.yaml` | `bottom_volume` | 底部放量 | reversal | 60 | trending_down |
| `chan_theory.yaml` | `chan_theory` | 缠论 | framework | 70 | volatile |
| `wave_theory.yaml` | `wave_theory` | 波浪理论 | framework | 80 | volatile |
| `dragon_head.yaml` | `dragon_head` | 龙头策略 | trend | 90 | sector_hot |
| `emotion_cycle.yaml` | `emotion_cycle` | 情绪周期 | framework | 100 | sector_hot |
| `one_yang_three_yin.yaml` | `one_yang_three_yin` | 一阳夹三阴 | pattern | 110 | (none) |

---

## 2. Core Design Logic

### 2.1 Why YAML, Not Code

The module's central architectural decision is that **strategies are pure natural-language documents**, not executable code. This lets traders and analysts write or modify trading patterns without touching Python. The `Skill` dataclass (`src/agent/skills/base.py`, line 27) is a passive container; its `instructions` field is injected verbatim into the LLM's system prompt via `SkillManager.get_skill_instructions()`. The LLM itself interprets the rules and decides which tools to call.

### 2.2 How Strategies Are Defined

Each YAML file must contain four required fields (`name`, `display_name`, `description`, `instructions`). Optional metadata fields control runtime behavior:

- `category` -- groups skills for ordered prompt rendering (trend -> pattern -> reversal -> framework). See `SkillManager.get_skill_instructions()` at `src/agent/skills/base.py:433-474`.
- `core_rules` -- references the 7 core trading principles (documented in `strategies/README.md`). Used only for human-readable cross-referencing in the generated prompt.
- `required_tools` -- tool names the strategy expects the LLM to call (e.g., `get_daily_history`, `analyze_trend`).
- `aliases` -- natural-language phrases used by the `/ask` command and bot selectors to match user intent to a strategy.
- `default_priority` -- numeric ordering hint (lower = shown first). Used by `_sort_skill_pool()` in `src/agent/skills/defaults.py:142-150`.
- `market_regimes` -- regime tags that the `SkillRouter` matches against detected market conditions.
- `default_active` -- if `true`, the strategy is the default when no explicit selection is made. Only `bull_trend.yaml` sets this.
- `default_router` -- if `true`, the strategy participates in the router's fallback set. `bull_trend.yaml` and `shrink_pullback.yaml` set this.

### 2.3 Loading Architecture

```
strategies/*.yaml
      │
      ▼  (SkillManager.load_builtin_skills)
  load_skill_from_yaml() ──► Skill dataclass
      │
      ▼  (SkillManager.register)
  SkillManager._skills: Dict[str, Skill]
      │
      ▼  (SkillManager.activate)
  enabled flags set on matching skills
      │
      ▼  (SkillManager.get_skill_instructions)
  Categorized prompt text → injected into LLM system prompt
```

The loading flow (`src/agent/skills/base.py:274-312`) scans `strategies/` for all `*.yaml` and `*.yml` files plus any nested `SKILL.md` bundles, parses each into a `Skill`, and registers them by name. Custom skills loaded via `AGENT_SKILL_DIR` override built-in skills on name collision (`src/agent/skills/base.py:383-391`).

### 2.4 Strategy Selection (Router)

`SkillRouter.select_skills()` (`src/agent/skills/router.py:28-65`) implements a three-tier priority:

1. **User explicit request** -- highest priority, from `ctx.meta["skills_requested"]`.
2. **Regime-based selection** -- the router detects market regime from the technical agent's opinion (MA alignment, trend score, volume status) and calls `get_regime_skill_ids()` (`src/agent/skills/defaults.py:238-267`) to find strategies whose `market_regimes` match.
3. **Default fallback** -- falls back to `get_default_router_skill_ids()` which picks strategies with `default_router: true` (currently `bull_trend` and `shrink_pullback`).

### 2.5 Core Trading Principles Reference

All strategies reference 7 numbered principles (defined in `strategies/README.md:76-85` and `src/agent/skills/defaults.py:26-59`):

| # | Principle |
|---|---|
| 1 | 严进策略 -- Never chase; bias from MA5 < 5% to enter |
| 2 | 趋势交易 -- MA5 > MA10 > MA20 bullish alignment |
| 3 | 效率优先 -- Volume confirms trend validity |
| 4 | 买点偏好 -- Prefer pullback to moving average support |
| 5 | 风险排查 -- Negative news is a veto |
| 6 | 量价配合 -- Volume validates price movement |
| 7 | 强势趋势股放宽 -- Relaxed standards for strong trend leaders |

**Core rules coverage by strategy** (which strategies reference the most rules):
- **4 rules each (maximum)**: `chan_theory` [1,2,3,4], `emotion_cycle` [1,2,3,5], `wave_theory` [1,2,3,4]
- **3 rules each**: `bull_trend` [1,2,3], `box_oscillation` [1,2,3], `shrink_pullback` [1,2,4], `ma_golden_cross` [1,2,3], `volume_breakout` [1,2,3]
- **2 rules each**: `dragon_head` [2,7], `one_yang_three_yin` [2,4], `bottom_volume` [2,5]

**Strategies using `search_stock_news` in required_tools**: Only `dragon_head` and `emotion_cycle` include `search_stock_news` in their `required_tools` list. Two additional strategies (`shrink_pullback` and `volume_breakout`) reference news checking in their instructions but do not list it in required_tools.

---

## 3. Core Data Structures

### 3.1 Skill Dataclass

Defined at `src/agent/skills/base.py:26-79`:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `name` | `str` | required | Unique identifier (e.g., `"dragon_head"`) |
| `display_name` | `str` | required | Human-readable name (e.g., `"龙头策略"`) |
| `description` | `str` | required | When to apply this strategy |
| `instructions` | `str` | required | Full natural-language rules injected into prompt |
| `category` | `str` | `"trend"` | One of: trend, pattern, reversal, framework |
| `core_rules` | `List[int]` | `[]` | Referenced principle numbers (1-7) |
| `required_tools` | `List[str]` | `[]` | Tool names the strategy uses |
| `allowed_tools` | `List[str]` | `[]` | Optional tool allowlist from SKILL.md frontmatter |
| `aliases` | `List[str]` | `[]` | NL matching phrases |
| `enabled` | `bool` | `False` | Activation flag |
| `source` | `str` | `"builtin"` | `"builtin"` or file path |
| `default_active` | `bool` | `False` | Part of default activation set |
| `default_router` | `bool` | `False` | Part of router fallback set |
| `default_priority` | `int` | `100` | Ordering hint (lower = first) |
| `market_regimes` | `List[str]` | `[]` | Regime tags for routing |
| `user_invocable` | `bool` | `True` | Exposed in user-facing selectors |
| `disable_model_invocation` | `bool` | `False` | Prevent auto-invocation by model |
| `execution_context` | `str` | `"inline"` | inline/fork hint |
| `subagent_type` | `str` | `""` | Subagent type hint |
| `preferred_model` | `str` | `""` | Model hint |

### 3.2 YAML Schema Per Strategy

#### Trend Strategies (`category: trend`)

**bull_trend.yaml** -- The default strategy. `default_active: true`, `default_router: true`, `default_priority: 10`. Instructions emphasize MA5/MA10/MA20 bullish alignment, pullback-over-chase preference, volume confirmation, and explicit buy/hold/reduce recommendations. Required tools: `get_daily_history`, `analyze_trend`.

**ma_golden_cross.yaml** -- Detects MA5 crossing MA10 (or MA10 crossing MA20) with volume confirmation. Priority 20. Required tools: `get_daily_history`, `analyze_trend`. Scoring: +10 for MA5 x MA10 cross with volume, +8 for MA10 x MA20, +5 for MACD cross above zero.

**volume_breakout.yaml** -- Price breaks resistance on 2x average volume. Priority 30. Required tools: `get_daily_history`, `analyze_trend`, `get_realtime_quote`. Key thresholds: volume > 2x 5-day average, close above resistance, bias < 5%.

**shrink_pullback.yaml** -- Volume shrinks during pullback to MA5/MA10 in an uptrend. Priority 40. `default_router: true`. Required tools: `get_daily_history`, `analyze_trend`, `get_realtime_quote`. Entry: price within 1% of MA5 or 2% of MA10, volume < 70% of 5-day average.

**dragon_head.yaml** -- Sector leader identification during sector rotation. Priority 90. Required tools: `get_realtime_quote`, `get_sector_rankings`, `search_stock_news`. Key: sector must be top-gaining, stock must outperform sector by 2%+, turnover > 5%, volume ratio > 1.5.

#### Pattern Strategies (`category: pattern`)

**one_yang_three_yin.yaml** -- K-line pattern: big yang, 3 small yin, then yang breaking day-1 close. Priority 110 (lowest). Required tools: `get_daily_history`, `analyze_trend`. No market regime restriction (applies universally). Scoring: +15 if pattern + bullish trend, +5 if pattern only.

#### Reversal Strategies (`category: reversal`)

**bottom_volume.yaml** -- Volume spike after extended decline signals potential reversal. Priority 60. Required tools: `get_daily_history`, `analyze_trend`. Key thresholds: > 15% decline from 20-day high, volume > 3x 5-day average, close bullish candle. Position limit: 20-30%.

#### Framework Strategies (`category: framework`)

**box_oscillation.yaml** -- Range-bound trading between support and resistance. Priority 50. Required tools: `get_daily_history`, `analyze_trend`, `get_realtime_quote`. Box must be touched 2-3 times at top/bottom. Buy within 5% of support, sell within 5% of resistance. Box width 5-15% = standard.

**chan_theory.yaml** -- Zen channel theory: pen -> stroke -> segment -> hub structure. Priority 70. Required tools: `get_daily_history`, `analyze_trend`, `get_realtime_quote`. Identifies buy/sell points (一买/二买/三买), divergence (背驰), and center (中枢) structures. Scoring: +15 for bottom divergence + first buy, -15 for top divergence.

**wave_theory.yaml** -- Elliott Wave 5-wave impulse + 3-wave correction. Priority 80. Required tools: `get_daily_history`, `analyze_trend`, `get_realtime_quote`. Identifies current wave position, Fibonacci levels (0.382/0.618/1.618), and optimal entries (wave 2 pullback = safest). Scoring: +15 for wave 2 bottom, +12 for wave 3 breakout, -10 for wave 5 end.

**emotion_cycle.yaml** -- Sentiment cycle timing using turnover rate and news sentiment. Priority 100 (highest). Required tools: `get_daily_history`, `get_realtime_quote`, `analyze_trend`, `search_stock_news`. Turnover rate thresholds: < 0.5% = cold/bottom, 0.5-2% = normal, 2-5% = active, > 5% = hot, > 10% = extreme top. Scoring: +14 for 3+ bottom signals, +20 for all 5 bottom signals.

---

## 4. State Flow

### 4.1 System Startup

1. `build_agent_executor()` (`src/agent/factory.py:274-330`) is called by API endpoints (`api/v1/endpoints/agent.py`), bot commands (`bot/commands/ask.py`), or CLI entrypoints.
2. `get_skill_manager()` (`src/agent/factory.py:175-214`) creates a cached `SkillManager` prototype by calling `SkillManager.load_builtin_skills()` which reads all `.yaml` files from `D:/claude/daily_stock_analysis/strategies/`.
3. If `AGENT_SKILL_DIR` is set in config, `load_custom_skills()` overlays custom YAML files, overriding built-in skills on name collision.

### 4.2 Skill Resolution Per Request

1. `resolve_skill_prompt_state()` (`src/agent/factory.py:217-271`) determines which skills to activate:
   - If the caller passed an explicit `skills` list, those are used.
   - If `config.agent_skills` is set, those are used.
   - Otherwise, `get_default_active_skill_ids()` returns skills with `default_active: true` (currently just `bull_trend`).
2. `SkillManager.activate(skill_names)` sets `enabled=True` on matching skills and `enabled=False` on all others.
3. `SkillManager.get_skill_instructions()` concatenates instructions grouped by category (trend -> pattern -> reversal -> framework).

### 4.3 Router-Based Selection (Automatic)

When `agent_skill_routing` is set to `"auto"` (the default), `SkillRouter.select_skills()` (`src/agent/skills/router.py:28-65`) runs:

1. Checks `ctx.meta["skills_requested"]` -- if present, returns those directly.
2. Reads `agent_skill_routing` config -- if `"manual"`, returns configured skills.
3. Calls `_detect_regime()` which examines the technical agent's opinion for MA alignment, trend score, and volume status to classify the market as `trending_up`, `trending_down`, `sideways`, `volatile`, or `sector_hot`.
4. Calls `get_regime_skill_ids(regime, ...)` which filters skills whose `market_regimes` contain the detected regime.
5. Falls back to `get_default_router_skill_ids()` (skills with `default_router: true`).

### 4.4 Prompt Injection

The combined skill instructions become part of the LLM system prompt. Each active skill renders as:

```
### 技能 N: {display_name} (关联核心理念：第X、Y条)

**适用场景**: {description}

{instructions}
```

This format is generated by `SkillManager.get_skill_instructions()` at `src/agent/skills/base.py:433-474`.

---

## 5. Common Modification Scenarios

### Scenario 1: Add a New Strategy

Create a new `.yaml` file in `D:/claude/daily_stock_analysis/strategies/`. The system auto-detects it on next startup. Minimum viable file:

```yaml
name: my_new_strategy
display_name: 我的新策略
description: 检测某种新形态
category: pattern

instructions: |
  **我的新策略**

  判断标准：
  1. 使用 `get_daily_history` 获取最近30日数据。
  2. 描述你的入场条件...
  3. 描述你的出场条件...

  评分调整：
  - 条件满足时：sentiment_score +10
```

The file will be parsed by `load_skill_from_yaml()` and registered automatically. No Python changes needed.

### Scenario 2: Modify a Strategy's Parameters

Edit the YAML file directly. For example, to make `volume_breakout` require 3x volume instead of 2x, change the instructions text in `D:/claude/daily_stock_analysis/strategies/volume_breakout.yaml`. To change its priority from 30 to 25, edit the `default_priority: 30` line to `default_priority: 25`. Changes take effect on next system restart (or cache invalidation if `agent_skill_dir` changes at runtime).

### Scenario 3: Create Custom Strategies Without Touching Built-in Files

Set `AGENT_SKILL_DIR` in your config or environment to point to a custom directory (e.g., `./my_skills`). Create `.yaml` files there. The system loads built-in skills first, then overlays custom skills. If a custom skill has the same `name` as a built-in one, it replaces the built-in version (`src/agent/skills/base.py:383-391`). This is the recommended approach for personal strategy variations.

### Scenario 4: Change Which Strategies Are Active by Default

Modify `default_active: true` on the desired strategy's YAML file. Currently only `bull_trend.yaml` has this flag. The default set is computed by `get_default_active_skill_ids()` in `src/agent/skills/defaults.py:198-211`, which picks the first skill with `default_active: true` from the sorted pool.

### Scenario 5: Add a Strategy to the Router Fallback Set

Set `default_router: true` on the strategy's YAML. Currently `bull_trend.yaml` and `shrink_pullback.yaml` have this flag. The router uses these as its fallback when no regime match is found (`src/agent/skills/defaults.py:214-235`).

### Scenario 6: Target a Strategy to a Specific Market Regime

Add or modify the `market_regimes` list. Available regime tags (detected by `SkillRouter._detect_regime()` at `src/agent/skills/router.py:75-99`):

- `trending_up` -- MA alignment bullish, trend score >= 70
- `trending_down` -- MA alignment bearish, trend score <= 30
- `sideways` -- MA alignment neutral, trend score 35-65
- `volatile` -- Heavy volume, trend score 30-70
- `sector_hot` -- `ctx.meta["sector_hot"]` is truthy

---

## File Reference

| File | Path | Role |
|---|---|---|
| README | `D:/claude/daily_stock_analysis/strategies/README.md` | Documentation + YAML templates + core principles table |
| bull_trend | `D:/claude/daily_stock_analysis/strategies/bull_trend.yaml` | Default trend strategy |
| ma_golden_cross | `D:/claude/daily_stock_analysis/strategies/ma_golden_cross.yaml` | Moving average golden cross |
| volume_breakout | `D:/claude/daily_stock_analysis/strategies/volume_breakout.yaml` | Volume-confirmed resistance breakout |
| shrink_pullback | `D:/claude/daily_stock_analysis/strategies/shrink_pullback.yaml` | Shrink-volume pullback entry |
| dragon_head | `D:/claude/daily_stock_analysis/strategies/dragon_head.yaml` | Sector leader identification |
| one_yang_three_yin | `D:/claude/daily_stock_analysis/strategies/one_yang_three_yin.yaml` | K-line consolidation pattern |
| bottom_volume | `D:/claude/daily_stock_analysis/strategies/bottom_volume.yaml` | Bottom volume reversal |
| box_oscillation | `D:/claude/daily_stock_analysis/strategies/box_oscillation.yaml` | Range-bound box trading |
| chan_theory | `D:/claude/daily_stock_analysis/strategies/chan_theory.yaml` | Zen channel theory analysis |
| wave_theory | `D:/claude/daily_stock_analysis/strategies/wave_theory.yaml` | Elliott wave analysis |
| emotion_cycle | `D:/claude/daily_stock_analysis/strategies/emotion_cycle.yaml` | Sentiment cycle timing |
| Skill base | `D:/claude/daily_stock_analysis/src/agent/skills/base.py` | `Skill` dataclass, `SkillManager`, YAML/MD loaders |
| Defaults | `D:/claude/daily_stock_analysis/src/agent/skills/defaults.py` | Default/Router/Regime selection functions, policy strings |
| Router | `D:/claude/daily_stock_analysis/src/agent/skills/router.py` | `SkillRouter` -- regime detection and skill selection |
| Factory | `D:/claude/daily_stock_analysis/src/agent/factory.py` | `build_agent_executor()`, skill manager caching, prompt resolution |
| Package init | `D:/claude/daily_stock_analysis/src/agent/skills/__init__.py` | Public API exports |
