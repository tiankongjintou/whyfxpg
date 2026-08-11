#!/usr/bin/env python3
"""创建初始管理员账户（P06 install.sh 调用）。

用法（在项目根目录，需 DATABASE_URL 指向已迁移的 PostgreSQL）::

    DATABASE_URL=postgresql://whyfxpg:pass@localhost:5432/whyfxpg \
      python scripts/self-hosted/bootstrap_admin.py \
      --company "初始企业" --plan enterprise

- 生成随机 api_key，sha256 哈希写入 accounts.api_key_hash（与 P02 认证一致）。
- 明文 api_key 仅在 stdout 输出一次，请立即保存（服务端不存明文）。
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys

from sqlalchemy import create_engine, text

from whyfxpg.core.db import is_postgres_url
from whyfxpg.services.account_service import hash_api_key


def main() -> int:
    parser = argparse.ArgumentParser(description="创建初始管理员账户")
    parser.add_argument("--company", default="WHYFXPG Admin", help="企业名称")
    parser.add_argument("--plan", default="enterprise", help="套餐(默认 enterprise 无限额)")
    parser.add_argument("--quota", type=int, default=0, help="月度额度(enterprise 忽略)")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not is_postgres_url(db_url):
        print("❌ 需要 DATABASE_URL 指向 PostgreSQL", file=sys.stderr)
        return 1

    api_key = "whx_" + secrets.token_hex(16)
    api_key_hash = hash_api_key(api_key)
    prefix = api_key[:10]

    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO accounts "
                "(company_name, plan_type, api_key_hash, api_key_prefix, monthly_quota, status) "
                "VALUES (:company, :plan, :hash, :prefix, :quota, 'active') "
                "ON CONFLICT (api_key_hash) DO NOTHING "
                "RETURNING id"
            ),
            {"company": args.company, "plan": args.plan,
             "hash": api_key_hash, "prefix": prefix, "quota": args.quota},
        )
        row = result.mappings().first()
    engine.dispose()

    if row is None:
        print("❌ 账户创建失败（api_key_hash 冲突，重试即可生成新 key）", file=sys.stderr)
        return 1

    print("✅ 管理员账户已创建:")
    print(f"   company:    {args.company}")
    print(f"   plan_type:  {args.plan}")
    print(f"   account_id: {row['id']}")
    print("   api_key(仅此一次,请立即保存):")
    print(f"   {api_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
