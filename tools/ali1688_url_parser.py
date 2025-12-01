# tools/ali1688_url_parser.py

import re
from typing import Dict, Any

import requests
from bs4 import BeautifulSoup


class Ali1688UrlParseError(Exception):
    pass


def parse_1688_url(url: str) -> Dict[str, Any]:
    """
    直接请求 1688 商品页面 HTML，用简单规则解析商品信息。
    注意：实际页面结构可能变动，这里只是 MVP 级解析，解析不到时字段为 None。
    """
    if "1688.com" not in url:
        raise Ali1688UrlParseError("当前工具只支持 1688.com 域名的商品 URL")

    headers = {
        # 尽量模拟正常浏览器
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        raise Ali1688UrlParseError(f"请求 1688 页面失败: {e}")

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    if "sufei-punish" in html or "<punish-component" in html:
        raise Ali1688UrlParseError(
            "当前请求被 1688 识别为自动访问，返回了验证页面（滑块/验证码）。"
            "服务器端暂时无法自动获取该商品信息，请在浏览器中打开该链接完成验证，"
            "并手动录入标题和价格。"
        )

    # ---------- 标题 ----------
    title = None

    # 1) 先尝试 og:title
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    # 2) fallback: <title> 标签
    if not title and soup.title:
        title_text = soup.title.get_text(strip=True)
        # 一般格式类似 “xxx - 阿里巴巴1688.com”
        title = title_text.replace("- 阿里巴巴1688.com", "").strip()

    # ---------- 价格（元） ----------
    price = None

    # 1) 尝试 meta price
    meta_price = soup.find("meta", attrs={"property": "og:product:price"})
    if meta_price and meta_price.get("content"):
        try:
            price = float(meta_price["content"])
        except Exception:
            price = None

    # 2) 尝试 itemprop="price"
    if price is None:
        price_tag = soup.find(attrs={"itemprop": "price"})
        if price_tag:
            price_text = price_tag.get("content") or price_tag.get_text(strip=True)
            if price_text:
                # 提取第一个数字
                m = re.search(r"\d+(\.\d+)?", price_text)
                if m:
                    try:
                        price = float(m.group(0))
                    except Exception:
                        price = None

    # 3) 尝试从 JS 中粗暴 regex 提取 "price":"123.45"
    if price is None:
        m = re.search(r'"price"\s*:\s*"(\d+(\.\d+)?)"', html)
        if not m:
            m = re.search(r'"unitPrice"\s*:\s*"(\d+(\.\d+)?)"', html)
        if m:
            try:
                price = float(m.group(1))
            except Exception:
                price = None

    # ---------- 图片 ----------
    images = []

    # 1) og:image
    og_img = soup.find("meta", attrs={"property": "og:image"})
    if og_img and og_img.get("content"):
        images.append(og_img["content"])

    # 2) detail/gallery 类图片（简单猜一下）
    #    这里用 class 名字里包含 "image" 或 "gallery" 的 <img>
    for img in soup.find_all("img"):
        cls = " ".join(img.get("class") or [])
        if any(k in cls.lower() for k in ["image", "gallery", "detail", "img"]):
            src = img.get("src") or img.get("data-lazy-src") or img.get("data-src")
            if src and src.startswith("http") and src not in images:
                images.append(src)

    # 保留前 5 张
    images = images[:5]

    # ---------- 返回统一结构 ----------
    snippet = html[:2000]  # 为了 debug，最多保留 2000 字符
    return {
        "url": url,
        "title_cn": title,
        "price_cny": price,
        "images": images,
        "raw_html_snippet": snippet,
    }
