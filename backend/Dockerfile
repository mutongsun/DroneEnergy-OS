FROM python:3.11-slim

WORKDIR /app

# 先装依赖再拷代码，充分利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

EXPOSE 8000

# 启动链：迁移 → 演示账号种子 → 服务；任一步失败容器即退出（fail-fast）
CMD ["sh", "-c", "alembic upgrade head && python -m app.auth.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
