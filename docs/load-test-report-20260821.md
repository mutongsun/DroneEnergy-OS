# 压测实测报告（2026-08-21）

> 按 [README 压测报告模板](../README.md#压测报告模板) 结构填写。
> 本次压测直接暴露并驱动修复了 **WS 扇出链路的 event loop 死锁**（重大缺陷），
> 修复前后对比数据见场景 B。

## 1. 测试概述

| 项 | 内容 |
|---|---|
| 测试日期 | 2026-08-21 |
| 执行人 | 开发组 |
| 版本/Commit | `4b14f03` + 压测期间热修复（v4 WS 池级修复、历史查询减列，见第 4 节） |
| 测试目标 | 验证单副本后端在 40 并发 REST 读 + 100 并发 WS 观看 + 3 路模拟器上报下的稳定性 |
| 环境 | 本地 Docker（WSL2 后端，宿主机 16GB/多核）；MySQL 8.0 + Redis 7 单实例 |

## 2. 拓扑与数据准备

- 部署方式：`docker compose up -d`（backend 单副本，宿主机 8001 → 容器 8000）
- 模拟器：3 架无人机 1Hz 推流（fake-data 容器，容器内网直连 `backend:8000`）
- 压测位置（重要，影响数据解读）：
  - **宿主机路径**：Locust / 早期探针经 Windows Docker 端口代理（`localhost:8001`）
  - **容器内路径**：`loadtest_ws.py` / `probe_http.py` 拷入 backend 容器直连 `localhost:8000`，隔离代理损耗
- 预热：WS 场景前小样本（5 客户端）回归通过后再放全量

## 3. 场景与结果

### 场景 A：REST 读负载（历史曲线查询 + 设备列表）

```
locust -f locustfile.py --headless -u 40 -r 10 --csv result_rest
```

| 指标 | 目标 | 实测 | 结论 |
|---|---|---|---|
| RPS（聚合） | ≥ 200 | 47.1 | ❌ 未达标（见瓶颈 3） |
| P95 延迟 (ms) | < 500 | 2000 | ❌ |
| P99 延迟 (ms) | < 1000 | 2300 | ❌ |
| 错误率 | < 0.1% | **0%**（8422 请求 0 失败） | ✅ |
| DB 连接池峰值 | < 上限 80% | 池扩容后无池级超时 | ✅（10+20 → 30+30） |

分端点明细（Locust，宿主机代理路径）：

| 端点 | 请求数 | RPS | P50 | P95 | P99 |
|---|---|---|---|---|---|
| `GET /api/v1/sensor/history/{id}`（~40KB） | 6273 | 35.1 | 1300ms | 2000ms | 2400ms |
| `GET /api/v1/drones`（~0.4KB） | 2049 | 11.5 | 560ms | 1000ms | 1200ms |
| `POST /api/v1/auth/login` | 100 | 0.6 | 250ms | 610ms | 690ms |

容器内直连对照（`probe_http.py`，40 并发 × 20 请求，隔离代理）：

| 端点 | 路径 | RPS | P50 |
|---|---|---|---|
| `GET /api/v1/drones` | 宿主机代理 | 11.5 | 560ms |
| `GET /api/v1/drones` | 容器内直连 | **175.8** | 222ms |
| `GET /api/v1/sensor/history/{id}` | 宿主机代理 | 35.1 | 1300ms |
| `GET /api/v1/sensor/history/{id}` | 容器内直连 | 31.6 | 1251ms |

> 解读：小响应端点（/drones）经 Windows Docker 端口代理吞吐损失 ~15 倍；
> 大响应端点（/history）代理与直连持平——瓶颈不在网络路径，在应用层（见瓶颈 3）。

### 场景 B：实时订阅扇出（WS 广播）

```
# 容器内直连，隔离 Windows 代理对长连接的干扰
docker cp loadtest_ws.py <backend>:/tmp/
docker exec <backend> python /tmp/loadtest_ws.py --clients 100 --duration 180
```

| 指标 | 目标 | 实测（修复后） | 结论 |
|---|---|---|---|
| 订阅端数 | 100 | 100（`ws_active_connections=100` 全保持） | ✅ |
| 每端帧率 (帧/分) | ≈ 60 | 53.3（稳态 ≈59.6 ≈ 1Hz） | ✅ |
| 断连数 | 0 | **0** | ✅ |
| `ws_messages_sent_total` 增速 | N×60/分 | 3 机合计 ~160 帧/分 × 33 端/机 | ✅ |
| 后端 CPU | < 70% | 3.64% | ✅ |
| db_pool_in_use（稳态） | — | **0** | ✅（握手后即归还） |

**修复前后对比**（同一脚本、同一拓扑、同一数据流）：

| 指标 | 修复前（v3 认证实现） | 修复后（v4 池级修复） |
|---|---|---|
| 每端帧率 (帧/分) | 0.0–0.3 | 53.3（稳态 ≈1Hz） |
| 断连数（180s 内） | 1572（57×1006 + 1515 次拒连） | **0** |
| 总帧送达 | 40 | **16000** |
| 压测后 /health | **超时假死**（10s 无响应，CPU 0%） | 4ms 正常 |

> 首帧延迟 p50=19.3s 为压测窗口起点恰逢后端重启后模拟器重连退避（非后端瓶颈）；
> 5 客户端回归场景下首帧延迟 0.99s（正常范围）。

### 场景 C：批量写入（`POST /api/v1/sensor/batch`）

| 项 | 说明 |
|---|---|
| 状态 | 未单独施压 |
| 背景写入 | 全程存在：3 架无人机 1Hz × 10 帧批量入库（稳态背景负载），压测期间 A/B 场景零错误、写入指标 `sensor_frames_written_total` 持续正常递增 |
| 遗留 | 专项写入压测（10 路并发上报 ≥500 帧/秒）待生产环境复测时补做 |

### 场景 D：AI 诊断（熔断验证）

| 项 | 说明 |
|---|---|
| 状态 | 未单独施压（单元测试覆盖熔断状态机与 fallback 100% 返回，见 `test_ai_circuit_breaker.py`） |
| 遗留 | 真实 DeepSeek API 的并发诊断施压待生产环境复测时补做 |

## 4. 瓶颈与结论

```text
1. 主要瓶颈与修复（本次压测核心产出）：

   ① WS 握手期 event loop 死锁（已修复，致命级）
      现象：100 并发观看端令后端整体假死（连 /health 都无响应），
            CPU 却为 0% —— 典型互等死锁特征。
      根因（两层叠加）：
      a) v3 认证在 async 端点内直接调用同步 db.get()：连接池耗尽时
         在 event loop 上同步等待，而归还连接的协程又需要 event loop
         调度——互等死锁。REST 不受影响（get_current_user 是 sync
         依赖，FastAPI 自动放线程池）。
      b) DB 会话随依赖注入存活到端点返回——WS 端点是无限循环，每个
         观看端在整条连接生命周期占用一个池连接，100 端必然打爆
         30+30=60 的池上限。
      修复（websocket/router.py v4）：
      - 认证查询经 run_in_threadpool 执行（不再阻塞 event loop）
      - 握手认证后立即 db.close() 归还（close 幂等，不影响依赖 teardown）
      验证：100 端 × 180s 零断连、稳态 1Hz、db_pool_in_use=0。

   ② REST 历史查询并发扩展性（部分缓解，遗留）
      现象：DB 层对照实验（固定 ~577 行）——
        SELECT *（22 列）：串行 24~32ms，40 并发 P50 1.9~2.4s（劣化 ~80 倍）
        9 列精简：        串行 7~9.5ms（3.4x），40 并发 P50 1.7~2.1s（仅 ~10%）
      排除项：连接层健康（SELECT 1 在 60 并发下 RPS 580、延迟线性）；
              MySQL 无辜（压测期间 CPU 仅 10%）；索引命中（idx_drone_time
              完全覆盖查询模式）；连接复用无关（预热后第二轮无改善）。
      定性：backend CPU ~150%（GIL 边界），瓶颈在 PyMySQL 纯 Python 驱动
            的结果集解析/Decimal 转换在 GIL 下的串行化叠加。
      已做：历史查询减列（SELECT * → HistoryPoint 所需 9 列），
            串行 3.4x、响应体 ~50% 缩减；并发下收益有限。
      遗留：迁移 mysqlclient（C 扩展驱动，解析释放 GIL）或加读副本。

   ③ Windows Docker 端口代理（环境项，非应用缺陷）
      小响应端点吞吐损失 ~15 倍（/drones 代理 11.5 RPS vs 直连 175.8），
      并诱发 WS 长连接雪崩（早期宿主机压测 1173 次拒连）。容器内直连
      复测后排除该变量。生产部署于 Linux 原生环境不受影响。

2. 容量结论：
   - 单副本稳定支撑：100 并发 WS 观看（1Hz 完整扇出、零断连、CPU <5%）
     + 3 路模拟器上报 + 40 并发 REST 读（零错误）。
   - REST 读吞吐上限：设备列表 ~176 RPS（直连）；历史查询 ~24-32 RPS
     @40 并发（P50 ~1.3s，受瓶颈 ② 限制）。演示与答辩场景富余。

3. 遗留问题：
   - PyMySQL → mysqlclient 驱动迁移（突破瓶颈 ② 的根治路径）
   - 场景 C（专项写入施压）与场景 D（真实 AI 并发诊断）待补
   - 多副本验证：--scale backend=2 的线性扩展与 Redis PubSub 跨副本
     广播行为已具备支持（v2 设计），待生产环境实测
   - WS 令牌经查询参数传递会进入访问日志，生产环境建议改用
     子协议头（Sec-WebSocket-Protocol）或短时一次性 ticket
```

## 5. 复现方式

| 场景 | 命令 |
|---|---|
| REST 读负载 | `locust -f locustfile.py --headless -u 40 -r 10 --csv result_rest` |
| WS 扇出 | `docker cp loadtest_ws.py <backend>:/tmp/ && docker exec <backend> python /tmp/loadtest_ws.py --clients 100 --duration 180` |
| 容器内直连 HTTP 对照 | `docker cp probe_http.py <backend>:/tmp/ && docker exec <backend> python /tmp/probe_http.py 40 20` |

压测期间关键面板（Grafana http://localhost:3001）：
- HTTP QPS / P95 延迟、WS 活跃连接与消息速率、DB 连接池占用（`db_pool_in_use` 压测中段实测 0）。
