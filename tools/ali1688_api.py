import os
import logging
import json
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

ONEBOUND_API_KEY = os.getenv("ONEBOUND_API_KEY")
ONEBOUND_API_SECRET = os.getenv("ONEBOUND_API_SECRET")

ONEBOUND_1688_BASE_URL = os.getenv(
    "ONEBOUND_1688_BASE_URL",
    "https://api-gw.onebound.cn/1688/item_search/",
)


class Search1688Error(Exception):
    """1688 搜索异常"""
    pass


def _build_1688_params(
    keyword: str,
    page: int,
    page_size: int,
    min_price_cny: Optional[float],
    max_price_cny: Optional[float],
) -> Dict[str, Any]:
    """
    构造调用 onebound 1688.item_search 的参数。
    """
    if not ONEBOUND_API_KEY or not ONEBOUND_API_SECRET:
        raise Search1688Error("ONEBOUND_API_KEY / ONEBOUND_API_SECRET 未配置")

    params: Dict[str, Any] = {
        "key": ONEBOUND_API_KEY,
        "secret": ONEBOUND_API_SECRET,
        "api_name": "item_search",
        "q": keyword,
        "page": page,
        "page_size": page_size,
        "result_type": "json",
        "lang": "cn",
        "sort": "_sale",
    }

    if min_price_cny is not None:
        params["start_price"] = min_price_cny
    if max_price_cny is not None:
        params["end_price"] = max_price_cny

    return params


def search_1688_items(
    keyword: str,
    max_items: int = 30,
    min_price_cny: Optional[float] = None,
    max_price_cny: Optional[float] = None,
    page: int = 1,
) -> List[Dict[str, Any]]:
    """
    调用 1688 搜索 API，返回统一结构的商品列表。
    """
    params = _build_1688_params(
        keyword=keyword,
        page=page,
        page_size=max_items,
        min_price_cny=min_price_cny,
        max_price_cny=max_price_cny,
    )

    try:
        resp = requests.get(ONEBOUND_1688_BASE_URL, params=params, timeout=10)

        # 调试输出：看真实请求和返回
        print("DEBUG 1688 status:", resp.status_code)
        print("DEBUG 1688 url:", resp.url)
        try:
            text = resp.text
            print("DEBUG 1688 body:", text[:800])  # 只打印前 800 字符
        except Exception:
            pass

        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.exception("调用 1688 API 失败: %s", e)
        raise Search1688Error(f"调用 1688 API 失败: {e}")

    # 看一下顶层 keys
    try:
        print("DEBUG 1688 data keys:", list(data.keys()))
    except Exception:
        print("DEBUG 1688 data not a dict:", type(data))

    # 默认按 onebound 的结构解析：data["items"]["item"]
    items_root = data.get("items") or {}
    raw_items = items_root.get("item") or []

    results: List[Dict[str, Any]] = []
    for it in raw_items[:max_items]:
        _id = (
            it.get("num_iid")
            or it.get("offerid")
            or it.get("id")
            or it.get("item_id")
            or ""
        )
        title = it.get("title") or it.get("subject") or ""
        price_str = it.get("price") or it.get("org_price") or "0"
        try:
            price = float(price_str)
        except Exception:
            price = 0.0

        results.append(
            {
                "id": str(_id),
                "title_cn": title,
                "price_cny": price,
                "pic_url": it.get("pic_url") or it.get("image") or it.get("img"),
                "detail_url": it.get("detail_url") or it.get("url"),
                "sales": int(it.get("sales") or it.get("volume") or 0),
            }
        )

    return results
