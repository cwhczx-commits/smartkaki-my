"""
fetch_coupons.py (v3)
======================
根据真实API响应修正:
  - country 字段真实名字是 countries (复数)
  - commission 不是单值字段，而是 commissions: [{"标签": "1.96%"}, ...] 这种数组，
    需要专门解析，取里面最大的百分比作为 "Up to X%" 展示
  - _raw 里去掉了 description 那段几KB的HTML，改成一段纯文字 summary，
    减小 coupons.json 体积

主数据源: /offers/all (application_status=Approved)
附加数据源: /campaigns/all (coupons_only=true)，允许为空
"""

import json
import os
import re
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
    "country": ["offer_country", "country", "countries"],   # 实测: 真实字段是 countries
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


def extract_commission_display(row: dict) -> str | None:
    """
    commissions / special_commissions 是 [{"标签": "1.96%"}, ...] 这种数组。
    取所有条目里出现过的最大百分比，格式化成 "Up to X%"。
    注意: 这会取全部档位里的最高值(包括限量/品牌特殊档位)，不代表大部分订单
    实际能拿到的比率——只是用来在网页上做一个吸引眼球的"最高可达"标签，
    如果想要更保守/准确的数字，可以改成只取 commissions[0] 那个基础档位。
    """
    percents = []
    fallback_text = None
    for group_key in ("commissions", "special_commissions"):
        for entry in row.get(group_key) or []:
            if not isinstance(entry, dict):
                continue
            for _, value in entry.items():
                value = str(value)
                if fallback_text is None:
                    fallback_text = value
                percents.extend(float(p) for p in re.findall(r"(\d+(?:\.\d+)?)\s*%", value))
    if percents:
        return f"Up to {max(percents):g}%"
    return fallback_text  # 比如纯flat-rate "Up to ¥16.50" 这种没有%号的情况


def strip_html(html: str, max_len: int = 220) -> str:
    """把HTML简介转成一小段纯文字摘要，给网页卡片用"""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&rsquo;", "'").replace("&lsquo;", "'")
                .replace("&ldquo;", '"').replace("&rdquo;", '"'))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text


def normalize(row: dict, source: str) -> dict:
    raw_trimmed = {k: v for k, v in row.items() if k != "description"}
    return {
        "source": source,  # "offer" 或 "coupon"
        "id": pick(row, "id"),
        "name": pick(row, "name"),
        "commission": extract_commission_display(row),
        "country": pick(row, "country"),
        "category": pick(row, "category"),
        "image": pick(row, "image"),
        "url": pick(row, "url"),
        "voucher_code": pick(row, "voucher_code"),
        "end_date": pick(row, "end_date"),
        "summary": strip_html(row.get("description", "")),
        "_raw": raw_trimmed,
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

    # 调试预览: 打印前3条精简后的结果，方便在Actions日志里核对字段对不对
    print("预览前几条 (调试用):")
    for d in deals[:3]:
        preview = {k: v for k, v in d.items() if k not in ("_raw", "summary")}
        print(" ", json.dumps(preview, ensure_ascii=False))

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
