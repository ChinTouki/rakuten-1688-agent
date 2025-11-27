# core/scoring.py
from typing import List, Tuple
from core.schemas import Ali1688Product, CandidateEval
from tools.profit import estimate_cost_and_price_jpy


def heuristic_japan_fit(product: Ali1688Product) -> Tuple[float, List[str]]:
    """
    这里只能做简单启发式，真实情况建议结合LLM看标题+图片再打分。
    返回 (得分0-1, 说明列表)
    """
    reasons = []

    score = 0.5  # 基础分

    # 简单示例：标题里有“可爱”“北欧”等字样可加分，你接入LLM后就可以做更聪明的判断
    if any(k in product.title_zh for k in ["收纳", "整理", "宠物", "猫", "狗"]):
        score += 0.2
        reasons.append("功能与日本常见生活场景匹配")

    if product.shop_score and product.shop_score >= 4.7:
        score += 0.1
        reasons.append("供应商评分较高")

    if product.monthly_sales and product.monthly_sales > 100:
        score += 0.1
        reasons.append("销量尚可")

    score = max(0.0, min(1.0, score))
    return score, reasons


def logistic_feasibility(product: Ali1688Product) -> Tuple[float, List[str]]:
    score = 0.7
    reasons = []

    if product.weight_kg and product.weight_kg > 2:
        score -= 0.2
        reasons.append("重量偏大")
    if product.volume_cm3 and product.volume_cm3 > 40000:
        score -= 0.2
        reasons.append("体积偏大")

    score = max(0.0, min(1.0, score))
    return score, reasons


def risk_penalty(product: Ali1688Product) -> Tuple[float, List[str]]:
    penalty = 0.0
    notes = []

    # v1: 简单用标题关键字判断，之后可以交给LLM分析图片+标题
    risky_words = ["迪士尼", "耐克", "阿迪达斯", "LV", "GUCCI", "香奈儿"]
    if any(w in product.title_zh.upper() for w in risky_words):
        penalty += 0.7
        notes.append("疑似IP/仿牌风险")

    # TODO: 可以根据类目、属性进一步判断监管风险

    return penalty, notes


def grade_from_score(score: float, margin_rate: float, penalty: float) -> str:
    if penalty >= 0.7:
        return "C"
    if margin_rate < 0.1:
        return "C"
    if score >= 0.7 and margin_rate >= 0.25:
        return "A"
    if score >= 0.5:
        return "B"
    return "C"


def build_candidate_eval(
    product: Ali1688Product,
    direction_name: str,
    intl_shipping_jpy: float,
    commission_rate: float,
    target_margin_rate: float,
    cny_to_jpy: float,
) -> CandidateEval:
    # 暂时写死国内运费
    domestic_shipping_cny = 5.0

    # 利润相关
    total_cost_jpy, suggested_price_jpy, margin_rate = estimate_cost_and_price_jpy(
        price_cny=product.price_cny,
        domestic_shipping_cny=domestic_shipping_cny,
        intl_shipping_jpy=intl_shipping_jpy,
        commission_rate=commission_rate,
        target_margin_rate=target_margin_rate,
        cny_to_jpy=cny_to_jpy,
    )

    # 日本匹配度
    japan_fit_score, fit_reasons = heuristic_japan_fit(product)

    # 物流
    logistics_score, logistics_reasons = logistic_feasibility(product)

    # 风险
    penalty, risk_notes = risk_penalty(product)

    # 综合
    total_score = 0.4 * japan_fit_score + 0.4 * margin_rate + 0.2 * logistics_score - penalty

    # 档位
    grade = grade_from_score(total_score, margin_rate, penalty)

    # 暂时生成非常简单的日文卖点
    jp_bullets = [
        f"中国工場直送の{direction_name}商品です。",
        "コストパフォーマンスに優れた実用アイテムです。",
    ] + [f"【参考情報】{r}" for r in fit_reasons[:2]]

    return CandidateEval(
        product=product,
        direction_name=direction_name,
        japan_fit_score=japan_fit_score,
        profit_score=margin_rate,
        logistics_score=logistics_score,
        risk_penalty=penalty,
        total_score=total_score,
        margin_rate=margin_rate,
        suggested_price_jpy=round(suggested_price_jpy),
        grade=grade,
        jp_bullets=jp_bullets,
        risk_notes=risk_notes,
    )
