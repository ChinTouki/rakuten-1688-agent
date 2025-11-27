# core/agent_core.py
from typing import List, Dict, Any
from core.schemas import RakutenDirection, CandidateEval
from tools.rakuten_stub import get_default_directions
from tools.ali1688_stub import search_ali1688_by_cn_keyword
from core.scoring import build_candidate_eval


def jp_to_cn_keywords(jp_keywords: List[str]) -> List[str]:
    """
    v1: 简单写死映射，后面可以交给 LLM 做智能翻译+扩展。
    """
    mapping = {
        "ペット": ["宠物", "宠物用品"],
        "抜け毛 掃除": ["宠物除毛", "宠物粘毛器"],
        "キッチン 収納": ["厨房收纳", "调料收纳"],
        "調味料 ラック": ["调味料架", "厨房调味料架"],
        "生活雑貨": ["生活杂货"],
        "収納 ボックス": ["收纳箱", "收纳盒"],
    }

    cn_keywords = set()
    for jp in jp_keywords:
        for k, v in mapping.items():
            if k in jp:
                cn_keywords.update(v)

    # 如果啥都没匹配上，就粗暴地加一个通用词
    if not cn_keywords:
        cn_keywords.add("日用百货")

    return list(cn_keywords)


def run_selection(
    directions: List[RakutenDirection] = None,
    intl_shipping_jpy: float = 500.0,
    commission_rate: float = 0.15,
    target_margin_rate: float = 0.3,
    cny_to_jpy: float = 22.0,
    per_keyword_limit: int = 10,
) -> Dict[str, List[CandidateEval]]:
    """
    主流程：返回 {grade: [CandidateEval, ...]}
    """
    if directions is None:
        directions = get_default_directions()

    all_evals: List[CandidateEval] = []

    for direction in directions:
        cn_keywords = jp_to_cn_keywords(direction.jp_keywords)
        for cn_kw in cn_keywords:
            products = search_ali1688_by_cn_keyword(cn_kw, limit=per_keyword_limit)
            for p in products:
                ev = build_candidate_eval(
                    product=p,
                    direction_name=direction.name,
                    intl_shipping_jpy=intl_shipping_jpy,
                    commission_rate=commission_rate,
                    target_margin_rate=target_margin_rate,
                    cny_to_jpy=cny_to_jpy,
                )
                all_evals.append(ev)

    # 按档位 & 分数排序
    buckets: Dict[str, List[CandidateEval]] = {"A": [], "B": [], "C": []}
    for ev in all_evals:
        buckets.setdefault(ev.grade, []).append(ev)

    for g in buckets:
        buckets[g].sort(key=lambda x: x.total_score, reverse=True)

    return buckets
