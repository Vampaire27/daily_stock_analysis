#!/usr/bin/env python
"""
短线买点机会筛选器
从候选股票列表中，筛选出最适合短线（10个交易日内）买入的股票。

评分标准：
1. 长期趋势向好（sentiment_score > 50，trend_prediction 看多/强烈看多）
2. 当前处于好买点（operation_advice 买入/加仓，decision_type buy）
3. 短期上涨概率高（short_term_outlook 积极，confidence_level 高/中）

Usage: python scripts/screen_short_term_opportunity.py [--stocks-code-file path] [--max-stocks N]
       或直接传入逗号分隔的股票代码
"""
import argparse
import json
import os
import sys
import time
from typing import List, Optional

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def load_stock_candidates(
    stocks_code: Optional[str] = None,
    stocks_code_file: Optional[str] = None,
) -> List[dict]:
    """加载候选股票"""
    if stocks_code_file:
        with open(stocks_code_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    if stocks_code:
        codes = [c.strip() for c in stocks_code.split(",") if c.strip()]
        return [{"code": c, "name": ""} for c in codes]
    return []


def score_stock(result) -> Optional[dict]:
    """
    对单只分析结果评分，返回评分详情。
    评分维度：
    - 趋势分（40%）：sentiment_score, trend_prediction
    - 买点位（35%）：operation_advice, decision_type
    - 短期概率（25%）：short_term_outlook, confidence_level
    """
    if result is None:
        return None

    score = 0.0
    details = []

    # --- 1. 趋势分（40分）---
    ss = getattr(result, "sentiment_score", 50)
    trend_score = min(ss / 100.0 * 40, 40)
    score += trend_score
    tp = getattr(result, "trend_prediction", "")
    if "强烈看多" in tp:
        score += 5
        details.append(f"趋势强烈看多")
    elif "看多" in tp:
        score += 3
        details.append(f"趋势看多")
    elif "看空" in tp:
        score -= 5
        details.append(f"趋势看空，扣分")

    # --- 2. 买点位置（35分）---
    advice = getattr(result, "operation_advice", "")
    dt = getattr(result, "decision_type", "")
    if "买入" in advice:
        score += 20
        details.append("操作建议买入")
    elif "加仓" in advice:
        score += 15
        details.append("操作建议加仓")
    elif "持有" in advice:
        score += 5
        details.append("操作建议持有")
    elif "卖出" in advice:
        score -= 10
        details.append("操作建议卖出，扣分")
    if dt == "buy":
        score += 10
    elif dt == "sell":
        score -= 5

    # --- 3. 短期上涨概率（25分）---
    outlook = getattr(result, "short_term_outlook", "")
    cl = getattr(result, "confidence_level", "中")
    if cl == "高":
        score += 10
    elif cl == "低":
        score -= 5

    # 检查短期展望是否积极
    positive_words = ["上涨", "反弹", "突破", "走高", "向上", "偏强", "乐观"]
    negative_words = ["下跌", "回调", "调整", "走低", "向下", "偏弱", "谨慎"]
    for w in positive_words:
        if w in outlook:
            score += 5
            break
    for w in negative_words:
        if w in outlook:
            score -= 3
            break

    current_price = getattr(result, "current_price", None)

    return {
        "code": result.code,
        "name": result.name,
        "total_score": round(score, 1),
        "sentiment_score": ss,
        "trend_prediction": tp,
        "operation_advice": advice,
        "decision_type": dt,
        "confidence_level": cl,
        "current_price": current_price,
        "score_details": " | ".join(details),
        "analysis_summary": getattr(result, "analysis_summary", ""),
        "short_term_outlook": outlook,
        "risk_warning": getattr(result, "risk_warning", ""),
    }


def main():
    parser = argparse.ArgumentParser(description="短线买点机会筛选")
    parser.add_argument(
        "--stocks-code",
        type=str,
        default="",
        help="逗号分隔的股票代码",
    )
    parser.add_argument(
        "--stocks-code-file",
        type=str,
        default="",
        help="候选股票 JSON 文件路径",
    )
    parser.add_argument(
        "--max-analyze",
        type=int,
        default=20,
        help="最多分析股票数（控制耗时和API调用）",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="返回排名靠前的股票数",
    )
    args = parser.parse_args()

    candidates = load_stock_candidates(args.stocks_code, args.stocks_code_file)
    if not candidates:
        print("[ERROR] 没有候选股票", file=sys.stderr)
        sys.exit(1)

    candidates = candidates[: args.max_analyze]
    print(f"共 {len(candidates)} 只候选股票，逐一分析中...", file=sys.stderr)

    # 逐一分析
    results = []
    for i, stock in enumerate(candidates):
        code = stock["code"]
        print(f"  [{i+1}/{len(candidates)}] 分析 {code}...", file=sys.stderr)
        try:
            from analyzer_service import analyze_stock

            result = analyze_stock(code, full_report=False)
            if result:
                scored = score_stock(result)
                if scored:
                    results.append(scored)
                    print(f"    评分: {scored['total_score']}, 建议: {scored['operation_advice']}", file=sys.stderr)
            time.sleep(1)  # 避免请求过快
        except Exception as e:
            print(f"    [WARN] 分析 {code} 失败: {e}", file=sys.stderr)

    if not results:
        print("[ERROR] 所有股票分析均失败", file=sys.stderr)
        sys.exit(1)

    # 排序
    results.sort(key=lambda x: x["total_score"], reverse=True)

    # 输出结果
    top = results[: args.top_n]
    print("\n" + "=" * 60, file=sys.stderr)
    print(f"短线买点推荐 Top {args.top_n}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for i, r in enumerate(top):
        print(f"\n#{i+1}: {r['code']} {r['name']}", file=sys.stderr)
        print(f"  评分: {r['total_score']}", file=sys.stderr)
        print(f"  趋势: {r['trend_prediction']} | 建议: {r['operation_advice']}", file=sys.stderr)
        print(f"  现价: {r['current_price']}", file=sys.stderr)
        print(f"  短期展望: {r['short_term_outlook'][:80]}", file=sys.stderr)

    print("\n" + "=" * 60, file=sys.stderr)
    print(json.dumps(top, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
