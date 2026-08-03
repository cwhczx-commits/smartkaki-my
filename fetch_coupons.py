"""
fetch_coupons.py (v2)
======================
主数据源: /offers/all (application_status=Approved) —— 你已确认有8条真实数据
附加数据源: /campaigns/all (coupons_only=true) —— 允许为空，不影响主流程

字段名策略:
  官方文档没给响应体的具体字段名(只给了请求参数)，所以这里用"候选key列表，
  取第一个存在且非空的"这种写法。跑完第一次之后，看 Actions 日志里打印的
  "第一条offer的原始字段"，或者直接打开 coupons.json 里任意一条的 "_raw"，
  对照真实字段名，去下面 FIELD_CANDIDATES 里调整/补充候选key即可，
  不需要改其他逻辑。
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://api.involve.asia/api"


def authenticate(key: str, secret: str) -> str:
    resp = requests.post(f"{BASE_URL}/authenticate", data={"key": key, "secret": secret}, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]["token"]


def request_with_backoff(method: str, endpoint: str, token: str, retries: int = 4, **kwargs) -> dict:
    for attempt in range(retries):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.request(method, f"{BASE_URL}{endpoint}", headers=headers, timeout=15, **kwargs)
        if resp.status_code == 429:
            time.sleep(0.25 * (2 ** attempt))
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"请求失败，已重试 {retries} 次: {endpoint}")


def fetch_all_pages(endpoint: str, token: str, data_template: dict) -> list:
    """通用分页拉取: 循环直到 page*limit >= count"""
    rows = []
    page = 1
    while True:
        data = dict(data_template)
        data["page"] = page
        resp = request_with_backoff("POST", endpoint, token, data=data)
        block = resp["data"]
        rows.extend(block["data"])
        if page * block["limit"] >= block["count"]:
            break
        page += 1
    return rows


# 候选字段名: 从左到右尝试，取第一个存在且非空的值
FIELD_CANDIDATES = {
    "id": ["offer_id", "id", "campaign_id"],
    "name": ["offer_name", "name", "title", "campaign_name"],
    "commission": ["commission", "commission_percent", "payout", "rate", "commission_rate"],
    "country": ["offer_country", "country"],
    "category": ["categories", "category"],
    "image": ["offer_logo", "logo", "banner", "banner_image", "image", "image_url"],
    "url": ["offer_url", "url", "landing_page", "tracking_link"],
    "voucher_code": ["voucher_code", "coupon_code", "code"],
    "end_date": ["end_date", "campaign_end_date", "expiry_date"],
}


def pick(row: dict, field: str):
    for key in FIELD_CANDIDATES[field]:
        if key in row and row[key]:
            return row[key]
    return None


def normalize(row: dict, source: str) -> dict:
    return {
        "source": source,  # "offer" 或 "coupon"
        "id": pick(row, "id"),
        "name": pick(row, "name"),
        "commission": pick(row, "commission"),
        "country": pick(row, "country"),
        "category": pick(row, "category"),
        "image": pick(row, "image"),
        "url": pick(row, "url"),
        "voucher_code": pick(row, "voucher_code"),
        "end_date": pick(row, "end_date"),
        "_raw": row,  # 原始数据全保留，字段名对不上时来这里查真实key叫什么
    }


def main():
    key = os.environ.get("INVOLVE_ASIA_KEY")
    secret = os.environ.get("INVOLVE_ASIA_SECRET")
    if not key or not secret:
        print("缺少 INVOLVE_ASIA_KEY / INVOLVE_ASIA_SECRET 环境变量", file=sys.stderr)
        sys.exit(1)

    print("正在认证...")
    token = authenticate(key, secret)

    print("正在拉取已批准的offers (主数据源)...")
    offers = fetch_all_pages(
        "/offers/all", token,
        {"limit": 100, "filters[application_status]": "Approved"},
    )
    print(f"  拉到 {len(offers)} 条offer")
    if offers:
        print("  第一条offer的原始字段(调试用，字段名对不上时看这里):")
        print(" ", json.dumps(offers[0], ensure_ascii=False)[:800])

    print("正在拉取带优惠码的campaigns (附加数据源，允许为空)...")
    try:
        coupons = fetch_all_pages(
            "/campaigns/all", token,
            {"limit": 100, "filters[coupons_only]": "true"},
        )
    except Exception as e:
        print(f"  campaigns拉取失败，忽略并继续跑主流程: {e}")
        coupons = []
    print(f"  拉到 {len(coupons)} 条coupon campaign")

    deals = [normalize(o, "offer") for o in offers] + [normalize(c, "coupon") for c in coupons]

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "offer_count": len(offers),
        "coupon_count": len(coupons),
        "deals": deals,
    }

    with open("coupons.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完成: {len(offers)} offers + {len(coupons)} coupons = {len(deals)} 条写入 coupons.json")


if __name__ == "__main__":
    main()
