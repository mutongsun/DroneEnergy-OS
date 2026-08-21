# DroneEnergy-OS 无人机热电监控平台

企业级全栈演示项目：无人机传感器数据实时接入（WebSocket）→ 时序落库（MySQL）→ 实时可视化（Vue3 + ECharts + Three.js）→ AI 能源诊断（DeepSeek，含熔断降级）→ 全链路可观测（Prometheus + Grafana）→ CI/CD 门禁（GitHub Actions）。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 + Alembic + PyMySQL |
| 实时 | WebSocket + Redis PubSub（跨副本广播） |
| AI | DeepSeek（AsyncOpenAI 协议，熔断器 + fallback 降级） |
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + ECharts + Three.js |
| 基础设施 | Docker Compose + Nginx（SPA + 反代） |
| 可观测性 | Prometheus（指标 + 告警）+ Grafana（自动置备看板）+ 结构化日志（trace_id 串联） |
| 质量门禁 | ruff（lint + format）+ mypy + pytest（覆盖率门禁）+ ESLint + vue-tsc + vitest |

## 快速开始

```bash
# 1. 启动核心栈（MySQL/Redis/后端/前端/模拟器）
docker compose up -d --build

# 2. 可选：启动监控栈（Prometheus + Grafana）
docker compose --profile monitoring up -d
```

| 入口 | 地址 | 凭据 |
|---|---|---|
| 前端 | http://localhost:5173 | 见下方 RBAC 账号表 |
| API | http://localhost:8001 | Bearer JWT |
| API 文档（Swagger） | http://localhost:8001/docs | — |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus 告警 | http://localhost:9090/alerts | — |

> 端口说明：宿主机 3306/6379/8000 常被本机其他服务占用，故对外映射 3307/6380/8001；容器间通信走内部网络不受影响。

### 模拟器

`fake-data` 容器模拟 3 架无人机（drone_id 1/2/3，机型 DJI_Mavic3 / XAG_P80Pro）：
- 1Hz 传感器帧经 `/ws/upload/{drone_id}` 实时推送（20 维遥测）
- 每 10 帧聚合批量 `POST /api/v1/sensor/batch` 落库（JWT 认证）
- 后端重新部署导致 WS 断开时自动重连

### 多副本验证

WS 广播经 Redis PubSub 扇出，天然支持后端水平扩展：

```bash
docker compose up -d --scale backend=2
```

---

## RBAC 权限说明

### 角色模型

| 角色 | 权限范围 | 说明 |
|---|---|---|
| `admin` | **全部权限**（隐式放行） | rbac.py 中 `user.role == "admin"` 直接通过，无需在各端点枚举 |
| `operator` | 读 + 写 | 业务操作：设备管理、数据上报、AI 诊断 |
| `viewer` | 只读 | 仅查看：设备列表/详情、历史曲线、实时监控 |

实现位于 [backend/app/auth/rbac.py](backend/app/auth/rbac.py)：

```python
def require_roles(*roles: str) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role == "admin" or user.role in allowed:
            return user
        raise HTTPException(status_code=403, detail=f"需要以下角色之一：{...}")
    return checker
```

设计要点：
- **认证与授权分层**：`get_current_user` 只验 JWT（无效/过期统一 401），`require_roles` 再验角色（403）
- **admin 隐式放行**：新增端点写 `require_roles("operator")` 即同时覆盖 operator + admin
- **前端按钮可见性**（`auth.canWrite`）仅为 UX 优化，真正的权限校验始终在后端

### 演示账号（seed 幂等注入）

| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | admin |
| operator | operator123 | operator |
| viewer | viewer123 | viewer |

> 生产实践注记：真实系统应通过受控 CLI 注入账号并强制首次改密，默认口令仅为本地演示便利。

### 端点 × 角色矩阵

| 端点 | 方法 | viewer | operator | admin |
|---|---|:---:|:---:|:---:|
| `/api/v1/auth/login` | POST | 公开 | 公开 | 公开 |
| `/api/v1/auth/me` | GET | ✅ | ✅ | ✅ |
| `/api/v1/health` | GET | 公开 | 公开 | 公开 |
| `/api/v1/drones`（列表/详情） | GET | ✅ | ✅ | ✅ |
| `/api/v1/drones`（创建） | POST | ❌ 403 | ✅ | ✅ |
| `/api/v1/drones/{id}`（更新） | PATCH | ❌ 403 | ✅ | ✅ |
| `/api/v1/drones/{id}`（删除） | DELETE | ❌ 403 | ✅ | ✅ |
| `/api/v1/sensor/history/{id}` | GET | ✅ | ✅ | ✅ |
| `/api/v1/sensor/batch` | POST | ❌ 403 | ✅ | ✅ |
| `/api/v1/ai/diagnose` | POST | ❌ 403 | ✅ | ✅ |
| `/ws/realtime/{id}` | WS | ✅（任意认证用户可观看） | ✅ | ✅ |
| `/ws/upload/{id}` | WS | ❌ 4403 | ✅ | ✅ |

> WS 认证说明：浏览器 WebSocket API 不支持自定义请求头，故采用查询参数传令牌
> （`/ws/realtime/1?token=<jwt>`）。认证失败以自定义关闭码标识：`4401`（令牌
> 缺失/无效/过期）、`4403`（角色不足），客户端据此引导重新登录。

错误码约定：
- `401 Unauthorized` — 未携带/无效/过期令牌（前端拦截器自动清凭据跳登录页）
- `403 Forbidden` — 令牌有效但角色不足

---

## API 概览

完整契约见 Swagger（`/docs`）。核心端点：

```bash
# 登录换发 JWT（8 小时有效期）
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "operator", "password": "operator123"}'

# 设备分页列表（status/model 筛选）
curl "http://localhost:8001/api/v1/drones?page=1&page_size=10&status=flying" \
  -H "Authorization: Bearer $TOKEN"

# 历史曲线（最近 N 分钟，升序，limit ≤ 2000）
curl "http://localhost:8001/api/v1/sensor/history/1?minutes=10&limit=600" \
  -H "Authorization: Bearer $TOKEN"

# AI 能源诊断（DeepSeek；模型不可用时返回 fallback 建议，仍 200）
curl -X POST http://localhost:8001/api/v1/ai/diagnose \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"drone_id": 1, "query": "SOC 下降过快怎么办？"}'
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:root123@localhost:3306/drone_energy` | 连接串（生产务必改密） |
| `REDIS_URL` | `redis://localhost:6379/0` | WS 广播通道 |
| `DEEPSEEK_API_KEY` | `""` | AI 密钥（空则诊断走 fallback） |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | — |
| `DEEPSEEK_TIMEOUT` | `30.0` | 秒 |
| `JWT_SECRET` | `change-me-in-prod` | **生产必须更换** |
| `JWT_EXPIRE_MINUTES` | `480` | — |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | — |
| `WS_HEARTBEAT_INTERVAL` | `30` | 秒 |

---

## 可观测性

### Prometheus 指标（`GET /metrics`）

| 指标 | 类型 | 含义 |
|---|---|---|
| `http_requests_total{method,route,status}` | Counter | HTTP 请求计数（路由模板，低基数） |
| `http_request_duration_seconds` | Histogram | HTTP 耗时分布 |
| `ws_active_connections` | Gauge | 当前 WS 连接数 |
| `ws_messages_sent_total{drone_id}` | Counter | WS 下行帧数 |
| `sensor_frames_received_total` / `sensor_frames_written_total` | Counter | 帧接收/落库数 |
| `ai_calls_total{status=ok\|error\|circuit_open}` | Counter | AI 调用结果 |
| `ai_call_duration_seconds` | Histogram | AI 耗时 |
| `db_pool_in_use` | Gauge | 数据库连接池借出数 |

### 告警规则（5 条）

| 规则 | 级别 | 条件 |
|---|---|---|
| HttpHighErrorRate | critical | 5xx 错误率 > 5%，持续 5m |
| HttpSlowP95 | warning | P95 延迟 > 1s，持续 10m |
| AiServiceDegraded | warning | AI 10 分钟内失败 ≥ 5 次 |
| SensorDataStreamBroken | warning | 帧接收速率归零 3m（模拟器停跑时误报） |
| WebSocketConnectionsDropped | warning | WS 连接 5 分钟内下降 > 3 |

Grafana 看板（9 面板）与数据源经 provisioning 自动加载，无需手工导入。

---

## CI/CD

`.github/workflows/backend.yml`（后端）与 `frontend.yml`（前端）：

```
push/PR → lint → format 检查 → 类型检查（mypy / vue-tsc）
        → 单测（pytest 覆盖率门禁 50% / vitest）
        → build → 镜像推送 ghcr.io（仅 main）
```

- 同分支新推送自动取消旧流水线（concurrency 控制）
- 镜像名强制小写（GHCR 约束）
- PR 只做质量门禁不推镜像

本地对齐 CI 门禁：

```bash
# 后端（backend/ 目录）
ruff check app tests && ruff format --check app tests && mypy app && pytest --cov=app --cov-fail-under=50

# 前端（frontend/ 目录）
npm run lint && npm run typecheck && npm run test && npm run build
```

---

## 压测报告模板

> 复制以下模板到 `docs/load-test-report-YYYYMMDD.md`，按实际压测数据填写。
> 推荐工具：[Locust](https://locust.io/)（Python 生态，支持自定义协议与 WebSocket 场景）。

### 1. 测试概述

| 项 | 内容 |
|---|---|
| 测试日期 | YYYY-MM-DD |
| 执行人 | |
| 版本/Commit | （`git rev-parse --short HEAD`） |
| 测试目标 | 例：验证单副本后端在 100 并发观看 + 3 路模拟器上报下的稳定性 |
| 环境 | 本地 Docker / 云主机（CPU? 内存?） |

### 2. 拓扑与数据准备

- 部署方式：`docker compose up -d [--scale backend=N]`
- 模拟器：3 架无人机 1Hz 推流（`fake-data` 容器）
- 压测机与被测机隔离（避免 CPU 争抢污染数据）
- 预热：正式采集前先跑 2 分钟预热流量

### 3. 场景与结果

#### 场景 A：REST 读负载（历史曲线查询）

```
locust -f locustfile.py --headless -u 100 -r 10 -t 5m \
  --csv result_rest  # 100 并发，10/s 爬坡，5 分钟
```

| 指标 | 目标 | 实测 | 结论 |
|---|---|---|---|
| RPS | ≥ 200 | | |
| P95 延迟 (ms) | < 500 | | |
| P99 延迟 (ms) | < 1000 | | |
| 错误率 | < 0.1% | | |
| DB 连接池峰值 (`db_pool_in_use`) | < 上限 80% | | |

#### 场景 B：实时订阅扇出（WS 广播）

```
# N 个观看端并发订阅 /ws/realtime/{drone_id}，持续 5 分钟
# 关注：每端是否稳定收到 ~1Hz 帧（60 帧/分钟）
```

| 指标 | 目标 | 实测 | 结论 |
|---|---|---|---|
| 订阅端数 | 100 | | |
| 每端帧率 (帧/分) | ≈ 60 | | |
| 断连数 | 0 | | |
| `ws_messages_sent_total` 增速 | N×60/分 | | |
| 后端 CPU | < 70% | | |

#### 场景 C：批量写入（`POST /api/v1/sensor/batch`）

| 指标 | 目标 | 实测 | 结论 |
|---|---|---|---|
| 并发上报路数 | 10 | | |
| 单批帧数 | 100（上限） | | |
| 落库速率 (帧/秒) | ≥ 500 | | |
| `sensor_frames_written_total` 增速 | 与压测端一致 | | |
| MySQL 写延迟 P95 (ms) | < 200 | | |

#### 场景 D：AI 诊断（熔断验证）

| 指标 | 目标 | 实测 | 结论 |
|---|---|---|---|
| 并发诊断请求 | 20 | | |
| 熔断开启条件 | 连续 3 次失败 | | |
| 熔断期间响应时间 (ms) | < 50（零外呼） | | |
| fallback 返回率 | 100%（AI 不可用时） | | |
| `ai_calls_total{circuit_open}` 计数 | > 0 | | |

### 4. 瓶颈与结论

```text
1. 主要瓶颈：
   （例：REST 读负载在 X 并发时 db_pool_in_use 打满，P95 抖升 → 建议连接池上调/加读副本）
2. 容量结论：
   （例：单副本可支撑 N 并发观看 + M 路上报；--scale backend=2 后线性扩展）
3. 遗留问题：
   （例：WS 端点暂无认证，公网暴露前需补令牌握手）
```

### 5. 附：压测期间监控截图

> Grafana 看板（http://localhost:3001）在压测窗口内的关键面板截图：
> - HTTP QPS / P95 延迟
> - WS 活跃连接与消息速率
> - DB 连接池占用
> - CPU / 内存

---

## 项目结构

```
DroneEnergy-OS/
├── backend/
│   ├── app/
│   │   ├── main.py               # 入口：中间件/指标/生命周期接线
│   │   ├── config.py             # pydantic-settings 环境配置
│   │   ├── models.py             # ORM（分区表仅映射列，DDL 走迁移）
│   │   ├── auth/                 # JWT 登录、RBAC、演示种子
│   │   ├── drones/               # 设备 CRUD（分页 + 筛选）
│   │   ├── sensors/              # 批量入库 + 历史查询
│   │   ├── ai/                   # DeepSeek 客户端（熔断）+ 诊断端点
│   │   ├── websocket/            # 连接管理器 + 上传/订阅端点分离
│   │   ├── middleware/           # TraceId / 指标中间件
│   │   └── monitoring/           # 指标注册 + 结构化日志
│   ├── alembic/                  # 迁移（分区表原生 DDL）
│   └── tests/                    # 50 个测试（SQLite 内存库）
├── frontend/
│   └── src/
│       ├── views/                # 登录 / 实时监控（3D+AI）/ 设备管理
│       ├── components/           # RealtimeChart / Drone3D / AiPanel
│       ├── composables/          # useRealtime（WS 订阅 + 滚动缓冲）
│       ├── stores/               # Pinia auth
│       └── api/                  # axios 封装（401 统一收口）
├── fake_data_generator/          # 3 机模拟器（共享 ClientSession + 重连）
├── monitoring/                   # Prometheus 配置/告警 + Grafana 置备
├── docs/                         # 设计方案 / 压测报告
└── docker-compose.yml
```

## 测试

```bash
cd backend
pytest --cov=app --cov-report=term --cov-fail-under=75   # 58 个用例，覆盖率门禁 75%
```

覆盖模块：auth（登录/JWT/RBAC）、drones CRUD、sensor 入库+历史、AI 诊断（替身客户端，不打真实 API）、WS 管理器（广播/幂等清理/心跳取消）、WS 端点认证（4401/4403 关闭码、角色矩阵）、熔断器状态机、可观测性（TraceId/指标）。

前端：`cd frontend && npm run test`（vitest，WS 解析 / 滚动缓冲 / auth store）。

## 路线图状态

- [x] Week 1：后端框架 + Alembic 建表 + JWT + 设备 CRUD + CI 门禁
- [x] Week 2：WS 实时链路（生产者/消费者分离）+ Redis 广播 + Vue3 前端 + ECharts
- [x] Week 3：Three.js 3D 姿态 + DeepSeek 诊断（熔断 + fallback）+ 历史查询
- [x] Week 4：RBAC 文档 + 压测报告模板 + README
- [x] Week 5：WS 端点令牌认证（4401/4403 关闭码）+ 3D 姿态可感知化（HUD/机头标记/最短路径插值）+ 模拟器姿态平滑模型 + 连接池扩容 + 压测实测回填（[docs/load-test-report-20260821.md](docs/load-test-report-20260821.md)）+ 覆盖率门禁上调 75%
- [x] 压测驱动修复：WS 握手期 event loop 死锁（100 并发观看曾令后端假死，v4 修复后零断连稳态 1Hz）+ 历史查询减列（串行 3.4x）
