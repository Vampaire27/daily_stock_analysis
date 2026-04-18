#!/usr/bin/env python
"""
获取热门行业板块的成分股列表

降级策略：
1. 优先尝试通过 akshare 获取实时板块成分股
2. 如果网络被封，使用内置的行业龙头/热门股列表
Usage: python scripts/get_hot_sector_stocks.py [--target-sectors AI,电力,半导体]
"""
import argparse
import json
import sys

# 默认关注的长线向好行业（概念板块关键词）
DEFAULT_SECTOR_KEYWORDS = [
    # AI / 人工智能产业链
    "人工智能", "AIGC", "AI芯片", "算力", "CPO", "光模块",
    # 半导体 / 芯片
    "半导体", "芯片", "存储芯片",
    # 电力 / 新能源
    "电力", "光伏", "储能", "核电", "特高压",
    # 其他长线向好
    "机器人", "消费电子",
]


# 内置行业龙头/热门股（当网络 API 不可用时的降级方案）
# 按行业分类，覆盖 AI、半导体、电力、新能源、机器人等主要长线向好行业
CURATED_STOCKS = {
    # AI / 算力
    "AI算力": [
        {"code": "300750", "name": "宁德时代"},
        {"code": "688981", "name": "中芯国际"},
        {"code": "002230", "name": "科大讯飞"},
        {"code": "688041", "name": "海光信息"},
        {"code": "300308", "name": "中际旭创"},
        {"code": "688256", "name": "寒武纪"},
        {"code": "002415", "name": "海康威视"},
        {"code": "300502", "name": "新易盛"},
    ],
    # 半导体
    "半导体": [
        {"code": "688981", "name": "中芯国际"},
        {"code": "688041", "name": "海光信息"},
        {"code": "688256", "name": "寒武纪"},
        {"code": "603501", "name": "韦尔股份"},
        {"code": "002371", "name": "北方华创"},
        {"code": "688126", "name": "沪硅产业"},
        {"code": "688396", "name": "华润微"},
    ],
    # 电力
    "电力": [
        {"code": "601985", "name": "中国核电"},
        {"code": "600900", "name": "长江电力"},
        {"code": "600011", "name": "华能国际"},
        {"code": "600027", "name": "华电国际"},
        {"code": "601991", "name": "大唐发电"},
        {"code": "000539", "name": "粤电力A"},
        {"code": "600886", "name": "国投电力"},
    ],
    # 光伏 / 储能
    "光伏储能": [
        {"code": "002594", "name": "比亚迪"},
        {"code": "300274", "name": "阳光电源"},
        {"code": "601012", "name": "隆基绿能"},
        {"code": "002129", "name": "TCL中环"},
        {"code": "600438", "name": "通威股份"},
        {"code": "300014", "name": "亿纬锂能"},
        {"code": "002459", "name": "晶澳科技"},
    ],
    # 机器人 / 智能汽车
    "机器人": [
        {"code": "002456", "name": "欧菲光"},
        {"code": "300124", "name": "汇川技术"},
        {"code": "002747", "name": "埃斯顿"},
        {"code": "603680", "name": "今创集团"},
        {"code": "688169", "name": "石头科技"},
    ],
    # 消费电子
    "消费电子": [
        {"code": "002475", "name": "立讯精密"},
        {"code": "002241", "name": "歌尔股份"},
        {"code": "601138", "name": "工业富联"},
        {"code": "002456", "name": "欧菲光"},
        {"code": "600745", "name": "闻泰科技"},
    ],
}


def get_sector_stocks_via_akshare(sector_name: str) -> list[dict]:
    """通过 akshare 获取指定概念板块的成分股"""
    try:
        import akshare as ak
        df = ak.stock_board_concept_cons_em(symbol=sector_name)
        if df is not None and not df.empty:
            return [
                {"code": str(row["代码"]).zfill(6), "name": str(row["名称"])}
                for _, row in df.iterrows()
            ]
    except Exception as e:
        print(f"  [WARN] akshare 获取板块 '{sector_name}' 成分股失败: {e}", file=sys.stderr)
    return []


def find_matching_sectors_via_akshare(keywords: list[str], top_n: int = 15) -> list[str]:
    """通过 akshare 从概念板块列表中匹配目标行业"""
    try:
        import akshare as ak
        all_boards = ak.stock_board_concept_name_em()
        if all_boards is None or all_boards.empty:
            return []
        all_names = list(all_boards["板块名称"])
        matched = []
        for kw in keywords:
            for name in all_names:
                if kw in name:
                    matched.append(name)
        return list(dict.fromkeys(matched))[:top_n]
    except Exception as e:
        print(f"  [WARN] akshare 获取板块列表失败: {e}", file=sys.stderr)
        return []


def get_curated_stocks(sector_keywords: list[str], max_stocks: int = 80) -> list[dict]:
    """从内置股票池中筛选"""
    all_stocks = {}
    # 根据关键词匹配行业
    matched_categories = set()
    for kw in sector_keywords:
        for cat in CURATED_STOCKS:
            if kw in cat or any(kw == w for w in ["AI", "算力", "芯片", "半导体", "电力", "光伏", "储能", "机器人"]):
                matched_categories.add(cat)
                break

    # 如果没有匹配到，使用全部类别
    if not matched_categories:
        matched_categories = set(CURATED_STOCKS.keys())

    print(f"  匹配到行业类别: {', '.join(matched_categories)}", file=sys.stderr)
    print("  使用内置行业龙头股票列表（网络 API 不可用）", file=sys.stderr)

    for cat in matched_categories:
        for s in CURATED_STOCKS.get(cat, []):
            all_stocks[s["code"]] = s
        if len(all_stocks) >= max_stocks:
            break

    return list(all_stocks.values())[:max_stocks]


def main():
    parser = argparse.ArgumentParser(description="获取热门行业板块的成分股")
    parser.add_argument(
        "--target-sectors",
        type=str,
        default="",
        help="逗号分隔的目标板块关键词，默认使用内置列表",
    )
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=80,
        help="最多返回股票数（去重后）",
    )
    args = parser.parse_args()

    if args.target_sectors:
        keywords = [k.strip() for k in args.target_sectors.split(",") if k.strip()]
    else:
        keywords = DEFAULT_SECTOR_KEYWORDS

    # 尝试 akshare 实时获取
    print("[1/3] 尝试通过 akshare 获取板块数据...", file=sys.stderr)
    sectors = find_matching_sectors_via_akshare(keywords)

    if sectors:
        print(f"  匹配到 {len(sectors)} 个板块: {', '.join(sectors[:5])}...", file=sys.stderr)
        all_stocks = {}
        for i, sector in enumerate(sectors):
            print(f"[2/3] 获取板块 '{sector}' 成分股 ({i+1}/{len(sectors)})...", file=sys.stderr)
            stocks = get_sector_stocks_via_akshare(sector)
            for s in stocks:
                all_stocks[s["code"]] = s
            if len(all_stocks) >= args.max_stocks:
                break
        stocks_list = list(all_stocks.values())[:args.max_stocks]
        print(f"[3/3] 共 {len(stocks_list)} 只候选股票（通过 akshare 获取）", file=sys.stderr)
    else:
        # 降级到内置列表
        print("  akshare 不可用，使用内置行业龙头列表", file=sys.stderr)
        stocks_list = get_curated_stocks(keywords, max_stocks=args.max_stocks)

    if not stocks_list:
        print("[ERROR] 没有候选股票", file=sys.stderr)
        sys.exit(1)

    # 输出 JSON
    print(json.dumps(stocks_list, ensure_ascii=False))


if __name__ == "__main__":
    main()
