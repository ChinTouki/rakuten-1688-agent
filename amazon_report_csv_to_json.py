import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# ==== 根据你项目的结构修改这里 ====
BASE_DIR = Path(__file__).resolve().parents[1]  # 项目根目录
OUT_DIR = BASE_DIR / "data" / "amazon_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_float(v: str) -> Optional[float]:
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_int(v: str) -> Optional[int]:
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def normalize_row(row: Dict[str, str]) -> Dict[str, Any]:
    """
    把亚马逊 Business Report 的一行，统一映射成我们内部用的字段。
    这里同时考虑英文列名 & 日文列名，你实际可以按自己 CSV 调整。
    """
    # 你可以先 print(row.keys()) 看看真实列名，然后在下面补充映射
    col = {k.strip(): v for k, v in row.items()}

    # 可能的列名候选（按你实际 CSV 调整）
    def pick(*cands: str) -> str:
        for c in cands:
            if c in col:
                return col[c]
        return ""

    date = pick("date", "Date", "日付")
    asin = pick("asin", "ASIN")
    sku = pick("sku", "SKU", "商品番号")
    title = pick("title", "タイトル", "商品名")

    units = parse_int(pick("units_ordered", "Units Ordered", "注文商品数"))
    sales_jpy = parse_float(pick("ordered_product_sales", "Ordered Product Sales", "注文商品売上"))
    page_views = parse_int(pick("page_views", "Page Views", "ページビュー"))
    sessions = parse_int(pick("sessions", "Sessions", "セッション"))
    conversion_rate = parse_float(
        pick("conversion_rate", "Unit Session Percentage", "ユニットセッション率 (%)").replace("%", "")
    )

    ad_spend_jpy = parse_float(pick("ad_spend_jpy", "Ad Spend", "広告費"))  # 如果没有就为空

    # 类别可以后面单独打，先留空
    # category = pick("category", "カテゴリ")  # 可选

    return {
        "date": date,                        # "2025-11-01"
        "asin": asin,
        "sku": sku or None,
        "title": title or None,
        "units": units or 0,
        "sales_jpy": sales_jpy or 0.0,
        "page_views": page_views,
        "sessions": sessions,
        "conversion_rate": conversion_rate,
        "ad_spend_jpy": ad_spend_jpy,
        # "category": category or None,
    }


def convert_csv_to_json(csv_path: Path, shop_id: str) -> Path:
    """
    把指定 CSV 转成 JSON，保存为 data/amazon_reports/{shop_id}.json
    """
    records: List[Dict[str, Any]] = []

    # 亚马逊 JP 报表常见是 Shift_JIS / CP932，你可以试试：
    #   - 如果报错，改成 encoding="utf-8-sig"
    with csv_path.open("r", encoding="cp932", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = normalize_row(row)
            # 只保留有 ASIN & 日期的行
            if rec["asin"] and rec["date"]:
                records.append(rec)

    out_path = OUT_DIR / f"{shop_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(records)} records saved to {out_path}")
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert Amazon Business Report CSV to JSON")
    parser.add_argument("csv_file", help="Path to Amazon CSV file")
    parser.add_argument("--shop-id", required=True, help="Shop ID, e.g. ht_amazon_main")
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    convert_csv_to_json(csv_path, args.shop_id)
