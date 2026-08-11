#!/usr/bin/env bash
# WHYFXPG 一键私有化部署脚本（P06）
#
# 用法:
#   curl -fsSL https://<release-url>/install.sh | bash
#   或本地:
#   bash scripts/self-hosted/install.sh
#
# 流程:
#   1. 检测 docker / docker compose
#   2. 生成 .env（随机 SECRET_KEY / PostgreSQL 密码）
#   3. docker compose up -d --build（api + worker + postgres + redis + minio）
#   4. 等待 api 健康检查通过
#   5. 提示创建管理员账户
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== WHYFXPG 一键部署 ==="

# 1. 环境检测
command -v docker >/dev/null 2>&1 || { echo "❌ 未检测到 docker，请先安装: https://docs.docker.com/get-docker/"; exit 1; }
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "❌ 未检测到 docker compose，请安装 Compose v2"; exit 1
fi
echo "✅ docker + compose 已就绪 ($($COMPOSE version --short 2>/dev/null || echo compose))"

# 2. 生成 .env（幂等：已存在则保留）
if [ ! -f .env ]; then
  SECRET_KEY="$(openssl rand -hex 32 2>/dev/null || python -c 'import secrets;print(secrets.token_hex(32))')"
  POSTGRES_PASSWORD="$(openssl rand -hex 16 2>/dev/null || python -c 'import secrets;print(secrets.token_hex(16))')"
  cat > .env <<EOF
SECRET_KEY=${SECRET_KEY}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
WHYFXPG_WORKER_INTERVAL_H=6
EOF
  echo "✅ 已生成 .env（SECRET_KEY / POSTGRES_PASSWORD）"
else
  echo "✅ .env 已存在，保留现有配置"
fi

# 3. 启动服务
echo "=== 构建并启动服务 (api/worker/postgres/redis/minio) ==="
$COMPOSE up -d --build

# 4. 等待健康检查
echo "=== 等待 API 就绪 ==="
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "✅ API 已就绪: http://localhost:8000  (Swagger: /docs)"
    break
  fi
  [ "$i" -eq 60 ] && { echo "❌ API 60 秒内未就绪，请查看日志: $COMPOSE logs api"; exit 1; }
  sleep 2
done

# 5. 管理员账户
echo ""
echo "=== 创建管理员账户 ==="
echo "执行以下命令创建初始企业账户（需在项目根目录，.venv 或容器内）:"
echo "  DATABASE_URL=\$(grep -E '^DATABASE_URL' .env 2>/dev/null || echo postgresql://whyfxpg:\$(grep POSTGRES_PASSWORD .env | cut -d= -f2)@localhost:5432/whyfxpg) \\"
echo "  python scripts/self-hosted/bootstrap_admin.py --company '我的企业' --plan enterprise"
echo ""
echo "✅ 部署完成。查看状态: $COMPOSE ps ; 日志: $COMPOSE logs -f api"
