import csv
import json
import argparse
from pathlib import Path


def convert_csv_to_json(csv_file: str, shop_id: str) -> None:
    """
    读取 Amazon 日报 CSV，转换为 data/amazon_reports/{shop_id}.json

    要求 CSV 至少包含这些列：
      - date
      - asin
      - sku
      - title
      - units
      - sales_jpy
      - page_views
      - sessions
      - ad_spend_jpy
    """
    csv_path = Path(csv_file)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

    records = []

    # ★关键：用 UTF-8-SIG 读取，避免 cp932 解码错误
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # 必须有 date & asin，其他缺失就按 0 或 None
            if not row.get("date") or not row.get("asin"):
                continue

            def _to_int(v, default=0):
                try:
                    v = (v or "").strip()
                    return int(v) if v else default
                except Exception:
                    return default

            def _to_float(v, default=0.0):
                try:
                    v = (v or "").strip()
                    return float(v) if v else default
                except Exception:
                    return default

            rec = {
                "date": row.get("date"),
                "asin": row.get("asin"),
                "sku": row.get("sku") or None,
                "title": row.get("title") or None,
                "units": _to_int(row.get("units")),
                "sales_jpy": _to_float(row.get("sales_jpy")),
                "page_views": _to_int(row.get("page_views")),
                "sessions": _to_int(row.get("sessions")),
                # 转化率先交给后端去算，这里统一设为 None
                "conversion_rate": None,
                "ad_spend_jpy": _to_float(row.get("ad_spend_jpy")),
            }
            records.append(rec)

    out_dir = Path("data/amazon_reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{shop_id}.json"
    out_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"saved: {out_path}  (records={len(records)})")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Amazon daily CSV report to JSON for HT shop analysis."
    )
    parser.add_argument(
        "csv_file",
        help="输入的 Amazon 日报 CSV 文件路径（UTF-8 或 UTF-8-SIG）",
    )
    parser.add_argument(
        "--shop-id",
        required=True,
        help="店铺 ID（生成 data/amazon_reports/{shop_id}.json）",
    )
    args = parser.parse_args()

    convert_csv_to_json(args.csv_file, args.shop_id)


if __name__ == "__main__":
    main()
