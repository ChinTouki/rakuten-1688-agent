# tools/ali1688_stub.py
"""
原本这里只是假的 3 个商品 demo。
现在改成对接真实 1688 搜索 API（通过 ali1688_api）。
对外保留原来的函数名 search_ali1688_by_cn_keyword，让其它代码不需要修改。
"""

from typing import List, Dict, Any, Optional
import logging

from tools.ali1688_api import search_1688_items, Search1688Error

logger = logging.getLogger(__name__)


def search_ali1688_by_cn_keyword(
    keyword: str,
    max_items: int = 30,
    min_price_cny: Optional[float] = None,
    max_price_cny: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    按中文关键字搜索 1688 商品（真实 API）。
    保持和旧 stub 一样的接口签名，方便 agent 直接调用。

    返回的每个 item 统一结构：
    {
        "id": str,
        "title_cn": str,
        "price_cny": float,
        "pic_url": str | None,
        "detail_url": str | None,
        "sales": int | None,
        "score": float,  # 简单打分（这里用销量当 score，占位）
    }
    """
    try:
        items = search_1688_items(
            keyword=keyword,
            max_items=max_items,
            min_price_cny=min_price_cny,
            max_price_cny=max_price_cny,
        )
    except Search1688Error as e:
        logger.error("1688 検索に失敗しました（stub fallback 使用）: %s", e)

        # 如果你想“失败时至少还能看到 3 个 demo”，在这里放回旧的假数据；
        # 如果你想“失败就抛错”，可以改成 raise。
        return [
            {
                "id": "demo1",
                "title_cn": "【fallback】宠物除毛刷 北欧风 软硅胶",
                "price_cny": 12.0,
                "pic_url": None,
                "detail_url": None,
                "sales": 0,
                "score": 0.0,
            },
            {
                "id": "demo2",
                "title_cn": "【fallback】厨房调料收纳架 多层 收纳",
                "price_cny": 18.0,
                "pic_url": None,
                "detail_url": None,
                "sales": 0,
                "score": 0.0,
            },
            {
                "id": "demo3",
                "title_cn": "【fallback】七彩发光耳机 炫酷 电竞",
                "price_cny": 25.0,
                "pic_url": None,
                "detail_url": None,
                "sales": 0,
                "score": 0.0,
            },
        ]

    # 给每个 item 加一个简单的 score 字段，方便后面排序 / 过滤用
    for it in items:
        sales = it.get("sales") or 0
        try:
            sales_val = float(sales)
        except Exception:
            sales_val = 0.0
        it["score"] = sales_val

    return items
