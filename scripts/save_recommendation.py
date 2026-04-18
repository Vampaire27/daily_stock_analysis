#!/usr/bin/env python
"""
保存短线推荐股票及其推荐逻辑。
每次 short-term-picker 推荐股票后调用，将推荐结果追加到推荐历史文件。

Usage: python scripts/save_recommendation.py --code 300750 --name "宁德时代" \
    --score 85.5 --price 185.50 --reason-json reason.json
"""
import argparse
import json
import os
import sys
from datetime import datetime

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 推荐历史文件路径
RECOMMENDATIONS_FILE = os.path.join(_PROJECT_ROOT, "data", "recommendations_history.json")


def load_history() -> list:
    """加载推荐历史"""
    if os.path.exists(RECOMMENDATIONS_FILE):
        with open(RECOMMENDATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history: list):
    """保存推荐历史"""
    os.makedirs(os.path.dirname(RECOMMENDATIONS_FILE), exist_ok=True)
    with open(RECOMMENDATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="保存短线推荐记录")
    parser.add_argument("--code", required=True, help="股票代码")
    parser.add_argument("--name", required=True, help="股票名称")
    parser.add_argument("--score", type=float, default=0, help="综合评分")
    parser.add_argument("--price", type=float, default=0, help="推荐时现价")
    parser.add_argument("--sector", default="", help="所属行业")
    parser.add_argument("--trend", default="", help="趋势状态")
    parser.add_argument("--advice", default="", help="操作建议")
    parser.add_argument("--confidence", default="", help="置信度")
    parser.add_argument("--support", default="", help="支撑位")
    parser.add_argument("--resistance", default="", help="压力位")
    parser.add_argument("--stop-loss", default="", help="止损位")
    parser.add_argument("--take-profit", default="", help="止盈位")
    parser.add_argument("--buy-range", default="", help="建议买入价位")
    parser.add_argument("--position", default="", help="建议仓位")
    parser.add_argument("--short-outlook", default="", help="短期展望")
    parser.add_argument("--risk", default="", help="风险提示")
    parser.add_argument("--reason-json", default="", help="推荐逻辑 JSON 文件路径")
    parser.add_argument("--reason-text", default="", help="推荐逻辑文本摘要")
    parser.add_argument("--review-lessons", default="", help="复盘经验总结文本")
    args = parser.parse_args()

    history = load_history()

    # 构建推荐记录
    record = {
        "id": len(history) + 1,
        "code": args.code,
        "name": args.name,
        "recommend_date": datetime.now().strftime("%Y-%m-%d"),
        "recommend_timestamp": datetime.now().isoformat(),
        "score": args.score,
        "price_at_recommend": args.price,
        "sector": args.sector,
        "trend": args.trend,
        "advice": args.advice,
        "confidence": args.confidence,
        "support": args.support,
        "resistance": args.resistance,
        "stop_loss": args.stop_loss,
        "take_profit": args.take_profit,
        "buy_range": args.buy_range,
        "position": args.position,
        "short_outlook": args.short_outlook,
        "risk_warning": args.risk,
        "reason_summary": args.reason_text,
        "review_lessons": args.review_lessons,
        # 复盘结果（后续由 review_recommendations.py 填充）
        "outcome": None,
        "actual_return": None,
        "hit_stop_loss": None,
        "hit_take_profit": None,
        "success": None,
        "review_date": None,
        "days_held": None,
    }

    # 如果提供了推荐逻辑 JSON 文件，读取并合并
    if args.reason_json and os.path.exists(args.reason_json):
        with open(args.reason_json, "r", encoding="utf-8") as f:
            reason_data = json.load(f)
            record["reason_detail"] = reason_data

    history.append(record)
    save_history(history)

    print(f"[OK] 推荐记录已保存: {args.code} {args.name} (ID: {record['id']})")
    print(f"     推荐日期: {record['recommend_date']}, 评分: {args.score}")
    print(f"     历史总计: {len(history)} 条推荐")


if __name__ == "__main__":
    main()
