---
name: daily_stock_analysis-dr-scripts
description: Use when working with the scripts module of daily_stock_analysis — utility scripts for screening, review, and build
---

# Scripts Module Deep-Read Reference

## 1. Module Purpose & Capabilities

The `scripts/` directory contains all operational utilities for the daily_stock_analysis project. These scripts fall into three functional groups:

1. **Stock data pipeline** — fetch, index, and generate frontend-searchable stock catalogs from external providers (Tushare, AkShare) and internal mappings.
2. **Analysis screening & review loop** — screen for short-term trading opportunities, save recommendation records with full rationale, and retrospectively review past recommendations against real market prices.
3. **Build & CI tooling** — cross-platform (macOS + Windows/PowerShell) build scripts for the backend (PyInstaller) and Electron desktop app, plus a CI gate script and an AI governance asset checker.

### Script Inventory

| Script | Platform | Purpose |
|--------|----------|---------|
| `fetch_tushare_stock_list.py` | Python | Fetch A/HK/US stock lists from Tushare Pro API |
| `generate_stock_index.py` | Python | Build frontend autocomplete index from `STOCK_NAME_MAP` (MVP) |
| `generate_index_from_csv.py` | Python | Build frontend autocomplete index from CSV data (Tushare or AkShare) |
| `get_hot_sector_stocks.py` | Python | Get hot sector constituent stocks via AkShare or curated fallback |
| `screen_short_term_opportunity.py` | Python | Score and rank candidate stocks for short-term (10 trading days) buy signals |
| `save_recommendation.py` | Python | Append a recommendation record with full metadata to history JSON |
| `review_recommendations.py` | Python | Retrospectively review past N days of recommendations against current prices |
| `check_ai_assets.py` | Python | Validate AI collaboration assets (AGENTS.md, CLAUDE.md, skills, gitignore) |
| `ci_gate.sh` | Bash | CI gate: syntax, flake8 critical, deterministic checks, offline pytest |
| `build-backend-macos.sh` | Bash | Build PyInstaller backend + React SPA on macOS |
| `build-backend.ps1` | PowerShell | Build PyInstaller backend + React SPA on Windows |
| `build-desktop-macos.sh` | Bash | Build Electron desktop app on macOS |
| `build-desktop.ps1` | PowerShell | Build Electron desktop app on Windows |
| `build-all-macos.sh` | Bash | Orchestrator: backend + desktop build on macOS |
| `build-all.ps1` | PowerShell | Orchestrator: backend + desktop build on Windows |
| `run-desktop.ps1` | PowerShell | Launch Electron desktop app in dev mode on Windows |

---

## 2. Core Design Logic

### 2.1 Two-Phase Stock Index Strategy

The project uses a two-phase approach to building the frontend stock autocomplete index (`apps/dsa-web/public/stocks.index.json`):

- **Phase 1 (MVP)**: `generate_stock_index.py` reads from `src/data/stock_mapping.py` (`STOCK_NAME_MAP`). This is a hardcoded dictionary suitable for a limited stock universe.
- **Phase 2 (Full)**: `generate_index_from_csv.py` reads from CSV files produced by `fetch_tushare_stock_list.py` (in `data/stock_list_{a,hk,us}.csv`) or AkShare logs (in `logs/stock_basic_*.csv`). This supports the full market.

Both scripts produce the same compressed JSON array format (see Section 3.3), allowing seamless migration between phases.

### 2.2 Fallback-First Design Pattern

Multiple scripts implement graceful degradation:

- `get_hot_sector_stocks.py`: Tries AkShare `stock_board_concept_name_em()` + `stock_board_concept_cons_em()` for real-time sector constituents; falls back to `CURATED_STOCKS` (a hardcoded dictionary in the same file, lines 29–87) when network/API fails.
- `review_recommendations.py` `get_current_price()`: Tries AkShare `stock_zh_a_spot_em()` first; falls back to direct East Money HTTP API (`push2.eastmoney.com/api/qt/stock/get`) with secid constructed as `1.{code}` for codes starting with '6' (Shanghai) or `0.{code}` otherwise (Shenzhen); the `f43` field is in cents and must be divided by 100 to get yuan; returns `None` if both fail.
- The main pipeline (`src/core/pipeline.py`, not in scripts) follows the same fail-open semantic.

### 2.3 Cross-Platform Build Parity

Build scripts come in matched Bash/PowerShell pairs with identical logic:

- `build-backend-macos.sh` ↔ `build-backend.ps1` — Both build the React SPA, install PyInstaller, pip-install `requirements.txt`, verify `python-multipart` is importable, then run PyInstaller with the same `--hidden-import` list and arguments.
- `build-desktop-macos.sh` ↔ `build-desktop.ps1` — Both require the backend artifact at `dist/backend/stock_analysis`, install npm dependencies, stop running Electron processes, and run `electron-builder`.
- `build-all-macos.sh` and `build-all.ps1` are thin orchestrators that call the backend + desktop scripts in sequence.

### 2.4 Recommendation Lifecycle

The scripts form a closed loop for short-term trading recommendations:

1. `get_hot_sector_stocks.py` — produces candidate stock list (JSON to stdout).
2. `screen_short_term_opportunity.py` — scores candidates via `analyzer_service.analyze_stock()`, returns top-N ranked results (JSON to stdout).
3. `save_recommendation.py` — persists the chosen recommendation to `data/recommendations_history.json`.
4. `review_recommendations.py` — retrospectively evaluates past recommendations against current prices, writes `data/review_report.json`.

---

## 3. Core Data Structures

### 3.1 Tushare Stock List CSVs (`data/stock_list_*.csv`)

Generated by `fetch_tushare_stock_list.py`. Three files:

**`data/stock_list_a.csv`** — A-share stocks (via `stock_basic` API):
```
ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type
```
Key fields: `ts_code` (e.g. `000001.SZ`), `symbol` (e.g. `000001`), `name` (Chinese name), `exchange` (`SSE`/`SZSE`/`BSE`), `is_hs` (`N`/`H`/`S`).

**`data/stock_list_hk.csv`** — HK stocks (via `hk_basic` API):
```
ts_code,name,fullname,enname,cn_spell,market,list_status,list_date,delist_date,trade_unit,isin,curr_type
```

**`data/stock_list_us.csv`** — US stocks (via `us_basic` API, paginated):
```
ts_code,name,enname,classify,list_date,delist_date
```
`classify` values: `ADR`, `GDR`, `EQT`.

### 3.2 Frontend Stock Index (`apps/dsa-web/public/stocks.index.json`)

Produced by both `generate_stock_index.py` and `generate_index_from_csv.py`. Stored as a **compressed JSON array** (not object array) to minimize file size. Each element is a 10-element array:

| Index | Field | Example |
|-------|-------|---------|
| 0 | `canonicalCode` | `"000001.SZ"` |
| 1 | `displayCode` | `"000001"` |
| 2 | `nameZh` | `"平安银行"` |
| 3 | `pinyinFull` | `"pinganyinxing"` |
| 4 | `pinyinAbbr` | `"payx"` |
| 5 | `aliases` | `["平银"]` |
| 6 | `market` | `"CN"` / `"HK"` / `"US"` / `"BSE"` |
| 7 | `assetType` | `"stock"` |
| 8 | `active` | `true` |
| 9 | `popularity` | `100` |

The `compress_index()` function (in both index generators, e.g. `generate_index_from_csv.py` lines 523–547) converts from the object format to this array format.

### 3.3 Recommendations History (`data/recommendations_history.json`)

Managed by `save_recommendation.py` (write) and `review_recommendations.py` (read/analyze). Each record:

```json
{
  "id": 1,
  "code": "300750",
  "name": "宁德时代",
  "recommend_date": "2025-04-15",
  "recommend_timestamp": "2025-04-15T10:30:00",
  "score": 85.5,
  "price_at_recommend": 185.50,
  "sector": "新能源",
  "trend": "上升通道",
  "advice": "买入",
  "confidence": "高",
  "support": "180.00",
  "resistance": "195.00",
  "stop_loss": "175.00",
  "take_profit": "200.00",
  "buy_range": "183-186",
  "position": "30%",
  "short_outlook": "短期有望突破压力位",
  "risk_warning": "大盘系统性风险",
  "reason_summary": "技术面看涨...",
  "reason_detail": {...},
  "review_lessons": "",
  "outcome": null,
  "actual_return": null,
  "hit_stop_loss": null,
  "hit_take_profit": null,
  "success": null,
  "review_date": null,
  "days_held": null
}
```

Fields `outcome` through `days_held` are populated later by `review_recommendations.py`.

### 3.4 Review Report (`data/review_report.json`)

Produced by `review_recommendations.py`:

```json
{
  "review_date": "2025-04-15",
  "review_timestamp": "2025-04-15T18:00:00",
  "days_range": 30,
  "cutoff_date": "2025-03-16",
  "total_recommendations": 10,
  "evaluated_count": 8,
  "price_fetch_fail": 2,
  "success_count": 5,
  "fail_count": 2,
  "neutral_count": 1,
  "accuracy_rate_pct": 71.4,
  "outcomes": [...],
  "lessons": "## 成功经验\n- ..."
}
```

Each item in `outcomes`:
```json
{
  "code": "300750",
  "name": "宁德时代",
  "recommend_date": "2025-04-10",
  "recommend_price": 185.50,
  "current_price": 198.00,
  "score_at_recommend": 85.5,
  "actual_return_pct": 6.74,
  "hit_stop_loss": false,
  "hit_take_profit": true,
  "success": true,
  "outcome_label": "成功"
}
```

### 3.5 Short-Term Opportunity Screening Output

`screen_short_term_opportunity.py` outputs to stdout as JSON array. Each element:

```json
{
  "code": "300750",
  "name": "宁德时代",
  "total_score": 78.5,
  "sentiment_score": 72,
  "trend_prediction": "看多",
  "operation_advice": "买入",
  "decision_type": "buy",
  "confidence_level": "高",
  "current_price": 185.50,
  "score_details": "趋势看多 | 操作建议买入",
  "analysis_summary": "...",
  "short_term_outlook": "短期有望上涨",
  "risk_warning": "..."
}
```

### 3.6 Hot Sector Stocks Output

`get_hot_sector_stocks.py` outputs to stdout as JSON array:
```json
[
  {"code": "300750", "name": "宁德时代"},
  {"code": "688981", "name": "中芯国际"}
]
```

---

## 4. State Flow

### 4.1 Script Invocation Patterns

**Stock Data Pipeline** (run periodically to refresh stock universe):
```
fetch_tushare_stock_list.py
  -> reads TUSHARE_TOKEN from .env
  -> writes data/stock_list_a.csv, data/stock_list_hk.csv, data/stock_list_us.csv
  -> writes data/README_stock_list.md

generate_index_from_csv.py [--source tushare|akshare]
  -> reads data/stock_list_*.csv (tushare) or logs/stock_basic_*.csv (akshare)
  -> writes apps/dsa-web/public/stocks.index.json
```

**Recommendation Lifecycle** (invoked by short-term-picker skill):
```
get_hot_sector_stocks.py [--target-sectors AI,电力]
  -> stdout: JSON array of candidate stocks

screen_short_term_opportunity.py [--stocks-code-file candidates.json] [--top-n 3]
  -> imports analyzer_service.analyze_stock()
  -> stdout: JSON array of top-N scored stocks

save_recommendation.py --code 300750 --name "宁德时代" --score 85.5 --price 185.50
  [required: --code, --name]
  [optional: --score, --price, --sector, --trend, --advice, --confidence, --support, --resistance,
   --stop-loss, --take-profit, --buy-range, --position, --short-outlook, --risk,
   --reason-json, --reason-text, --review-lessons]
  -> appends to data/recommendations_history.json with auto-incremented id

review_recommendations.py [--days 30]
  -> reads data/recommendations_history.json
  -> fetches current prices (akshare -> eastmoney fallback)
  -> writes data/review_report.json
  -> stdout: JSON review report
```

**Build Pipeline** (release process):
```
# macOS:
build-all-macos.sh
  -> build-backend-macos.sh
       -> npm run build (apps/dsa-web)
       -> pip install -r requirements.txt
       -> PyInstaller --name stock_analysis --onedir --noconsole
          (hidden-imports: multipart, json_repair, tiktoken, api.*, src.services.*, uvicorn.*)
       -> cp dist/stock_analysis dist/backend/stock_analysis
  -> build-desktop-macos.sh
       -> checks dist/backend/stock_analysis exists
       -> npx electron-builder --mac dmg

# Windows:
build-all.ps1
  -> build-backend.ps1  (same logic, PowerShell)
  -> build-desktop.ps1  (same logic, PowerShell)
```

**CI Gate** (GitHub Actions `backend-gate` job):
```
ci_gate.sh [all|syntax|flake8|deterministic|offline-tests]
  -> all: runs ALL four checks in sequence: syntax_check -> flake8_checks -> deterministic_checks -> offline_test_suite
  -> syntax:    python -m py_compile on all core .py files
  -> flake8:    flake8 --select=E9,F63,F7,F82
  -> deterministic: test.sh code + test.sh yfinance
  -> offline:   pytest -m "not network"
  -> invalid input: prints usage, exits 2
```

**AI Asset Check** (GitHub Actions `ai-governance` job):
```
check_ai_assets.py
  -> ensure CLAUDE.md is symlink to AGENTS.md
  -> ensure .github/copilot-instructions.md references canonical sources
  -> ensure .github/instructions/*.instructions.md exist (backend, client, governance)
  -> ensure .claude/skills/ contains README.md + analyze-issue/SKILL.md + analyze-pr/SKILL.md + fix-issue/SKILL.md
  -> ensure .gitignore has .claude/* exclusion rules
  -> ensure no tracked .claude/ files outside .claude/skills/
```

### 4.2 Error Handling Summary

| Script | Error Strategy |
|--------|---------------|
| `fetch_tushare_stock_list.py` | Returns `None` on API failure per market; continues to next market; generates doc even with partial data |
| `generate_index_from_csv.py` | Warns on missing CSV files; skips unreadable files; US stock dedup via `get_us_delist_priority()` — assigns priority 2 to records with empty delist_date (currently active), 1 to 'NaT', 0 to actual delist dates; keeps highest priority row per ts_code, on tie keeps first CSV occurrence |
| `get_hot_sector_stocks.py` | `try/except` around all AkShare calls; falls back to `CURATED_STOCKS`; exits 1 if no candidates |
| `screen_short_term_opportunity.py` | `try/except` per stock with `time.sleep(1)` rate limiting; exits 1 if all stocks fail |
| `save_recommendation.py` | Creates `data/` directory if missing; appends to existing history |
| `review_recommendations.py` | Two-tier price fetch (akshare -> eastmoney); records `price_fetch_fail` count; marks unevaluable records as `None` success |
| `ci_gate.sh` | `set -euo pipefail`; fails fast on any check failure |
| `build-backend-macos.sh` | Checks Python, PyInstaller, python-multipart availability before build; validates output exists after PyInstaller |
| `build-desktop-macos.sh` | Checks `dist/backend/stock_analysis` exists; supports `DSA_MAC_ARCH` env var for arch targeting |
| `build-desktop.ps1` | Checks Developer Mode enabled (registry); sets `CSC_IDENTITY_AUTO_DISCOVERY=false` to skip code signing |

### 4.3 Environment Variables

| Variable | Used By | Purpose |
|----------|---------|---------|
| `TUSHARE_TOKEN` | `fetch_tushare_stock_list.py` | Tushare Pro API authentication |
| `PYTHON_BIN` | `build-backend.ps1` | Python binary path for build |
| `DSA_MAC_ARCH` | `build-desktop-macos.sh` | Target macOS architecture (`x64` or `arm64`) |
| `DSA_SKIP_DEVMODE_CHECK` | `build-desktop.ps1` | Skip Windows Developer Mode check |
| `CI` | `build-desktop.ps1` | Implicitly skips Developer Mode check when set |

---

## 5. Common Modification Scenarios

### Scenario 1: Adding a New Stock Screening Script

Follow the pattern established by `screen_short_term_opportunity.py` and `get_hot_sector_stocks.py`:

1. Accept CLI arguments via `argparse` (use `--stocks-code` and/or `--stocks-code-file` for input flexibility).
2. Load candidates using a function similar to `load_stock_candidates()` (line 27–40 in `screen_short_term_opportunity.py`).
3. Process each candidate, wrapping per-stock logic in `try/except` with error logging to `sys.stderr`.
4. Output results as JSON to stdout (using `json.dumps(..., ensure_ascii=False)`).
5. Log progress/info to `sys.stderr` so stdout remains clean JSON.
6. Exit with code 1 on total failure (no candidates, all analyses failed).
7. Add the script to `ci_gate.sh` syntax check if it is in the `src/`, `data_provider/`, or root level (note: scripts in `scripts/` are NOT currently checked by `ci_gate.sh`).

### Scenario 2: Modifying the Review/Retrospective Logic

The review logic is entirely in `review_recommendations.py`. Key functions to edit:

- **`get_current_price()`** (line 32–68): Add a new data source by inserting a new `try/except` block before the final `return None`. Follow the existing pattern: attempt import, fetch, parse, return float or continue to next source.
- **`analyze_outcome()`** (line 71–121): Modify the success/failure thresholds. Currently: `actual_return > 3` = success, `actual_return < -5` = failure. Change these thresholds or add new conditions (e.g., based on stop_loss/take_profit triggers).
- **`generate_lessons()`** (line 124–237): Add new analysis dimensions. The function builds a Markdown string with sections for successes, failures, and pattern analysis (by sector, confidence, trend). Add a new dimension by iterating over `outcomes` + `history` and appending to `lessons_parts`.

### Scenario 3: Adding a New Market to the Stock Index Generator

To add a new market (e.g., Tokyo Stock Exchange):

1. In `generate_index_from_csv.py`:
   - Add the market CSV file path in `load_tushare_data()` `market_files` dict (line 86–90).
   - Update `determine_market()` (line 360–392) to recognize the new suffix (e.g., `.T` for Tokyo).
   - Add the market to `generate_aliases()` with a new alias map (pattern at lines 409–461).
   - Add the market suffix mapping in `extract_symbol_from_ts_code()` if needed.

2. In `generate_stock_index.py`:
   - Update `determine_market_and_type()` (line 101–131) to recognize new code patterns.
   - Update `market_to_suffix()` (line 134–152) to add the new suffix.
   - Update `build_canonical_code()` (line 155–182) for exchange-specific code rules.
     `build_canonical_code(code)` determines market suffix for 6-digit Chinese codes:
     - '6xxxx' or '900xxx' → .SH (Shanghai main board/STAR/B-shares)
     - '0xxxx', '2xxxx', '3xxxx' → .SZ (Shenzhen main board/ChiNext/B-shares)
     - '920xxx', '43xx', '83xx', '87xx', '88xx', '81xx', '82xx' → .BJ (Beijing Stock Exchange)

3. In `fetch_tushare_stock_list.py`:
   - Add a new `fetch_*_stock_list()` function following the pattern of `fetch_a_stock_list()`.
   - Add the fetch call and `save_to_csv()` call in `main()`.
   - Update `generate_data_documentation()` to include the new market in the README.

### Scenario 4: Adding a New Build Hidden-Import to PyInstaller

When the backend imports a new module that PyInstaller cannot auto-detect:

1. Edit **both** `build-backend-macos.sh` (lines 57–95) and `build-backend.ps1` (lines 61–99).
2. Add the module path to the `hidden_imports` array (Bash) or `$hiddenImports` array (PowerShell).
3. The arrays must stay in sync. The hidden-import list currently covers:
   - `multipart` / `multipart.multipart` (form data parsing)
   - `json_repair` (LLM output parsing)
   - `tiktoken` / `tiktoken_ext` / `tiktoken_ext.openai_public` (token counting)
   - `api.*` (all FastAPI endpoint and schema modules)
   - `api.middlewares.*` (error handler middleware)
   - `src.services.*` (task queue, analysis service, history service)
   - `uvicorn.*` (ASGI server submodules)

### Scenario 5: Modifying the Short-Term Scoring Algorithm

The scoring logic is in `screen_short_term_opportunity.py` function `score_stock()` (line 43–128):

- **Trend score** (40% base): Derived from `sentiment_score` (0–100, mapped to 0–40 points) plus bonus/penalty for `trend_prediction` text matching ("强烈看多" +5, "看多" +3, "看空" -5).
- **Buy-point score** (35% base): Based on `operation_advice` ("买入" +20, "加仓" +15, "持有" +5, "卖出" -10) plus `decision_type` ("buy" +10, "sell" -5).
- **Short-term probability** (25% base): Based on `confidence_level` ("高" +10, "低" -5) plus keyword matching in `short_term_outlook` against positive/negative word lists.

To add a new scoring dimension:
1. Add a new section in `score_stock()` that extracts the relevant attribute from `result`.
2. Compute a score contribution and append to `details`.
3. Adjust the weight distribution if you want to keep the total bounded (currently scores can range approximately -20 to 100+).
