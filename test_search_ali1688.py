from dotenv import load_dotenv
load_dotenv()  # 读取 .env 中的 ONEBOUND_API_KEY / SECRET

from tools.ali1688_stub import search_ali1688_by_cn_keyword

def main():
    keyword = "收纳盒"
    items = search_ali1688_by_cn_keyword(
        keyword=keyword,
        max_items=5,
        min_price_cny=5,
        max_price_cny=40,
    )

    print(f"keyword: {keyword}, got {len(items)} items")
    for it in items:
        print("-" * 40)
        print("id:", it.get("id"))
        print("title_cn:", it.get("title_cn"))
        print("price_cny:", it.get("price_cny"))
        print("sales:", it.get("sales"))
        print("score:", it.get("score"))
        print("url:", it.get("detail_url"))

if __name__ == "__main__":
    main()
