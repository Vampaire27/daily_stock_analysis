#!/usr/bin/env python
"""
复盘过去 N 天的短线推荐股票。
对比推荐时的预期与实际走势，总结成功和失败的经验。

Usage: python scripts/review_recommendations.py [--days 30]
       默认复盘过去 30 个自然日内的推荐记录。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

RECOMMENDATIONS_FILE = os.path.join(_PROJECT_ROOT, "data", "recommendations_history.json")
REVIEW_OUTPUT_FILE = os.path.join(_PROJECT_ROOT, "data", "review_report.json")


def load_history() -> list:
    """加载推荐历史"""
    if os.path.exists(RECOMMENDATIONS_FILE):
        with open(RECOMMENDATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_current_price(code: str) -> float | None:
    """
    获取股票当前价格（实时）。
    尝试多个数据源，全部失败时返回 None。
    """
    # 方法 1: akshare 东方财富接口
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if not row.empty:
            price = float(row.iloc[0]["最新价"])
            print(f"  [OK] {code} 价格: {price} (来源: akshare)", file=sys.stderr)
            return price
    except Exception as e:
        print(f"  [WARN] akshare 获取 {code} 价格失败: {e}", file=sys.stderr)

    # 方法 2: 直接请求东方财富 API
    try:
        import urllib.request
        prefix = "1" if code.startswith("6") else "0"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={prefix}.{code}&fields=f43"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            price = data.get("data", {}).get("f43")
            if price and price > 0:
                # f43 单位是分，需要除以 100
                price_yuan = float(price) / 100.0
                print(f"  [OK] {code} 价格: {price_yuan} (来源: eastmoney)", file=sys.stderr)
                return price_yuan
    except Exception as e:
        print(f"  [WARN] eastmoney API 获取 {code} 价格失败: {e}", file=sys.stderr)

    # 全部失败
    print(f"  [FAIL] 无法获取 {code} 实时价格（所有数据源不可用）", file=sys.stderr)
    return None


def analyze_outcome(record: dict, current_price: float | None) -> dict:
    """分析单只推荐股票的结果"""
    code = record["code"]
    recommend_price = record.get("price_at_recommend", 0)
    stop_loss_str = record.get("stop_loss", "")
    take_profit_str = record.get("take_profit", "")

    outcome = {
        "code": code,
        "name": record.get("name", ""),
        "recommend_date": record.get("recommend_date", ""),
        "recommend_price": recommend_price,
        "current_price": current_price,
        "score_at_recommend": record.get("score", 0),
    }

    if current_price and recommend_price > 0:
        actual_return = (current_price - recommend_price) / recommend_price * 100
        outcome["actual_return_pct"] = round(actual_return, 2)

        # 判断是否触发止损
        try:
            stop_loss = float(str(stop_loss_str).replace(",", "").replace("元", "").strip())
            if stop_loss > 0:
                outcome["hit_stop_loss"] = current_price <= stop_loss
        except (ValueError, TypeError):
            pass

        # 判断是否达到止盈
        try:
            take_profit = float(str(take_profit_str).replace(",", "").replace("元", "").strip().split("-")[0])
            if take_profit > 0:
                outcome["hit_take_profit"] = current_price >= take_profit
        except (ValueError, TypeError):
            pass

        # 综合判断成功/失败
        # 短线推荐，10 个交易日内，收益 > 3% 算成功，< -5% 算失败
        if actual_return > 3:
            outcome["success"] = True
            outcome["outcome_label"] = "成功"
        elif actual_return < -5:
            outcome["success"] = False
            outcome["outcome_label"] = "失败"
        else:
            outcome["success"] = None
            outcome["outcome_label"] = "中性"
    else:
        outcome["outcome_label"] = "无法评估（缺少价格数据）"

    return outcome


def generate_lessons(outcomes: list, history: list) -> str:
    """基于复盘结果生成经验总结"""
    successes = [o for o in outcomes if o.get("success") is True]
    failures = [o for o in outcomes if o.get("success") is False]

    lessons_parts = []

    # --- 成功经验 ---
    if successes:
        lessons_parts.append("## 成功经验")
        for s in successes:
            code = s["code"]
            ret = s.get("actual_return_pct", "N/A")
            rec = next((r for r in history if r["code"] == code), {})
            trend = rec.get("trend", "")
            advice = rec.get("advice", "")
            sector = rec.get("sector", "")
            confidence = rec.get("confidence", "")
            lessons_parts.append(
                f"- **{code} {rec.get('name', '')}** (收益 {ret}%): "
                f"行业={sector}, 趋势={trend}, 建议={advice}, 置信度={confidence}"
            )

    # --- 失败教训 ---
    if failures:
        lessons_parts.append("## 失败教训")
        for f_item in failures:
            code = f_item["code"]
            ret = f_item.get("actual_return_pct", "N/A")
            rec = next((r for r in history if r["code"] == code), {})
            trend = rec.get("trend", "")
            advice = rec.get("advice", "")
            sector = rec.get("sector", "")
            confidence = rec.get("confidence", "")
            stop_loss = rec.get("stop_loss", "")
            lessons_parts.append(
                f"- **{code} {rec.get('name', '')}** (收益 {ret}%): "
                f"行业={sector}, 趋势={trend}, 建议={advice}, 置信度={confidence}, "
                f"止损={stop_loss}"
            )

    # --- 模式分析 ---
    if successes or failures:
        lessons_parts.append("## 模式总结")

        # 按行业统计
        sector_stats = {}
        all_evaluated = successes + failures
        for item in all_evaluated:
            code = item["code"]
            rec = next((r for r in history if r["code"] == code), {})
            sector = rec.get("sector", "未知")
            if sector not in sector_stats:
                sector_stats[sector] = {"total": 0, "success": 0, "fail": 0}
            sector_stats[sector]["total"] += 1
            if item.get("success") is True:
                sector_stats[sector]["success"] += 1
            else:
                sector_stats[sector]["fail"] += 1

        lessons_parts.append("### 行业准确率")
        for sector, stats in sorted(sector_stats.items(), key=lambda x: x[1]["total"], reverse=True):
            rate = stats["success"] / stats["total"] * 100 if stats["total"] > 0 else 0
            lessons_parts.append(
                f"- {sector}: {stats['success']}/{stats['total']} ({rate:.0f}% 成功率)"
            )

        # 按置信度统计
        conf_stats = {}
        for item in all_evaluated:
            code = item["code"]
            rec = next((r for r in history if r["code"] == code), {})
            conf = rec.get("confidence", "未知")
            if conf not in conf_stats:
                conf_stats[conf] = {"total": 0, "success": 0}
            conf_stats[conf]["total"] += 1
            if item.get("success") is True:
                conf_stats[conf]["success"] += 1

        if conf_stats:
            lessons_parts.append("### 置信度准确率")
            for conf in ["高", "中", "低"]:
                if conf in conf_stats:
                    stats = conf_stats[conf]
                    rate = stats["success"] / stats["total"] * 100 if stats["total"] > 0 else 0
                    lessons_parts.append(
                        f"- {conf}: {stats['success']}/{stats['total']} ({rate:.0f}% 成功率)"
                    )

        # 按趋势状态统计
        trend_stats = {}
        for item in all_evaluated:
            code = item["code"]
            rec = next((r for r in history if r["code"] == code), {})
            trend = rec.get("trend", "未知")
            if trend not in trend_stats:
                trend_stats[trend] = {"total": 0, "success": 0}
            trend_stats[trend]["total"] += 1
            if item.get("success") is True:
                trend_stats[trend]["success"] += 1

        if trend_stats:
            lessons_parts.append("### 趋势状态准确率")
            for trend, stats in sorted(trend_stats.items(), key=lambda x: x[1]["total"], reverse=True):
                rate = stats["success"] / stats["total"] * 100 if stats["total"] > 0 else 0
                lessons_parts.append(
                    f"- {trend}: {stats['success']}/{stats['total']} ({rate:.0f}% 成功率)"
                )

    if not lessons_parts:
        lessons_parts.append("## 暂无可评估数据")
        lessons_parts.append("没有足够价格数据或推荐记录不足，无法进行有效复盘。")

    return "\n".join(lessons_parts)


def main():
    parser = argparse.ArgumentParser(description="复盘短线推荐股票")
    parser.add_argument("--days", type=int, default=30, help="复盘过去多少天内的推荐（默认 30 天）")
    parser.add_argument("--output", default="", help="输出复盘报告 JSON 文件路径（默认自动）")
    args = parser.parse_args()

    history = load_history()
    if not history:
        print("[INFO] 没有推荐记录，跳过复盘", file=sys.stderr)
        print(json.dumps({"status": "no_data", "message": "没有推荐记录"}, ensure_ascii=False))
        return

    # 筛选过去 N 天内的推荐
    cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    recent = [r for r in history if r.get("recommend_date", "") >= cutoff]

    if not recent:
        print(f"[INFO] 过去 {args.days} 天内没有推荐记录", file=sys.stderr)
        print(json.dumps({"status": "no_recent_data", "cutoff_date": cutoff}, ensure_ascii=False))
        return

    print(f"复盘过去 {args.days} 天内的 {len(recent)} 条推荐记录...", file=sys.stderr)

    # 逐只评估
    outcomes = []
    price_fail_count = 0
    for record in recent:
        code = record["code"]
        current_price = get_current_price(code)
        if current_price is None:
            price_fail_count += 1
        outcome = analyze_outcome(record, current_price)
        outcomes.append(outcome)
        label = outcome.get("outcome_label", "N/A")
        ret = outcome.get("actual_return_pct", "N/A")
        print(f"  {code} {record.get('name', '')}: {label} (收益 {ret}%)", file=sys.stderr)

    # 生成经验总结
    lessons = generate_lessons(outcomes, history)

    # 构建复盘报告
    success_count = len([o for o in outcomes if o.get("success") is True])
    fail_count = len([o for o in outcomes if o.get("success") is False])
    total_evaluated = success_count + fail_count
    accuracy = success_count / total_evaluated * 100 if total_evaluated > 0 else 0

    report = {
        "review_date": datetime.now().strftime("%Y-%m-%d"),
        "review_timestamp": datetime.now().isoformat(),
        "days_range": args.days,
        "cutoff_date": cutoff,
        "total_recommendations": len(recent),
        "evaluated_count": total_evaluated,
        "price_fetch_fail": price_fail_count,
        "success_count": success_count,
        "fail_count": fail_count,
        "neutral_count": len([o for o in outcomes if o.get("success") is None]),
        "accuracy_rate_pct": round(accuracy, 1),
        "outcomes": outcomes,
        "lessons": lessons,
    }

    # 保存复盘报告
    output_path = args.output or REVIEW_OUTPUT_FILE
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}", file=sys.stderr)
    print(f"复盘报告已保存: {output_path}", file=sys.stderr)
    print(f"评估总数: {len(recent)} 条推荐", file=sys.stderr)
    print(f"可评估: {total_evaluated} 条", file=sys.stderr)
    if price_fail_count > 0:
        print(f"价格获取失败: {price_fail_count} 条（网络不可用）", file=sys.stderr)
    print(f"成功: {success_count} | 失败: {fail_count} | 中性: {len(recent) - total_evaluated - price_fail_count}", file=sys.stderr)
    if total_evaluated > 0:
        print(f"准确率: {accuracy:.1f}%", file=sys.stderr)
    print(f"{'=' * 50}", file=sys.stderr)

    # 输出复盘报告 JSON 到 stdout（供 skill 读取）
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
