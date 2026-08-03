"""
fetch_coupons.py
=================
从 Involve Asia Publisher API 拉取所有带优惠码(voucher_code)的 campaign，
写入 coupons.json，供静态网页用 JS 直接读取。

设计给 GitHub Actions 用:
- 凭证从环境变量读取 (INVOLVE_ASIA_KEY / INVOLVE_ASIA_SECRET)，由 GitHub Secrets 注入
- 每次跑都是全新进程，所以不需要处理"token过期"这种跨次调用的缓存问题，
  一次认证用完这次运行就够了
- 输出结构先保留API返回的原始字段 + 少量顶层元信息，
  等你看到真实响应长什么样之后，再决定网页具体要用哪些字段做筛选/精简
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


def fetch_all_coupon_campaigns(token: str, extra_filters: dict | None = None) -> list:
    """分页拉完所有 coupons_only=true 的 campaign"""
    rows = []
    page = 1
    limit = 100  # /campaigns/all 的分页上限是100
    while True:
        data = {"page": page, "limit": limit, "filters[coupons_only]": "true"}
        if extra_filters:
            for k, v in extra_filters.items():
                data[f"filters[{k}]"] = v
        resp = request_with_backoff("POST", "/campaigns/all", token, data=data)
        block = resp["data"]
        rows.extend(block["data"])
        print(f"  第{page}页: 拉到{len(block['data'])}条, 累计{len(rows)}/{block['count']}")
        if page * block["limit"] >= block["count"]:
            break
        page += 1
    return rows


def main():
    key = os.environ.get("INVOLVE_ASIA_KEY")
    secret = os.environ.get("INVOLVE_ASIA_SECRET")
    if not key or not secret:
        print("缺少 INVOLVE_ASIA_KEY / INVOLVE_ASIA_SECRET 环境变量", file=sys.stderr)
        sys.exit(1)

    # 你可以在这里加国家/分类过滤，例如只要马来西亚:
    # extra_filters = {"country": "Malaysia"}
    extra_filters = None

    print("正在认证...")
    token = authenticate(key, secret)

    print("正在拉取优惠券 campaigns...")
    coupons = fetch_all_coupon_campaigns(token, extra_filters)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(coupons),
        "coupons": coupons,
    }

    with open("coupons.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完成，写入 coupons.json，共 {len(coupons)} 条")


if __name__ == "__main__":
    main()
