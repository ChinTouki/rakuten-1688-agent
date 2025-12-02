from tools.ali1688_stub import search_ali1688_by_cn_keyword

if __name__ == "__main__":
    kw = "收纳盒"
    items = search_ali1688_by_cn_keyword(
        keyword=kw,
        min_price_cny=5,
        max_price_cny=50,
        max_items=10,
    )
    print(f"keyword: {kw}, got {len(items)} items")
    for it in items:
        print(it)
