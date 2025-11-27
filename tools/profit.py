# tools/profit.py
from typing import Tuple


def estimate_cost_and_price_jpy(
    price_cny: float,
    domestic_shipping_cny: float,
    intl_shipping_jpy: float,
    commission_rate: float,
    target_margin_rate: float,
    cny_to_jpy: float,
) -> Tuple[float, float, float]:
    """
    返回: (total_cost_jpy, suggested_price_jpy, margin_rate)
    """
    # 1. 人民币成本全部折算成日元
    base_cost_jpy = (price_cny + domestic_shipping_cny) * cny_to_jpy

    # 2. 加上国际运费
    total_cost_before_fee = base_cost_jpy + intl_shipping_jpy

    # 3. 给平台手续费留出空间：售价的 commission_rate 要覆盖
    # 假设: 售价 * (1 - commission_rate) - total_cost_before_fee = 目标毛利
    #      目标毛利 = target_margin_rate * 售价
    # =>   售价 * (1 - commission_rate - target_margin_rate) = total_cost_before_fee
    denom = 1.0 - commission_rate - target_margin_rate
    if denom <= 0:
        # 目标毛利率太高，按最低可行的方案来
        denom = 1.0 - commission_rate - 0.05  # 至少留5%毛利

    suggested_price_jpy = total_cost_before_fee / denom

    # 实际毛利率
    real_margin = (suggested_price_jpy * (1 - commission_rate) - total_cost_before_fee) / suggested_price_jpy

    return total_cost_before_fee, suggested_price_jpy, real_margin
