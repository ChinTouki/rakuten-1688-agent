from typing import List, Dict, Any


# 一些“日本市场热门类目”的假数据（乐天 + 亚马逊混在一起的 stub）
# 以后你可以用真实排行榜替换这里。
_ALL_CATEGORY_CANDIDATES: List[Dict[str, Any]] = [
    {
        "source": "rakuten",
        "jp_category": "収納・整理グッズ（インテリア・寝具・収納）",
        "scene": "家の省スペース化・片付け需要",
        "trend_reason": "楽天の住まい・暮らし／インテリア系ランキングで常に上位。共働き・子育て世代の『とりあえず収納したい』ニーズが強い。",
        "suggested_1688_keywords": ["收纳盒", "收纳篮", "抽屉收纳", "墙挂收纳"],
        "risk_level": "low",
        "risk_notes": "サイズ・重量に注意。大型家具は送料と破損リスクが高いため避ける。",
    },
    {
        "source": "rakuten",
        "jp_category": "キッチン用品・小型調理グッズ",
        "scene": "時短料理・お弁当・在宅ごはん需要",
        "trend_reason": "楽天ランキングでキッチンツール系はレビュー数が多く、買い替えサイクルも短い。",
        "suggested_1688_keywords": ["厨房小工具", "厨房收纳", "便当盒", "料理模具"],
        "risk_level": "low",
        "risk_notes": "食品衛生法対応（食品接触材質）に注意。できるだけ素材表示が明確な商品を選ぶ。",
    },
    {
        "source": "rakuten",
        "jp_category": "ペット用品（ケア・おもちゃ）",
        "scene": "少子高齢化＋ペット家族化で継続需要",
        "trend_reason": "グローバルでもペット用品は成長カテゴリ。楽天でもペットジャンルが安定して強い。",
        "suggested_1688_keywords": ["宠物梳", "宠物玩具", "宠物窝", "猫抓板"],
        "risk_level": "mid",
        "risk_notes": "ペットフード・サプリは規制が重いので避ける。ブラシ・おもちゃ・服など非食品に絞る。",
    },
    {
        "source": "amazon",
        "jp_category": "Amazon｜PC・周辺機器（USBハブ・ドッキングステーション）",
        "scene": "在宅ワーク・ゲーミング・マルチモニター需要",
        "trend_reason": "Amazon.co.jp で常に売れ筋上位に入る PC 周辺小物。単価も手頃で買い替えサイクルが短い。",
        "suggested_1688_keywords": ["usb 集线器", "type-c 扩展坞", "hdmi 转接线"],
        "risk_level": "low",
        "risk_notes": "PSE 対象となる AC アダプタ内蔵製品は慎重に。まずはバスパワーの USB ハブやケーブル中心。",
    },
    {
        "source": "amazon",
        "jp_category": "Amazon｜スマホアクセサリ（保護フィルム・ケース）",
        "scene": "スマホ買い替え・機種変更需要＋消耗品需要",
        "trend_reason": "スマホ周辺は Amazon での購入比率が高く、iPhone/Android 新機種ごとに波が来る定番カテゴリ。",
        "suggested_1688_keywords": ["手机 壳", "钢化膜", "手机 支架"],
        "risk_level": "low",
        "risk_notes": "機種対応のミスに注意。まずは汎用タイプや人気機種に絞る。",
    },
    {
        "source": "amazon",
        "jp_category": "Amazon｜オフィス・文房具（ノート・ペン・整理グッズ）",
        "scene": "在宅ワーク・勉強用のロングテール消耗品",
        "trend_reason": "ノート・ペン・デスク整理グッズは Amazon でレビュー数が多く、リピート性が高い。",
        "suggested_1688_keywords": ["笔记本 文具", "中性笔", "桌面 收纳 办公"],
        "risk_level": "low",
        "risk_notes": "ブランド模倣品は避ける。無地・シンプルデザインの OEM っぽいものが安全。",
    },
]


def get_jp_trending_categories(ms_req) -> List[Dict[str, Any]]:
    """
    app.py から呼ばれる「日本市场热门类目」 stub。

    ms_req 是一个有 attributes 的对象（MarketSuggestRequest）：
      - ms_req.budget_level: "low"/"mid"/"high"
      - ms_req.avoid_keywords: List[str]
      - ms_req.top_k: int
      - ms_req.market_sources: Optional[List[str]]（例如 ["rakuten","amazon"]）

    这里完全是 stub：
      - 简单按 market_sources / 避开关键词 / top_k 做筛选
      - 预算目前先不参与过滤，将来你可以按预算把类目再分级
    """
    budget_level = getattr(ms_req, "budget_level", "low")
    avoid_keywords = getattr(ms_req, "avoid_keywords", []) or []
    top_k = getattr(ms_req, "top_k", 5)
    market_sources = getattr(ms_req, "market_sources", None) or ["rakuten", "amazon"]

    # 1) 先按来源过滤（rakuten / amazon）
    candidates = [
        c
        for c in _ALL_CATEGORY_CANDIDATES
        if c.get("source") in market_sources
    ]

    # 2) 按避开关键词过滤（如果 jp_category 里包含任意一个避开词，就剔除）
    if avoid_keywords:
        def _hit_avoid(cat: Dict[str, Any]) -> bool:
            name = cat.get("jp_category", "")
            return any(kw and (kw in name) for kw in avoid_keywords)

        candidates = [c for c in candidates if not _hit_avoid(c)]

    # 3) 预算目前不细分，先按原始顺序截断 top_k
    #    （你以后可以根据 budget_level 做排序或不同列表）
    return candidates[:top_k]
