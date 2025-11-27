# core/schemas.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class RakutenDirection:
    """日本侧的选品方向（一个大致类目/关键词）"""
    name: str                    # 例如 "宠物用品"
    jp_keywords: List[str]       # 例如 ["ペット", "抜け毛 掃除"]


@dataclass
class Ali1688Product:
    """1688 返回的商品基本信息"""
    offer_id: str
    title_zh: str
    price_cny: float
    min_order_qty: int
    shop_name: str
    shop_score: Optional[float] = None
    monthly_sales: Optional[int] = None
    thumb_url: Optional[str] = None
    attrs: Dict[str, str] = field(default_factory=dict)
    weight_kg: Optional[float] = None
    volume_cm3: Optional[float] = None


@dataclass
class CandidateEval:
    """经过Agent评估后的候选商品"""
    product: Ali1688Product
    direction_name: str
    japan_fit_score: float
    profit_score: float
    logistics_score: float
    risk_penalty: float
    total_score: float
    margin_rate: float
    suggested_price_jpy: float
    grade: str  # "A" / "B" / "C"
    jp_bullets: List[str]
    risk_notes: List[str]
