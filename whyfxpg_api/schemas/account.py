"""账户响应 Schema。"""

from pydantic import BaseModel


class AccountOut(BaseModel):
    """账户公开信息（不含 api_key_hash / api_key_prefix）。"""

    account_id: str
    company_name: str
    plan_type: str
    monthly_quota: int
    status: str
