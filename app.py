import os
import csv
import json
import logging
logger = logging.getLogger("uvicorn.error") 
from io import StringIO
from typing import List, Optional

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse


from pydantic import BaseModel

import requests
from bs4 import BeautifulSoup
import openai

# 你项目里用到的内部模块（按你实际有的为准）
from core.schemas import Ali1688UrlParseRequest, Ali1688ParsedItem

from tools.ali1688_url_parser import parse_1688_url, Ali1688UrlParseError
from tools.ali1688_stub import search_ali1688_by_cn_keyword
from tools.ali1688_url_parser import parse_1688_url, Ali1688UrlParseError


# 读取 .env
load_dotenv()

# ========= OpenAI & 访问密码 =========

# 从环境变量读取 OpenAI Key（你已经在 .env 里配了 OPENAI_API_KEY）
openai.api_key = os.getenv("OPENAI_API_KEY", "")
logger.info("OPENAI_API_KEY length at startup: %d", len(openai.api_key or ""))

# 从环境变量读取访问密码（token），前端用 X-Agent-Token 传
AGENT_ACCESS_TOKEN = os.getenv("AGENT_ACCESS_TOKEN", "").strip()
logger.info("AGENT_ACCESS_TOKEN length at startup: %d", len(AGENT_ACCESS_TOKEN))


# ========= FastAPI 实例 & 静态文件 =========

app = FastAPI(title="Rakuten-1688 Selection Agent v1")

# CORS（方便你在本机 / Render 上用浏览器访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 如果以后要限制域名，可以改成具体列表
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 前端静态文件挂载（/ui/ → frontend 目录）
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")



@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """
    浏览器请求 /favicon.ico 时返回图标。
    没有的话就返回 404，不影响其他功能。
    """
    icon_path = os.path.join("frontend", "icon-192.png")
    if os.path.exists(icon_path):
        return FileResponse(icon_path)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})





def verify_token(
    x_agent_token: Optional[str] = Header(
        default=None,
        alias="X-Agent-Token",
    )
):
    """
    简单访问控制：
      - 如果环境变量 AGENT_ACCESS_TOKEN 没配置：不校验（方便本地开发）
      - 如果配置了：要求请求头 X-Agent-Token 完全一致
    """
    if not AGENT_ACCESS_TOKEN:
        # 没配置就相当于不启用保护
        logger.warning("AGENT_ACCESS_TOKEN is empty; skip auth check")
        return

    # 打印一下收到的 header 和 env 的长度（不会把密码内容输出，只输出 repr 和长度）
    logger.info(
        "verify_token: header=%r (len=%d), env_len=%d",
        x_agent_token,
        len(x_agent_token or ""),
        len(AGENT_ACCESS_TOKEN),
    )

    if x_agent_token != AGENT_ACCESS_TOKEN:
        logger.warning("verify_token: token mismatch")
        raise HTTPException(status_code=401, detail="Unauthorized")

    logger.info("verify_token: token OK")



@app.get("/auth/check", dependencies=[Depends(verify_token)])
def auth_check():
    """
    用于前端在密码弹窗中即时验证 token 是否正确。
    - 正确：返回 {"ok": True}
    - 错误：verify_token 会直接抛 401，前端会显示“パスワードが正しくありません。”
    """
    return {"ok": True}




class MarketAutoSelectRequest(BaseModel):
    """
    /market_auto_select & /market_auto_select_csv 用的请求体：
    - budget_level: 预算强度
    - avoid_keywords: 想避开的类目（前端输入框会传过来）
    - top_k_categories: 推荐几个类目
    - max_items_per_category: 每个类目最多抓几个 1688 商品
    - min_price_cny / max_price_cny: 1688 采购价区间
    """
    budget_level: str = "low"
    avoid_keywords: List[str] = []
    top_k_categories: int = 5
    max_items_per_category: int = 30
    min_price_cny: float = 5.0
    max_price_cny: float = 40.0




class SelectionRequest(BaseModel):
    directions: List[str] = []
    min_price_cny: float = 5.0
    max_price_cny: float = 30.0
    # 人民币兑日元汇率（粗略）
    cny_to_jpy: float = 22.0
    # 平均每件国际运费（日元，先粗略给个值）
    intl_shipping_jpy: float = 500.0
    # 乐天平台综合费率（佣金+系统费等，粗略）
    commission_rate: float = 0.15

class AutoSelectRequest(BaseModel):
    # 你输入的类目，可以是「宠物」「厨房收纳」之类，先当做中文关键词
    category: str
    # 每次最多从1688抓多少个候选
    max_items: int = 20
    # 价格过滤条件（人民币）
    min_price_cny: float = 0.0
    max_price_cny: float = 9999.0


class MarketSuggestRequest(BaseModel):
    budget_level: str = "low"
    avoid_keywords: List[str] = []
    top_k: int = 5
    market_sources: List[str] = ["rakuten"]  # 新增: ["rakuten"], ["amazon"], ["rakuten","amazon"]


class ProfitSimItem(BaseModel):
    product_id: str
    title_cn: str
    cost_cny: float          # 1688 进货价
    shipping_cny: float = 0  # 从 1688 到日本的单位运费（可以估算）
    sell_price_jpy: float    # 计划在乐天的含税售价
    other_fee_jpy: float = 0 # 其它固定成本：包装、仓库处理等（可选）


class ProfitSimRequest(BaseModel):
    fx_rate: float = 21.0         # 汇率：1元人民币≈多少日元（先手动输入）
    rakuten_fee_rate: float = 0.15  # 乐天综合手续费（平台+支付+其他），先用15%估算
    items: List[ProfitSimItem]

class ListingCopyRequest(BaseModel):
    title_cn: str
    desc_cn: Optional[str] = ""
    keywords_jp: List[str] = []
    shop_tone: str = "シンプル"





# 先用几条假数据模拟1688返回的商品列表
DUMMY_1688_PRODUCTS = [
    {
        "id": "p1",
        "title_cn": "宠物除毛刷 北欧风 软硅胶",
        "price_cny": 12.0,
        "tags": ["宠物", "除毛", "家用"],
    },
    {
        "id": "p2",
        "title_cn": "厨房调料收纳架 多层 收纳",
        "price_cny": 18.0,
        "tags": ["厨房", "收纳"],
    },
    {
        "id": "p3",
        "title_cn": "七彩发光耳机 炫酷 电竞",
        "price_cny": 25.0,
        "tags": ["发光", "电竞"],
    },
]

CSV_PATH = "1688_products.csv"

def load_products_from_csv():
    """
    从本地 1688_products.csv 读取真实商品列表。
    文件不存在或为空时，退回 DUMMY_1688_PRODUCTS。
    """
    if not os.path.exists(CSV_PATH):
        return DUMMY_1688_PRODUCTS

    products = []
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 价格
            raw_price = (row.get("price_cny") or "").strip()
            try:
                price = float(raw_price) if raw_price else 0.0
            except ValueError:
                price = 0.0

            # tags: 用逗号分隔
            raw_tags = row.get("tags") or ""
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

            products.append(
                {
                    "id": row.get("id") or "",
                    "title_cn": row.get("title_cn") or "",
                    "price_cny": price,
                    "tags": tags,
                }
            )

    # 如果文件里没读到任何有效行，退回 DUMMY
    if not products:
        return DUMMY_1688_PRODUCTS

    return products

def search_1688_stub(category: str, max_items: int = 20):
    """
    1688 搜索的占位函数（stub）。

    现在用本地假数据 + 简单过滤模拟：
    - 将来你可以把这里改成调用 1688 正式 API 或爬虫，
      只要返回的列表结构保持一致：[{id, title_cn, price_cny, tags}, ...]
    """
    # 这里简单用 DUMMY_1688_PRODUCTS 模拟：按类目关键字筛一筛
    results = []
    for p in DUMMY_1688_PRODUCTS:
        title = p["title_cn"]
        if category in title:
            results.append(p)

    # 如果没有命中，就先退回全量（防止列表为空不好测试）
    if not results:
        results = DUMMY_1688_PRODUCTS.copy()

    # 截断到 max_items
    return results[:max_items]


def get_jp_trending_categories_stub() -> List[dict]:
    """
    基于 2025 年日本（特别是楽天）公开的趋势信息，手工整理的一版类目推荐。
    将来你可以把这里改成：
      - 调用楽天ランキング页面 / API 做实时抓取
      - 或者用 LLM + WebSearch 来动态更新
    """
    categories = [
        {
            "jp_category": "収納・整理グッズ（インテリア・寝具・収納）",
            "scene": "家の省スペース化・片付け需要",
            "trend_reason": "楽天の住まい・暮らし／インテリア系ランキングで常に上位。共働き・子育て世代の『とりあえず収納したい』ニーズが強い。",
            "suitable_for_1688": True,
            "risk_level": "low",
            "risk_notes": "サイズ・重量に注意。大型家具は送料と破損リスクが高いため避ける。",
            "suggested_1688_keywords": ["收纳盒", "收纳篮", "抽屉收纳", "墙挂收纳"],
        },
        {
            "jp_category": "キッチン用品・小型調理グッズ",
            "scene": "時短料理・お弁当・在宅ごはん需要",
            "trend_reason": "楽天ランキングでキッチンツール系はレビュー数が多く、買い替えサイクルも短い。",
            "suitable_for_1688": True,
            "risk_level": "low",
            "risk_notes": "食品衛生法対応（食品接触材質）に注意。できるだけ素材表示が明確な商品を選ぶ。",
            "suggested_1688_keywords": ["厨房小工具", "厨房收纳", "便当盒", "料理模具"],
        },
        {
            "jp_category": "ペット用品（ケア・おもちゃ）",
            "scene": "少子高齢化＋ペット家族化で継続需要",
            "trend_reason": "グローバルでもペット用品は成長カテゴリ。楽天でもペットジャンルが安定して強い。",
            "suitable_for_1688": True,
            "risk_level": "mid",
            "risk_notes": "ペットフード・サプリは規制が重いので避ける。ブラシ・おもちゃ・服など非食品に絞る。",
            "suggested_1688_keywords": ["宠物梳", "宠物玩具", "宠物窝", "猫抓板"],
        },
        {
            "jp_category": "美容雑貨・コスメ収納",
            "scene": "コスメ好き層＋SNS映えニーズ",
            "trend_reason": "楽天 Global Express の 2025 上半期カテゴリ 2位が『美容グッズ・コスメ』。ただし本体コスメは薬機法が重いので雑貨側を攻める。:contentReference[oaicite:4]{index=4}",
            "suitable_for_1688": True,
            "risk_level": "mid",
            "risk_notes": "化粧品本体は避けて、ブラシ・パフ・収納ボックス・ミラーなどに限定。",
            "suggested_1688_keywords": ["化妆刷", "化妆收纳盒", "化妆镜", "收纳化妆包"],
        },
        {
            "jp_category": "スポーツ・アウトドア小物",
            "scene": "健康志向＋週末レジャー需要",
            "trend_reason": "楽天 Global Express 2025 上半期でスポーツ＆アウトドアが人気カテゴリ（TOP4-6）。:contentReference[oaicite:5]{index=5}",
            "suitable_for_1688": True,
            "risk_level": "mid",
            "risk_notes": "安全性に直結する防護具などは慎重に。まずはヨガ・ストレッチ・筋トレの軽量小物中心。",
            "suggested_1688_keywords": ["瑜伽垫", "弹力带", "健身小器材", "户外折叠椅"],
        },
    ]
    return categories

# ========= 日本市場トレンド（楽天天週間ランキング）を使った動的カテゴリ取得 =========

def _fetch_rakuten_weekly_item_names(limit: int = 80) -> list[str]:
    """
    楽天市場 週間総合ランキング https://ranking.rakuten.co.jp/weekly/
    から「item.rakuten.co.jp」へのリンクテキスト（商品名）を最大 limit 件まで取得する。
    """
    url = "https://ranking.rakuten.co.jp/weekly/"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Rakuten1688SelectionBot/0.1)"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    names: List[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # 商品ページへのリンクだけ拾う
        if "item.rakuten.co.jp" not in href:
            continue

        text = a.get_text(strip=True)
        if not text:
            continue
        # 「レビュー(〇件)」などは除外
        if "レビュー" in text:
            continue
        if text in names:
            continue

        names.append(text)
        if len(names) >= limit:
            break

    return names


# 「どのジャンルが今売れているか」を判定するためのルール
CATEGORY_RULES = [
    {
        "jp_category": "収納・整理グッズ（インテリア・寝具・収納）",
        "scene": "家の省スペース化・片付け需要",
        "triggers": ["収納", "ラック", "ボックス", "ケース", "整理", "クローゼット"],
        "budget_band": "low",
        "suitable_for_1688": True,
        "risk_level": "low",
        "risk_notes": "大型家具・ガラス製品は送料と破損リスクが高いため避ける。",
        "suggested_1688_keywords": ["收纳盒", "收纳篮", "抽屉收纳", "墙挂收纳"],
    },
    {
        "jp_category": "キッチン用品・小型調理グッズ",
        "scene": "時短料理・お弁当・在宅ごはん需要",
        "triggers": ["フライパン", "鍋", "保存容器", "キッチン", "まな板", "お弁当箱"],
        "budget_band": "low",
        "suitable_for_1688": True,
        "risk_level": "low",
        "risk_notes": "食品衛生法対応（食品接触材質）に注意。素材表示が明確な商品を選ぶ。",
        "suggested_1688_keywords": ["厨房小工具", "厨房收纳", "便当盒", "料理模具"],
    },
    {
        "jp_category": "ペット用品（ケア・おもちゃ）",
        "scene": "少子高齢化＋ペット家族化で継続需要",
        "triggers": ["ペット", "犬", "猫", "トイレシート", "キャットタワー", "ケア"],
        "budget_band": "low",
        "suitable_for_1688": True,
        "risk_level": "mid",
        "risk_notes": "ペットフード・サプリは規制が重いので避ける。ブラシ・おもちゃ中心。",
        "suggested_1688_keywords": ["宠物梳", "宠物玩具", "宠物窝", "猫抓板"],
    },
    {
        "jp_category": "美容雑貨・コスメ収納",
        "scene": "コスメ好き層＋SNS映えニーズ",
        "triggers": ["コスメ", "メイク", "ミラー", "ドレッサー", "コスメボックス"],
        "budget_band": "low",
        "suitable_for_1688": True,
        "risk_level": "mid",
        "risk_notes": "化粧品本体は薬機法が重いので避けて、ツール・収納中心に。",
        "suggested_1688_keywords": ["化妆刷", "化妆收纳盒", "化妆镜", "收纳化妆包"],
    },
    {
        "jp_category": "スポーツ・アウトドア小物",
        "scene": "健康志向＋週末レジャー需要",
        "triggers": ["ヨガ", "ダンベル", "トレーニング", "アウトドア", "キャンプ"],
        "budget_band": "mid",
        "suitable_for_1688": True,
        "risk_level": "mid",
        "risk_notes": "安全性に直結する防護具は慎重に。まずはヨガ・筋トレ小物中心。",
        "suggested_1688_keywords": ["瑜伽垫", "弹力带", "健身小器材", "户外折叠椅"],
    },
    # 生鮮・冷凍系はルールに入れない（あなたの条件：冷蔵・冷凍なし）
]

def _classify_items_to_categories(item_names: list[str]) -> list[dict]:
    """
    根据 CATEGORY_RULES，把楽天商品タイトル归类成若干大类，并给每个大类一个 score（命中次数）。
    返回的每个 dict 至少包含:
      - jp_category
      - scene
      - suggested_1688_keywords
      - budget_band
      - suitable_for_1688
      - risk_level
      - risk_notes
      - score
    """
    bucket: dict[str, dict] = {}

    for name in item_names:
        for rule in CATEGORY_RULES:
            if any(trigger in name for trigger in rule["triggers"]):
                key = rule["jp_category"]
                if key not in bucket:
                    # 拷贝一份 rule，附带 score
                    bucket[key] = {**rule, "score": 0}
                bucket[key]["score"] += 1

    # 按 score 从高到低排序
    return sorted(bucket.values(), key=lambda x: x["score"], reverse=True)



def get_jp_trending_categories(req: "MarketSuggestRequest") -> List[dict]:
    """
    日本市場トレンド＋你的条件（预算/避开类目）综合后，返回推荐类目列表。
    如果抓取或解析失败，会退回到 get_jp_trending_categories_stub()。
    """
    # 从请求里取参数
    budget = getattr(req, "budget_level", "low") or "low"
    avoid = getattr(req, "avoid_keywords", []) or []
    top_k = getattr(req, "top_k", 5) or 5

    avoid = [str(x) for x in avoid]

    try:
        # 1) 抓取乐天週間総合ランキング的商品标题
        item_names = _fetch_rakuten_weekly_item_names(limit=80)

        # 2) 根据规则判断哪些大类最近在榜上出现多
        candidates = _classify_items_to_categories(item_names)

        # 3) 按预算带过滤（非常粗略，后面可以细化）
        if budget in ("low", "mid", "high"):
            candidates = [
                c for c in candidates if c["budget_band"] in (budget, "all")
            ]

        # 4) 按避开关键词过滤（比如你不想碰「ベビー」「食品」）
        if avoid:
            filtered = []
            for c in candidates:
                text = c["jp_category"] + " " + " ".join(
                    c.get("suggested_1688_keywords", [])
                )
                if any(ng in text for ng in avoid):
                    continue
                filtered.append(c)
            candidates = filtered

        # 5) 为空就退回静态 stub
        if not candidates:
            try:
                return get_jp_trending_categories_stub()
            except NameError:
                return []

        # 6) 截断 top_k
        return candidates[: int(top_k)]

    except Exception:
        # 任意错误都退回静态 stub，保证 /market_suggest 不会炸
        try:
            return get_jp_trending_categories_stub()
        except NameError:
            return []
        
def get_jp_trending_from_rakuten(req: "MarketSuggestRequest") -> List[dict]:
    """
    仅使用楽天週間ランキング来做日本市场类目推荐。
    不做 top_k 截断，由总控函数 get_jp_trending_categories 统一排序和截断。
    """
    budget = getattr(req, "budget_level", "low") or "low"
    avoid = getattr(req, "avoid_keywords", []) or []
    avoid = [str(x) for x in avoid]

    try:
        # 1) 抓取乐天週間総合ランキング商品名
        item_names = _fetch_rakuten_weekly_item_names(limit=80)

        # 2) 标题 → 规则 → 类目候选
        candidates = _classify_items_to_categories(item_names)

        # 3) 按预算带粗过滤
        if budget in ("low", "mid", "high"):
            candidates = [
                c for c in candidates if c.get("budget_band") in (budget, "all")
            ]

        # 4) 按 NG 关键字过滤
        if avoid:
            filtered = []
            for c in candidates:
                text = c.get("jp_category", "") + " " + " ".join(
                    c.get("suggested_1688_keywords", [])
                )
                if any(ng in text for ng in avoid):
                    continue
                filtered.append(c)
            candidates = filtered

        # 在这里不做 top_k，由外层统一截断
        return candidates

    except Exception:
        # 抓取或解析失败时，交给上层决定怎么 fallback
        return []


def get_jp_trending_from_amazon_stub(req: "MarketSuggestRequest") -> List[dict]:
    """
    日本 Amazon.co.jp 趋势的 stub 版本：
    先手工列几个在亚马逊日本一贯很强的类目，后面可以接真正的 Amazon API。
    """
    budget = getattr(req, "budget_level", "low") or "low"
    avoid = getattr(req, "avoid_keywords", []) or []
    avoid = [str(x) for x in avoid]

    # 手工整理几个“更偏向 Amazon 的”强势类目，名称前面加 Amazon｜，避免和楽天重名
    categories = [
        {
            "jp_category": "Amazon｜PC・周辺機器（USBハブ・ドッキングステーション）",
            "scene": "在宅ワーク・ゲーミング・マルチモニター需要",
            "trend_reason": "Amazon.co.jp で常に売れ筋上位に入る PC 周辺小物。単価も手頃で買い替えサイクルが短い。",
            "suitable_for_1688": True,
            "risk_level": "low",
            "risk_notes": "PSE 対象となる AC アダプタ内蔵製品は慎重に。まずはバスパワーの USB ハブやケーブル中心。",
            "suggested_1688_keywords": ["usb 集线器", "type-c 扩展坞", "hdmi 转接线"],
            "budget_band": "low",
            "score": 7,
        },
        {
            "jp_category": "Amazon｜スマホアクセサリ（保護フィルム・ケース）",
            "scene": "スマホ買い替え・機種変更需要＋消耗品需要",
            "trend_reason": "スマホ周辺は Amazon での購入比率が高く、iPhone/Android 新機種ごとに波が来る定番カテゴリ。",
            "suitable_for_1688": True,
            "risk_level": "low",
            "risk_notes": "機種対応のミスに注意。まずは汎用タイプや人気機種に絞る。",
            "suggested_1688_keywords": ["手机 壳", "钢化膜", "手机 支架"],
            "budget_band": "low",
            "score": 6,
        },
        {
            "jp_category": "Amazon｜生活家電（スティック掃除機・小型クリーナー）",
            "scene": "一人暮らし・共働き家庭の省スペース家電需要",
            "trend_reason": "コードレス掃除機や卓上クリーナーは Amazon のレビューとランキングが強く、価格帯も広い。",
            "suitable_for_1688": True,
            "risk_level": "mid",
            "risk_notes": "PSE/Sマークなど電気用品安全法に注意。MVP 時点では電源直結品は避け、小型 USB 給電品から試すのがおすすめ。",
            "suggested_1688_keywords": ["无线 吸尘器", "桌面 吸尘器", "车载 吸尘器"],
            "budget_band": "mid",
            "score": 5,
        },
        {
            "jp_category": "Amazon｜オフィス・文房具（ノート・ペン・整理グッズ）",
            "scene": "在宅ワーク・勉強用のロングテール消耗品",
            "trend_reason": "ノート・ペン・デスク整理グッズは Amazon でレビュー数が多く、リピート性が高い。",
            "suitable_for_1688": True,
            "risk_level": "low",
            "risk_notes": "ブランド模倣品は避ける。無地・シンプルデザインの OEM っぽいものが安全。",
            "suggested_1688_keywords": ["笔记本 文具", "中性笔", "桌面 收纳 办公"],
            "budget_band": "low",
            "score": 4,
        },
    ]

    # 预算带过滤
    if budget in ("low", "mid", "high"):
        categories = [
            c for c in categories if c.get("budget_band") in (budget, "all")
        ]

    # NG 关键字过滤
    if avoid:
        filtered = []
        for c in categories:
            text = c.get("jp_category", "") + " " + " ".join(
                c.get("suggested_1688_keywords", [])
            )
            if any(ng in text for ng in avoid):
                continue
            filtered.append(c)
        categories = filtered

    return categories


def get_jp_trending_categories(req: "MarketSuggestRequest") -> List[dict]:
    """
    总控函数：
    - 根据 req.market_sources 决定用楽天 / Amazon / 或两者
    - 合并结果后按 score 排序，再按 top_k 截断
    - 若完全没有结果则退回静态 stub
    """
    sources = getattr(req, "market_sources", None) or ["rakuten"]
    all_results: List[dict] = []

    if "rakuten" in sources:
        all_results.extend(get_jp_trending_from_rakuten(req))
    if "amazon" in sources:
        all_results.extend(get_jp_trending_from_amazon_stub(req))

    # 如果两个都没拿到结果，退回你原来的静态 stub
    if not all_results:
        try:
            return get_jp_trending_categories_stub()
        except NameError:
            return []

    # 全部按 score 排序，并按 top_k 截断
    try:
        top_k = int(getattr(req, "top_k", 5) or 5)
    except Exception:
        top_k = 5

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_results[:top_k]



def score_product(prod: dict, req: SelectionRequest) -> float:
    """
    简单打分逻辑：
    - 价格在区间内 +0.4
    - 标题里含有“日本友好关键词” +0.4
    - 和用户给的方向有点关系 +0.2
    """
    score = 0.0

    # 价格
    if req.min_price_cny <= prod["price_cny"] <= req.max_price_cny:
        score += 0.4

    # 日本市场友好的关键词（收纳、宠物、北欧、简约等）
    japan_keywords = ["收纳", "宠物", "北欧", "简约", "厨房", "生活", "整理"]
    if any(k in prod["title_cn"] for k in japan_keywords):
        score += 0.4

    # 和方向的相关性
    for d in req.directions:
        if d and d in prod["title_cn"]:
            score += 0.2
            break

    return score

def grade_from_score(score: float, margin_rate: float) -> str:
    """
    根据综合评分和毛利率给商品分档：
    - C 档：分数太低 或 毛利率 < 10%
    - A 档：分数 ≥ 0.7 且 毛利率 ≥ 25%
    - B 档：其他中间情况
    """
    if margin_rate < 0.1 or score < 0.3:
        return "C"
    if score >= 0.7 and margin_rate >= 0.25:
        return "A"
    return "B"

def build_jp_bullets(prod: dict, directions: list) -> list:
    """
    根据1688商品中文标题和方向，生成几条给日本乐天用的日文卖点。
    这里只做很简单的规则，后面可以换成 LLM 来写更聪明的文案。
    """
    title = prod.get("title_cn", "")
    bullets = []

    # 通用一句
    bullets.append("中国工場から直送されるコストパフォーマンスの高いアイテムです。")

    # 宠物相关
    if "宠物" in title:
        bullets.append("ペットとの暮らしで役立つ実用的なアイテムです。")
    if "除毛" in title or "粘毛" in title:
        bullets.append("ソファや服についた抜け毛を手軽にお手入れできます。")

    # 厨房收纳
    if "厨房" in title or "キッチン" in title:
        bullets.append("キッチン周りの小物を省スペースでスッキリ収納できます。")
    if "收纳" in title or "收納" in title:
        bullets.append("限られたスペースでも整理しやすい収納デザインです。")

    # 方向补充（比如 你传了 “宠物”“厨房收纳”）
    for d in directions:
        if d and len(bullets) < 4:
            bullets.append(f"{d}用途としても活用いただけます。")

    return bullets[:4]  # 最多保留4条

def llm_evaluate_product(prod: dict,
                         suggested_price_jpy: int,
                         margin_rate: float,
                         directions: list) -> dict:
    """
    调用 GPT，评估这个 1688 商品对日本乐天的适配度，
    返回 dict: { japan_fit_score, grade, risk_notes, jp_bullets }
    """

    title = prod.get("title_cn", "")
    directions_str = "、".join(directions) if directions else "未指定"

    prompt = f"""
你是一名熟悉日本乐天市场的跨境电商选品顾问。

现在有一个来自 1688 的商品，请你从「是否适合在日本乐天销售」的角度进行评估，并返回 JSON。

【商品信息】
- 中文标题: {title}
- 进货价 (CNY): {prod.get("price_cny")}
- 建议乐天售价 (JPY): {suggested_price_jpy}
- 预估毛利率: {margin_rate:.3f}
- 店铺标签: {", ".join(prod.get("tags", []))}
- 用户希望经营的方向: {directions_str}

【评估要求】
1. japan_fit_score: 0〜1 之间的小数，越高表示越适合日本乐天销售。
2. grade: "A" / "B" / "C"
3. risk_notes: 中文简短说明潜在风险。
4. jp_bullets: 2〜4 条日文卖点文案（です・ます調）。

请严格只输出下面这种 JSON 格式，不要多写解释：
{{
  "japan_fit_score": 0.0,
  "grade": "A",
  "risk_notes": ["..."],
  "jp_bullets": ["...", "..."]
}}
    """.strip()

    resp = openai.ChatCompletion.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant for Japanese Rakuten cross-border product selection."
            },
            {
                "role": "user",
                "content": prompt
            },
        ],
        temperature=0.3,
    )

    content = resp["choices"][0]["message"]["content"]
    data = json.loads(content)
    return data


def estimate_price_and_margin(price_cny: float, req: SelectionRequest):
    """
    简单利润模型：
    - 人民币成本 + 国内运费(写死5元) → 换算成日元
    - 加上国际运费
    - 考虑乐天平台费率，反推出建议售价和毛利率
    """
    domestic_cny = 5.0  # 先写死每件国内运费5元

    # 1) 成本换算成日元
    base_cost_jpy = (price_cny + domestic_cny) * req.cny_to_jpy

    # 2) 加上国际运费
    total_cost_before_fee = base_cost_jpy + req.intl_shipping_jpy

    # 3) 反推建议售价：售价 * (1 - commission) 要覆盖成本 + 预留一点毛利
    # 这里先按目标毛利率20%来算，可以后面改成参数
    target_margin_rate = 0.2
    denom = 1.0 - req.commission_rate - target_margin_rate
    if denom <= 0:
        denom = 1.0 - req.commission_rate - 0.05  # 死活留5%毛利

    suggested_price_jpy = total_cost_before_fee / denom

    # 实际毛利率
    real_margin = (
        suggested_price_jpy * (1 - req.commission_rate) - total_cost_before_fee
    ) / suggested_price_jpy

    return round(suggested_price_jpy), round(real_margin, 3)

def generate_rakuten_listing_copy(req: ListingCopyRequest) -> dict:
    """
    使用 ChatGPT 生成乐天商品文案：
    - 标题
    - 箇条書き（卖点）
    - 长描述
    - 搜索用キーワード
    """
    # 把日文关键词拼成提示
    kw_line = "、".join(req.keywords_jp) if req.keywords_jp else ""
    system_msg = (
        "あなたは日本の楽天市場のプロ店長です。"
        "中国輸入商品の元情報（中国語）をもとに、日本の楽天市場向けの商品ページ用のテキストを作成します。"
        "薬機法・景表法に抵触しないように、誇大広告は避けてください。"
    )

    user_prompt = f"""
【元タイトル（中国語）】
{req.title_cn}

【元説明（中国語・空欄可）】
{req.desc_cn}

【優先して入れたい日本語キーワード（あれば）】
{kw_line}

【希望する文体】
{req.shop_tone}

以下の JSON 形式で回答してください（日本語）:

{{
  "title_jp": "楽天用の商品タイトル（全角70文字前後）",
  "bullets_jp": [
    "箇条書きのポイント1",
    "箇条書きのポイント2",
    "箇条書きのポイント3"
  ],
  "description_jp": "商品説明文（3〜5段落程度）",
  "search_keywords_jp": ["検索キーワード1", "検索キーワード2", "検索キーワード3"]
}}
    """.strip()

    resp = openai.ChatCompletion.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )

    content = resp["choices"][0]["message"]["content"]
    # 尝试解析为 JSON；如果失败就包在一个字段里返回
    try:
        data = json.loads(content)
    except Exception:
        data = {"raw_text": content}

    return data



@app.get("/")
def read_root():
    return {"message": "Rakuten-1688 agent is running"}


@app.post("/select")
def select_products(req: SelectionRequest):
    """
    从本地 CSV / 假数据中选品：
      - 用 score_product 做基础打分
      - 用 estimate_price_and_margin 估算建议售价和毛利率
      - 选用 LLM 做精细评估（失败则回退到规则打分）
    """
    products = load_products_from_csv()
    results = []

    for p in products:
        price_cny = float(p.get("price_cny", 0.0))

        # 1) 规则打分（base_score）
        base_score = score_product(p, req)

        # 2) 利润模型：建议售价 + 毛利率
        suggested_price_jpy, margin_rate = estimate_price_and_margin(price_cny, req)

        # 3) 默认档位和卖点（LLM 失败时用）
        grade = grade_from_score(base_score, margin_rate)
        jp_bullets = build_jp_bullets(p, req.directions)
        risk_notes: list[str] = []

        # 4) 尝试调用 LLM 做更细的评估（可选）
        japan_fit_score = base_score  # 默认用规则分
        try:
            llm_res = llm_evaluate_product(
                prod=p,
                suggested_price_jpy=suggested_price_jpy,
                margin_rate=margin_rate,
                directions=req.directions,
            )
            if isinstance(llm_res, dict):
                if "japan_fit_score" in llm_res:
                    japan_fit_score = float(llm_res["japan_fit_score"])
                if "grade" in llm_res:
                    grade = llm_res["grade"]
                if llm_res.get("jp_bullets"):
                    jp_bullets = llm_res["jp_bullets"]
                if llm_res.get("risk_notes"):
                    risk_notes = llm_res["risk_notes"]
        except Exception as e:
            risk_notes.append(
                f"LLM評価に失敗したため、ルールベースで算出しました。error={e}"
            )

        results.append(
            {
                "id": p.get("id", ""),
                "title_cn": p.get("title_cn", ""),
                "price_cny": price_cny,
                "score": round(japan_fit_score, 3),
                "suggested_price_jpy": suggested_price_jpy,
                "margin_rate": margin_rate,
                "grade": grade,
                "jp_bullets": jp_bullets,
                "risk_notes": risk_notes,
            }
        )

    # 按最终得分降序
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "directions": req.directions,
        "results": results,
    }


@app.post("/select_csv", response_class=PlainTextResponse)
def select_products_csv(req: SelectionRequest):
    """
    和 /select 请求体完全相同，但返回值是 CSV 文本，方便导入 Excel。
    """
    # 复用原来的逻辑，先拿到 JSON 结果
    result = select_products(req)
    items = result["results"]

    # 用 StringIO + csv.writer 拼一段 CSV 字符串
    output = StringIO()
    writer = csv.writer(output)

    # 表头：可以根据你现在的结果字段调整
    writer.writerow([
        "id",
        "title_cn",
        "price_cny",
        "score",
        "grade",
        "suggested_price_jpy",
        "margin_rate",
    ])

    for item in items:
        writer.writerow([
            item.get("id", ""),
            item.get("title_cn", ""),
            item.get("price_cny", ""),
            item.get("score", ""),
            item.get("grade", ""),
            item.get("suggested_price_jpy", ""),
            item.get("margin_rate", ""),
        ])

    csv_text = '\ufeff' + output.getvalue()
    return csv_text

@app.post("/auto_select")
def auto_select(req: AutoSelectRequest):
    """
    输入一个类目（category），agent 自动“去1688”拉一批候选商品，
    再用现有的打分规则做选品。
    """
    # 1) 用类目在1688搜索（目前用 stub 模拟，将来这里会变成真 API 调用）
    raw_products = search_1688_stub(req.category, req.max_items)

    # 2) 按你已有的规则 + 价格区间打分
    scored = []
    for p in raw_products:
        # 加一层价格过滤
        price = p["price_cny"]
        if not (req.min_price_cny <= price <= req.max_price_cny):
            continue

        s = score_product(
            p,
            SelectionRequest(
                directions=[req.category],
                min_price_cny=req.min_price_cny,
                max_price_cny=req.max_price_cny,
            ),
        )

        scored.append(
            {
                "id": p["id"],
                "title_cn": p["title_cn"],
                "price_cny": price,
                "score": round(s, 3),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "category": req.category,
        "min_price_cny": req.min_price_cny,
        "max_price_cny": req.max_price_cny,
        "results": scored,
    }

@app.post(
    "/ali1688/parse_url",
    response_model=Ali1688ParsedItem,
    dependencies=[Depends(verify_token)],
)
def ali1688_parse_url(req: Ali1688UrlParseRequest):

    """
    贴 1688 商品 URL，自动抓取商品标题 / 价格 / 图片。
    """
    try:
        item_dict = parse_1688_url(req.url)
    except Ali1688UrlParseError as e:
        # 抛成 400，前端可以直接提示
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))

    # 用 Pydantic 做一次标准化
    return Ali1688ParsedItem(**item_dict)

@app.post("/market_suggest")
def market_suggest(req: MarketSuggestRequest):
    """
    根据日本市场（特别是楽天週間ランキング）的最新趋势，
    推荐若干适合「无冷链 + 1688 进货 + 无压货代发」的类目，
    并给出对应的 1688 搜索关键词建议。
    """
    categories = get_jp_trending_categories(req)

    suggestions = []
    for c in categories:
        suggestions.append(
            {
                "jp_category": c["jp_category"],
                "scene": c.get("scene", ""),
                "trend_reason": c.get("trend_reason", ""),
                "suitable_for_1688": c.get("suitable_for_1688", True),
                "risk_level": c.get("risk_level", "low"),
                "risk_notes": c.get("risk_notes", ""),
                "suggested_1688_keywords": c.get("suggested_1688_keywords", []),
                "score": c.get("score", 0),
                # 给你一个可以直接丢给 /auto_select 的示例 payload
                "sample_auto_select_payload": {
                    # 这里你也可以手动改成中文关键词，比如取 suggested_1688_keywords[0]
                    "category": c["jp_category"],
                    "max_items": 30,
                    "min_price_cny": 5,
                    "max_price_cny": 40,
                },
            }
        )

    return {
        "budget_level": req.budget_level,
        "avoid_keywords": req.avoid_keywords,
        "suggestions": suggestions,
    }

@app.post("/market_auto_select", dependencies=[Depends(verify_token)])
def market_auto_select(req: MarketAutoSelectRequest):
    """
    一键管道：
      1. 根据日本乐天週間ランキング，按预算和避开关键词选出若干热门类目
      2. 为每个类目选一个 1688 搜索关键词
      3. 使用现有的打分逻辑（score_product）对 1688 候选商品打分
    """
    # 1) 先根据日本市场情况选类目（复用 get_jp_trending_categories）
    ms_req = MarketSuggestRequest(
    budget_level=req.budget_level,
    avoid_keywords=req.avoid_keywords,
    top_k=req.top_k_categories,
    market_sources=["rakuten", "amazon"],  # 默认两边一起看
)

    trending_cats = get_jp_trending_categories(ms_req)

    results = []

    for cat in trending_cats:
        # 2) 选一个喂给 1688 的搜索关键词
        kw_list = cat.get("suggested_1688_keywords") or []
        if kw_list:
            category_kw = kw_list[0]   # 先用第一个关键词
        else:
            # 没有预设关键词时，就用日文类目名，后面你可以自己映射成中文
            category_kw = cat["jp_category"]

        # 3) 类目对应的 1688 候选商品（现在用 stub，将来你把这行换成真实 API 即可）
        raw_products = search_1688_stub(category_kw, req.max_items_per_category)

        # 4) 用你现有的规则对候选商品做价格过滤 + 打分
        sel_req = SelectionRequest(
            directions=[category_kw],  # 当成方向关键词，用于 score_product 里的匹配
            min_price_cny=req.min_price_cny,
            max_price_cny=req.max_price_cny,
        )

        scored_items = []
        for p in raw_products:
            price = p.get("price_cny", 0.0)
            # 价格过滤
            if not (req.min_price_cny <= price <= req.max_price_cny):
                continue

            s = score_product(p, sel_req)

            scored_items.append(
                {
                    "id": p.get("id", ""),
                    "title_cn": p.get("title_cn", ""),
                    "price_cny": price,
                    "score": round(s, 3),
                }
            )

        # 按分数从高到低排序
        scored_items.sort(key=lambda x: x["score"], reverse=True)

        results.append(
            {
                "jp_category": cat["jp_category"],
                "scene": cat.get("scene", ""),
                "trend_reason": cat.get("trend_reason", ""),
                "category_keyword_1688": category_kw,
                "suggested_1688_keywords": kw_list,
                "risk_level": cat.get("risk_level", "low"),
                "risk_notes": cat.get("risk_notes", ""),
                "items": scored_items,
            }
        )

    return {
        "budget_level": req.budget_level,
        "avoid_keywords": req.avoid_keywords,
        "top_k_categories": req.top_k_categories,
        "min_price_cny": req.min_price_cny,
        "max_price_cny": req.max_price_cny,
        "results": results,
    }

@app.post(
    "/market_auto_select_csv",
    response_class=PlainTextResponse,
    dependencies=[Depends(verify_token)],
)
def market_auto_select_csv(req: MarketAutoSelectRequest):

    """
    /market_auto_select 的 CSV 版：
    - 按日本市场趋势选类目
    - 每个类目下的候选 SKU 打分
    - 全部打平成一张 CSV 表方便在 Excel 里筛选
    """
    result = market_auto_select(req)
    cats = result.get("results", [])

    output = StringIO()
    writer = csv.writer(output)

    # 表头：可以按需要以后再加列
    writer.writerow([
        "jp_category",          # 日本侧类目
        "scene",                # 使用场景
        "risk_level",           # 风险等级
        "category_keyword_1688",# 这次喂给 1688 的关键词
        "item_id",              # 1688 商品ID（你先用自己的ID占位）
        "title_cn",             # 中文标题
        "price_cny",            # 进货价
        "score",                # 你的选品打分
    ])

    for cat in cats:
        jp_category = cat.get("jp_category", "")
        scene = cat.get("scene", "")
        risk_level = cat.get("risk_level", "")
        kw_1688 = cat.get("category_keyword_1688", "")

        for item in cat.get("items", []):
            writer.writerow([
                jp_category,
                scene,
                risk_level,
                kw_1688,
                item.get("id", ""),
                item.get("title_cn", ""),
                item.get("price_cny", ""),
                item.get("score", ""),
            ])

    csv_text = '\ufeff' + output.getvalue()
    return csv_text

@app.post("/rakuten_profit_simulate", dependencies=[Depends(verify_token)])
def rakuten_profit_simulate(req: ProfitSimRequest):
    """
    给一组候选商品做乐天利润测算：
    - 输入：1688 成本、预估运费、乐天售价、手续费比例
    - 输出：毛利、毛利率、简单建议
    """
    result_items = []

    for it in req.items:
        # 1) 人民币成本 → 日元
        total_cost_cny = it.cost_cny + it.shipping_cny
        total_cost_jpy = total_cost_cny * req.fx_rate + it.other_fee_jpy

        # 2) 乐天手续费（粗略按销售额 * 手续费率算）
        rakuten_fee_jpy = it.sell_price_jpy * req.rakuten_fee_rate

        # 3) 毛利和毛利率
        gross_profit = it.sell_price_jpy - total_cost_jpy - rakuten_fee_jpy
        if it.sell_price_jpy > 0:
            margin = gross_profit / it.sell_price_jpy
        else:
            margin = 0.0

        # 4) 简单建议文案
        if gross_profit <= 0:
            advice = "赤字。進貨価格または販売価格を見直してください。"
        elif margin < 0.1:
            advice = "利益率が低め（10％未満）。セット販売・まとめ買いなどを検討。"
        elif margin < 0.25:
            advice = "標準的な利益率。広告費をどこまで乗せられるか試算してください。"
        else:
            advice = "高めの利益率。優先的にテスト出品候補。"

        result_items.append(
            {
                "product_id": it.product_id,
                "title_cn": it.title_cn,
                "cost_total_jpy": round(total_cost_jpy),
                "rakuten_fee_jpy": round(rakuten_fee_jpy),
                "gross_profit_jpy": round(gross_profit),
                "margin": round(margin, 3),
                "advice": advice,
            }
        )

    return {
        "fx_rate": req.fx_rate,
        "rakuten_fee_rate": req.rakuten_fee_rate,
        "items": result_items,
    }

@app.post("/rakuten_listing_copy", dependencies=[Depends(verify_token)])
def rakuten_listing_copy(req: ListingCopyRequest):
    """
    1688の中国語情報から、楽天向け日本語商品ページ文案を生成するエンドポイント。
    エラーが起きても HTTP 500 にはせず、error フィールドにメッセージを入れて 200 で返す。
    """
    system_prompt = (
        "あなたは日本の楽天市場のプロの運営担当者です。"
        "出力は必ず JSON のみで返してください。"
        "構造は {"
        '"title_jp": "...",'
        '"bullets_jp": ["...", "..."],'
        '"description_jp": "...",'
        '"search_keywords_jp": ["...", "..."]'
        "} です。"
    )

    user_prompt = f"""
1688の商品情報をもとに、楽天市場向けの日本語の商品ページ文案を作ってください。

[中国語タイトル]
{req.title_cn}

[中国語説明文]
{req.desc_cn or "（説明文なし）"}

[優先キーワード（日文）]
{", ".join(req.keywords_jp) if req.keywords_jp else "（特になし）"}

[文体]
{req.shop_tone}

注意:
- タイトルは全角 60〜80 文字程度を目安にしてください。
- 箇条書きは 4〜6 個にしてください。
- 説明文は 400〜800 文字を目安に、読みやすい段落にしてください。
- 絶対に JSON 以外の文章は書かないでください。
""".strip()

    # 1) 先调用 OpenAI，如果失败，就用 error 结构返回（HTTP 200）
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # 模型按你现在用的
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
        )
        content = resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("OPENAI ChatCompletion error: %r", e)
        return {
            "title_jp": "",
            "bullets_jp": [],
            "description_jp": "",
            "search_keywords_jp": [],
            "error": {
                "code": "OPENAI_CALL_ERROR",
                "message_ja": "現在AI文案生成が一時的に利用しづらい状態です。時間をおいて再度お試しください。",
                "debug": str(e),
            },
        }

    # 2) 解析 JSON，如果失败，用 error + raw_text 返回
    try:
        data = json.loads(content)
        return {
            "title_jp": data.get("title_jp", ""),
            "bullets_jp": data.get("bullets_jp", []),
            "description_jp": data.get("description_jp", ""),
            "search_keywords_jp": data.get("search_keywords_jp", []),
        }
    except Exception as e:
        logger.warning("OPENAI JSON parse failed: %r; content=%r", e, content)
        return {
            "title_jp": "",
            "bullets_jp": [],
            "description_jp": "",
            "search_keywords_jp": [],
            "error": {
                "code": "OPENAI_JSON_ERROR",
                "message_ja": "AIからの応答をうまく解析できませんでした。テキストをそのまま表示します。",
                "debug": str(e),
                "raw_text": content,
            },
        }
