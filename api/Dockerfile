# WHYFXPG API / Worker 镜像（P06）
# build context 为项目根：docker compose build 时自动以 . 为 context
FROM python:3.12-slim

WORKDIR /app

# 时区与基础工具
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 先复制依赖清单以利用构建缓存
COPY pyproject.toml uv.lock ./
COPY whyfxpg ./whyfxpg
COPY whyfxpg_api ./whyfxpg_api
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# 安装依赖（含 pg 可选组:alembic/sqlalchemy/psycopg2）
RUN pip install --no-cache-dir ".[pg]"

EXPOSE 8000

# API 服务默认命令:先跑 schema 迁移,再启动 uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn whyfxpg_api.main:app --host 0.0.0.0 --port 8000"]
