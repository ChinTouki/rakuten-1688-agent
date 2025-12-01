# core/schemas.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from typing import Optional, List
from pydantic import BaseModel

# ...（这里是你原有的 schema 定义）...


class Ali1688UrlParseRequest(BaseModel):
    """前端贴一个 1688 商品 URL 过来"""
    url: str


class Ali1688ParsedItem(BaseModel):
    """从 1688 网页解析出来的结构化商品信息"""
    url: str
    title_cn: Optional[str] = None
    price_cny: Optional[float] = None
    images: List[str] = []
    # 方便后面做 debug / 更复杂解析，可选保留一小段 HTML
    raw_html_snippet: Optional[str] = None


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
