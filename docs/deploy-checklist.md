# 服务器部署完整检查清单

> 适用场景：Linux 云服务器首次部署 DroneEnergy-OS 测试环境。
> 按章节顺序逐项勾选，全部完成即可上线。日常更新见第 9 节（30 秒）。
> 配套文档：README「测试环境部署」章节（操作命令详解）。
>
> **提速提示**：章节 2/3/4/5/8 与 9 的服务器侧验证已自动化到
> [scripts/deploy-server.sh](../scripts/deploy-server.sh)（幂等一键脚本：
> 环境→仓库→.env→镜像→容器→健康检查→API 冒烟）。跑完脚本后，
> 手动勾选剩余项即可：§1 规格、§6 GitHub Secrets、§7 安全组、
> §9 浏览器体验项、§10 CD 链路、§11 可选项。

## 1. 服务器前置条件

- [ ] 规格满足最低要求：**2 核 CPU / 4GB 内存 / 40GB 磁盘**
  （实测各容器内存合计 ~1.5GB：backend 260MB + mysql 470MB + 其余 <100MB；
  加监控栈 grafana/prometheus 再 +100MB，4GB 留有余量）
- [ ] 操作系统：Ubuntu 22.04/24.04 或 Debian 12（x86_64；ARM 服务器需先在 CI 增加
  `platform: linux/arm64` 构建，否则镜像拉下来跑不起来）
- [ ] 可访问公网（拉 GHCR 镜像、git clone）
- [ ] 已知服务器公网 IP，且 SSH 可登录（记录下来，第 6 节要用）

## 2. 基础环境安装

- [ ] 安装 Docker + Compose 插件：
  `curl -fsSL https://get.docker.com | sh`
- [ ] 安装 git 与 curl：`sudo apt-get install -y git curl`
- [ ] 当前用户加入 docker 组：`sudo usermod -aG docker $USER`，**重新登录生效**
- [ ] 验证：`docker version && docker compose version`
  （compose 需 v2.24+——prod 配置用了 `!override` 标签收敛端口，
  get.docker.com 安装的版本均满足）
- [ ] 验证免 sudo：`docker ps` 不报 permission denied

## 3. 仓库与部署目录

- [ ] 克隆仓库到约定目录（deploy.yml 硬编码此路径）：
  `git clone https://github.com/mutongsun/DroneEnergy-OS.git /opt/droneenergy-os`
- [ ] 验证关键文件存在：
  `ls /opt/droneenergy-os/docker-compose.yml /opt/droneenergy-os/docker-compose.prod.yml`
- [ ] git 凭据可用（deploy 时会 `git pull --ff-only`；私有仓库需配 PAT 或 deploy key）

## 4. 环境变量（.env）

- [ ] 从模板创建：`cp .env.example .env && vim .env`
- [ ] `MYSQL_ROOT_PASSWORD`：**必改**，强密码（生成：`openssl rand -hex 16`）
  - 注意：MySQL 仅在数据卷**首次初始化**时读取此变量。部署后想改密码，
    需 `docker compose down -v` 删卷重来（会清空历史数据，测试环境可接受）
- [ ] `JWT_SECRET`：**必改**，随机长串（生成：`openssl rand -hex 32`）
  （不改则所有 JWT 可被公开仓库里的默认值伪造）
- [ ] `DEEPSEEK_API_KEY`：填写（留空则 AI 诊断走本地 fallback，页面仍可用）
- [ ] `API_USER` / `API_PASSWORD`：默认 operator/operator123 即可
  （模拟器上报账号，seed 的演示账号，测试环境不必改）
- [ ] 权限收紧：`chmod 600 .env`
- [ ] 确认 `.env` 不会被误提交：仓库 `.gitignore` 已排除，无需操作

## 5. GHCR 镜像访问（三选一）

- [ ] 方案 A（推荐）：服务器 docker login 拉私有镜像
  - GitHub → Settings → Developer settings → Personal access tokens (classic)
    → Generate new token，勾选 **read:packages**
  - 服务器执行：`echo <PAT> | docker login ghcr.io -u mutongsun --password-stdin`
  - 验证：`docker pull ghcr.io/mutongsun/droneenergy-os/backend:latest` 成功
- [ ] 方案 B：把三个包设为 public（GitHub 仓库右侧 Packages → 各包 Settings →
  Change visibility），跳过 login（镜像不含密钥，运行时经 .env 注入）
- [ ] 方案 C：服务器上免 login，仅当包已 public 时有效
- [ ] 确认三个镜像在 CI 均已产出（Actions 里 Backend CI 与 Frontend CI 全绿，
  包列表有 backend / frontend / fake-data 三个 latest）

## 6. GitHub Secrets（仓库侧配置）

- [ ] 本地生成部署专用密钥对：
  `ssh-keygen -t ed25519 -f droneenergy-deploy -C "github-actions-deploy"`
- [ ] 公钥追加到服务器：`cat droneenergy-deploy.pub >> ~/.ssh/authorized_keys`
- [ ] 验证免密登录：`ssh -i droneenergy-deploy <user>@<server> hostname` 成功
- [ ] 仓库 Settings → Secrets and variables → Actions，添加三个 Secret：
  - [ ] `TEST_SSH_HOST` = 服务器 IP/域名
  - [ ] `TEST_SSH_USER` = SSH 用户名（须在 docker 组）
  - [ ] `TEST_SSH_KEY` = 私钥文件**完整内容**（含 BEGIN/END 行）
- [ ] 验证：Actions 页面已出现 "Deploy (test)" workflow（手动触发型）

## 7. 网络与端口安全

- [ ] 云安全组**只放行**：22（SSH，建议限来源 IP）+ 5173（前端入口）
- [ ] 明确不放行：3306/3307（MySQL）、6379/6380（Redis）、8000/8001（backend 直连）
  - prod 配置已做端口收敛：mysql/redis 零映射、backend 仅绑 127.0.0.1，
    即使安全组漏配，公网也扫不到——两层防御
- [ ] 踩坑提示：**UFW 拦不住 Docker 端口映射**（Docker 的 iptables DOCKER 链
  优先于 ufw INPUT 链）。端口管控必须靠云安全组或 `!override` 绑定，
  不要依赖 ufw enable
- [ ] 可选加固：`sudo ufw allow 22 && sudo ufw enable`（仅保护非容器服务）

## 8. 首次部署执行

- [ ] 服务器上首次启动（与 CD 后续部署同一命令序列）：
  ```bash
  cd /opt/droneenergy-os
  docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build
  ```
- [ ] 观察启动日志：backend 容器先跑 Alembic 迁移 + seed 演示账号再起服务，
  MySQL 健康检查通过后才开始，**全程约 30~60 秒属正常**
- [ ] 容器状态五绿：`docker compose -f docker-compose.yml -f docker-compose.prod.yml ps`
  （backend / frontend / fake-data / mysql / redis 均 Up，mysql 带 healthy）
- [ ] 服务器本机健康检查：`curl -s http://localhost:8001/api/v1/health` 返回 200

## 9. 部署后功能验证（浏览器）

- [ ] 访问 `http://<服务器IP>:5173` 出现登录页（前端 nginx 已反代
  /api/ 与 /ws/，同源无 CORS 问题）
- [ ] **登录**：viewer / viewer123 能登录
- [ ] **实时曲线**：监控页传感器曲线持续刷新（≈1Hz，模拟器 fake-data 在推流）
- [ ] **3D 姿态**：无人机 3D 模型随姿态平滑联动，HUD 读数变化
- [ ] **RBAC 生效**：viewer 调 AI 诊断按钮应被拒（403）；换 operator /
  operator123 登录可用 AI 诊断面板（填了 DEEPSEEK_API_KEY 时返回模型结论，
  未填时返回 fallback 建议但仍是 200）
- [ ] **数据落库**：`docker compose -f docker-compose.yml -f docker-compose.prod.yml
  exec mysql mysql -uroot -p<密码> drone_energy -e "SELECT COUNT(*) FROM sensor_snapshots;"`
  间隔一分钟查两次，行数递增
- [ ] **历史曲线页**：能拉出最近 10 分钟曲线（REST 链路 + DB 读取正常）
- [ ] **WS 长连接稳定**：实时页面挂 5 分钟以上不断流（nginx read_timeout
  已配 3600s，服务端心跳 30s）

## 10. CD 链路验证（GitHub → 服务器全自动）

- [ ] 本地随便改一行代码（或空提交）push 到 main
- [ ] 等 Backend CI + Frontend CI 全绿（镜像已更新到 GHCR）
- [ ] GitHub → Actions → **Deploy (test)** → Run workflow → 选 `deploy`
- [ ] 流水线四步全过：拉配置 → 拉镜像 → 滚动更新 → 健康检查 OK
- [ ] 浏览器验证改动生效（必要时 Ctrl+F5 强刷前端静态资源）
- [ ] 观察部署互斥：部署进行中再点一次 Run workflow 会排队而非并发执行

## 11. 可选项

- [ ] 监控栈（Prometheus + Grafana）：
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile monitoring up -d`
  Grafana http://<IP>:3000（默认 admin/admin，首次登录改密；或安全组不开 3000
  用 SSH 隧道访问：`ssh -L 3000:localhost:3000 <server>`）
- [ ] 数据备份：MySQL 数据卷定期快照/导出
  `docker compose ... exec mysql mysqldump -uroot -p<密码> drone_energy | gzip > backup-$(date +%F).sql.gz`
- [ ] HTTPS（正式对外演示前）：当前 HTTP 明文 + JWT 经查询参数走 WS，
  公网裸奔有被嗅探风险；低成本方案 Cloudflare 免费版代理 5173 端口

## 12. 故障排查速查

| 症状 | 定位 |
|---|---|
| `pull` 报 denied / not found | GHCR 未 login（第 5 节）或 CI 镜像还没推完（等 CI 绿） |
| deploy 健康检查失败 | Actions 日志自动附 backend 最近 30 行：常见为迁移失败（看 MySQL 是否 healthy、密码是否与 .env 一致） |
| 页面白屏/接口 502 | `docker compose ... logs --tail 50 frontend backend`；前端反代目标 backend:8000，backend 未起则 502 |
| 登录 500 | JWT_SECRET 含特殊 shell 字符未加引号（.env 值加双引号重试） |
| 实时曲线不动 | `docker compose ... logs -f fake-data`：模拟器在重连说明 backend 重启过，1 分钟内自愈 |
| `!override` 报语法错 | compose 版本 <2.24：`docker compose version` 确认，用 get.docker.com 重装 |
| 服务器改了 .env 不生效 | 环境变量进容器需重建：`docker compose ... up -d --force-recreate backend` |
