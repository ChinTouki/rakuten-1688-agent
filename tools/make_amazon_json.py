import csv, json
from pathlib import Path

input_csv = "ht_amazon_main_2025-11.csv"
shop_id = "ht_amazon_main"

records = []
with open(input_csv, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        records.append({
            "date": row["date"],
            "asin": row["asin"],
            "sku": row.get("sku"),
            "title": row.get("title"),
            "units": int(row.get("units", 0) or 0),
            "sales_jpy": float(row.get("sales_jpy", 0) or 0),
            "page_views": int(row.get("page_views", 0) or 0),
            "sessions": int(row.get("sessions", 0) or 0),
            "conversion_rate": None,      # 让后端自己算也可以
            "ad_spend_jpy": float(row.get("ad_spend_jpy", 0) or 0),
        })

out_dir = Path("data/amazon_reports")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"{shop_id}.json"
out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

print("saved:", out_path)
