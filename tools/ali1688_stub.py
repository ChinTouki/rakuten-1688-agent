# tools/rakuten_stub.py
from typing import List
from core.schemas import RakutenDirection


def get_default_directions() -> List[RakutenDirection]:
    """v1 先写死几个方向，后面再接乐天API"""
    return [
        RakutenDirection(
            name="宠物用品",
            jp_keywords=["ペット", "犬 猫 抜け毛 掃除"]
        ),
        RakutenDirection(
            name="厨房收纳",
            jp_keywords=["キッチン 収納", "調味料 ラック"]
        ),
        RakutenDirection(
            name="生活杂货",
            jp_keywords=["生活雑貨", "収納 ボックス"]
        ),
    ]
# tools/ali1688_stub.py
from typing import List
from core.schemas import Ali1688Product


def search_ali1688_by_cn_keyword(keyword_zh: str, limit: int = 10) -> List[Ali1688Product]:
    """
    v1: 先用假数据，等你接入1688 OpenAPI后替换这里。
    """
    # TODO: 替换成真实的 1688 API 调用
    dummy = [
        Ali1688Product(
            offer_id=f"dummy_{keyword_zh}_{i}",
            title_zh=f"{keyword_zh} 示例商品{i}",
            price_cny=10 + i,
            min_order_qty=2,
            shop_name="示例供应商",
            shop_score=4.8,
            monthly_sales=100 + i * 5,
        )
        for i in range(limit)
    ]
    return dummy
