# tools/ali1688_stub.py
"""
1688 选品统一入口（给 agent_core 用）

- 优先走 Onebound 真 1688 搜索（tools.ali1688_api.search_1688_items）
- 出错或返回为空时，自动回退到 DEMO_ITEMS
"""

from typing import List, Dict, Any
import logging

from tools.ali1688_api import search_1688_items, Search1688Error


# 作为兜底的 DEMO 数据（你原来那 3 条）
DEMO_ITEMS: List[Dict[str, Any]] = [
    {
        "id": "p1",
        "title_cn": "宠物除毛刷 北欧风 软硅胶",
        "price_cny": 12,
        "score": 0.8,
    },
    {
        "id": "p2",
        "title_cn": "厨房调料收纳架 多层 收纳",
        "price_cny": 18,
        "score": 0.8,
    },
    {
        "id": "p3",
        "title_cn": "七彩发光耳机 炫酷 电竞",
        "price_cny": 25,
        "score": 0.4,
    },
]


def _filter_demo(
    min_price_cny: float,
    max_price_cny: float,
    max_items: int,
) -> List[Dict[str, Any]]:
    """在 DEMO_ITEMS 里按价格区间筛一筛，顺便按 score 排个序。"""
    items = [
        it
        for it in DEMO_ITEMS
        if min_price_cny <= it.get("price_cny", 0.0) <= max_price_cny
    ]
    items.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return items[:max_items]


def search_ali1688_by_cn_keyword(
    keyword: str,
    min_price_cny: float,
    max_price_cny: float,
    max_items: int = 20,
) -> List[Dict[str, Any]]:
    """
    *给 agent_core 用的统一函数*

    策略：
    1. 尝试调用 Onebound 真实 1688 搜索；
    2. 如果调用失败（网络 / 权限 / JSON 格式等）或结果为空，
       自动回退到本地 DEMO_ITEMS，保证前端永远有内容可展示。
    """
    # 先尝试真实 1688 搜索
    try:
        real_items = search_1688_items(
            keyword=keyword,
            min_price_cny=min_price_cny,
            max_price_cny=max_price_cny,
            max_items=max_items,
        )
        if real_items:
            return real_items

        logging.warning(
            "[1688] Onebound 搜索返回空列表，使用 DEMO 数据。 keyword=%s",
            keyword,
        )
    except Search1688Error as e:
        logging.warning(
            "[1688] Onebound 搜索失败（业务错误），使用 DEMO 数据。 keyword=%s, err=%s",
            keyword,
            e,
        )
    except Exception as e:
        logging.exception(
            "[1688] Onebound 搜索异常（非预期错误），使用 DEMO 数据。 keyword=%s, err=%s",
            keyword,
            e,
        )

    # 降级：使用 DEMO 数据
    return _filter_demo(min_price_cny, max_price_cny, max_items)
