# tools/ali1688_api.py
"""
Onebound 1688 API 适配层

统一在这里调用 Onebound 的 1688 搜索接口，把返回数据转换成
内部统一使用的格式：
    [
        {
            "id": str,          # 商品 ID
            "title_cn": str,    # 中文标题
            "price_cny": float, # 价格（CNY）
            "score": float,     # 一个简单评分（后续可用销量/热度调整）
        },
        ...
    ]
"""

from typing import List, Dict, Any
import os
import requests


ONEBOUND_API_HOST = os.getenv("ONEBOUND_API_HOST", "https://api.onebound.cn")
ONEBOUND_API_KEY = os.getenv("ONEBOUND_API_KEY", "").strip()
ONEBOUND_TIMEOUT = float(os.getenv("ONEBOUND_TIMEOUT", "10.0"))  # 秒


class Search1688Error(Exception):
    """对外统一抛这个异常，让上层决定如何降级处理。"""
    pass


def _ensure_key():
    if not ONEBOUND_API_KEY:
        raise Search1688Error("ONEBOUND_API_KEY 未设置，请在 .env 中配置你的 Onebound key。")


def search_1688_items(
    keyword: str,
    min_price_cny: float,
    max_price_cny: float,
    max_items: int = 20,
) -> List[Dict[str, Any]]:
    """
    通过 Onebound 调用 1688 搜索接口。

    注意：
    - 具体参数名（q / keyword / price_min / price_max 等）要以 Onebound 文档为准。
      这里给出的是一个常见的参数形式，如果不匹配可以微调。
    """
    _ensure_key()

    params = {
        "key": ONEBOUND_API_KEY,
        "q": keyword,
        "page": 1,
        "page_size": max_items,
        # 下面这些参数名根据你实际使用的 Onebound 文档调整：
        "min_price": min_price_cny,
        "max_price": max_price_cny,
        # "cid": "",  # 如需按类目过滤，可在这里追加
    }

    try:
        resp = requests.get(
            f"{ONEBOUND_API_HOST}/1688/item_search",
            params=params,
            timeout=ONEBOUND_TIMEOUT,
        )
    except requests.RequestException as e:
        raise Search1688Error(f"调用 Onebound 失败（网络问题）：{e}") from e

    if resp.status_code != 200:
        raise Search1688Error(f"Onebound HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except Exception as e:
        raise Search1688Error(f"Onebound 返回内容不是合法 JSON：{e}") from e

    # 根据 Onebound 的标准结构进行判断
    # 你之前看到的错误 JSON 大致是：
    # {
    #   "error": "...",
    #   "reason": "...",
    #   "error_code": "4005",
    #   "success": 0,
    #   ...
    # }
    success = data.get("success")
    if not success:
        reason = data.get("reason") or data.get("error") or "unknown error"
        code = data.get("error_code") or "N/A"
        raise Search1688Error(f"Onebound 返回错误（code={code}）：{reason}")

    # 正常情况下，结构大致类似：
    # {
    #   "items": {
    #       "item": [
    #           {
    #               "item_id": "...",
    #               "title": "...",
    #               "price": "12.50",
    #               ...
    #           },
    #           ...
    #       ]
    #   },
    #   ...
    # }
    items_raw = []
    items_block = data.get("items") or {}
    if isinstance(items_block, dict):
        items_raw = items_block.get("item") or []
    elif isinstance(items_block, list):
        # 有些第三方会直接把 item 列表放在 items 里
        items_raw = items_block
    else:
        items_raw = []

    normalized: List[Dict[str, Any]] = []
    for it in items_raw:
        if not isinstance(it, dict):
            continue
        try:
            item_id = str(
                it.get("item_id")
                or it.get("num_iid")
                or it.get("offer_id")
                or ""
            )
            title = str(it.get("title") or "")
            price_raw = it.get("price")
            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                price = 0.0

            # 简单给一个 score，后面你可以根据销量、收藏数等做更复杂打分
            score = 0.5

            normalized.append(
                {
                    "id": item_id,
                    "title_cn": title,
                    "price_cny": price,
                    "score": score,
                }
            )
        except Exception:
            # 单条有问题就跳过，不影响整体
            continue

    return normalized
