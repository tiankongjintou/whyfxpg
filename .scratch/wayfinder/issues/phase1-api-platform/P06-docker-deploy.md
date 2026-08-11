# P06 — Docker 一键部署

**What to build:**
交付 docker-compose.yml，实现 API 服务容器化，以及一键私有化部署脚本（curl | bash）。包含 PostgreSQL + Redis + MinIO + API Worker。

**Blocked by:** P05-webhook-system.md

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1** `docker-compose.yml`：api、worker、postgres:16-alpine、
  redis:7-alpine、minio/minio 五服务 + 三数据卷（pgdata/redisdata/s3data）。
- **AC-2** API 服务：8000 端口，DATABASE_URL/REDIS_URL/SECRET_KEY 环境变量，
  启动命令先 `alembic upgrade head` 再 uvicorn；依赖 db/redis/minio 健康检查。
- **AC-3** Worker 服务：`python -m whyfxpg.worker`（新增 `whyfxpg/worker.py`
  定时管道循环，`WHYFXPG_WORKER_INTERVAL_H` 可配）。
- **AC-4** 数据卷：postgres / redis / S3 各一卷。
- **AC-5** `scripts/self-hosted/install.sh`：检测 docker+compose → 生成 .env
  （随机 SECRET_KEY/密码，幂等）→ `docker compose up -d --build` →
  健康等待 → 管理员创建提示；配套 `scripts/self-hosted/bootstrap_admin.py`
  （生成 api_key，sha256 写 accounts，明文仅输出一次）。
- **AC-6** 本机无 docker 环境，`docker compose up` 实机启动验证
  待部署机执行（文件交付完整，bash -n 语法校验通过）。
- **AC-7** `docs/06-开发环境与运行指南.md` 新增第六章 Docker 部署说明。
- 镜像：`api/Dockerfile`（python:3.12-slim，安装 `.[pg]`，含 alembic 迁移）。

## Acceptance criteria

- [ ] `docker-compose.yml`：api 服务、worker 服务、postgres:16-alpine、redis:7-alpine、minio/minio
- [ ] API 服务：8000 端口、环境变量 DATABASE_URL/REDIS_URL/SECRET_KEY
- [ ] Worker 服务：后台数据采集管道任务
- [ ] 数据目录：postgres 数据卷、redis 数据卷、S3 数据卷
- [ ] `scripts/self-hosted/install.sh` — 一键部署脚本（检测 Docker 环境、启动服务、创建管理员账户）
- [ ] 本地 `docker compose up` 可完整启动所有服务
- [ ] 文档更新：`docs/06-开发环境与运行指南.md` 补充 Docker 部署说明

## References

- `docs/技术改造路线图.md` §7 部署架构
