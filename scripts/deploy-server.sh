#!/usr/bin/env bash
# ==============================================================================
# DroneEnergy-OS 测试环境一键部署脚本（在 Linux 服务器上运行）
#
# 自动化 docs/deploy-checklist.md 的服务器侧章节：
#   2 基础环境（Docker/Compose/git/curl）
#   3 仓库获取（clone 或 git pull，幂等）
#   4 .env 生成（随机强密码，已存在则保留）
#   5 GHCR 镜像访问（token 参数或失败时交互补登录）
#   8 首次部署（pull + up --no-build）
#   9 功能冒烟（健康检查/登录/设备/历史/落库流水）
#
# 用法（两种姿势等价）：
#   # 姿势一：直接在服务器上跑（自动 clone 到 /opt/droneenergy-os）
#   curl -fsSL -o deploy.sh \
#     https://raw.githubusercontent.com/mutongsun/DroneEnergy-OS/main/scripts/deploy-server.sh
#   bash deploy.sh
#
#   # 姿势二：先 clone 仓库再运行（部署目录 = 仓库目录）
#   git clone https://github.com/mutongsun/DroneEnergy-OS.git /opt/droneenergy-os
#   bash /opt/droneenergy-os/scripts/deploy-server.sh
#
# 可选参数：
#   --deepseek-key KEY    AI 诊断密钥（不给则交互式询问，可留空走 fallback）
#   --ghcr-token TOKEN    GHCR PAT（read:packages；不给则 pull 失败时询问）
#   --with-monitoring     附加启动 Prometheus + Grafana
#   --dir PATH            部署目录（默认：脚本所在仓库，或 /opt/droneenergy-os）
#   -h | --help           帮助
#
# 设计约束：
# - 幂等：重复执行安全（已装跳过、.env 不覆盖、仓库走 pull）
# - 脚本无法代劳的事项在结束时统一提示（安全组 / GitHub Secrets / 浏览器验证）
# ==============================================================================
set -euo pipefail

DEEPSEEK_KEY=""
GHCR_TOKEN=""
WITH_MONITORING=0
DEPLOY_DIR_ARG=""
GHCR_USER="mutongsun"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

usage() { sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }
while [ $# -gt 0 ]; do
  case "$1" in
    --deepseek-key)  DEEPSEEK_KEY="${2:?缺少参数值}"; shift 2 ;;
    --ghcr-token)    GHCR_TOKEN="${2:?缺少参数值}"; shift 2 ;;
    --with-monitoring) WITH_MONITORING=1; shift ;;
    --dir)           DEPLOY_DIR_ARG="${2:?缺少参数值}"; shift 2 ;;
    -h|--help)       usage ;;
    *) echo "未知参数: $1（--help 查看用法）" >&2; exit 1 ;;
  esac
done

log()  { printf '\033[32m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[33m[警告]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- 0. 环境预检 ----------
[ "$(uname -s)" = "Linux" ] || die "本脚本仅支持 Linux 服务器（当前: $(uname -s)）"
[ "$(uname -m)" = "x86_64" ] || die "当前架构 $(uname -m) 不支持：CI 镜像为 linux/amd64，需先给 CI 增加 arm64 构建"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "非 root 且无 sudo，无法安装依赖"
  SUDO="sudo"
fi

if [ ! -f /etc/debian_version ]; then
  warn "非 Debian/Ubuntu 系统（$(uname -r)），apt 安装步骤可能失败，可自行装好 docker/git 后重跑"
fi

# ---------- 1. 基础环境安装（幂等）----------
if ! command -v docker >/dev/null 2>&1; then
  log "安装 Docker（get.docker.com 官方脚本）..."
  curl -fsSL https://get.docker.com | $SUDO sh
else
  log "Docker 已安装: $(docker --version | cut -d, -f1)"
fi

# compose 版本 >= 2.24（prod 配置的 !override 标签依赖）
compose_ver=$(docker compose version --short 2>/dev/null | sed 's/^v//' || echo "0")
compose_major=$(echo "$compose_ver" | cut -d. -f1); compose_major=${compose_major:-0}
compose_minor=$(echo "$compose_ver" | cut -d. -f2); compose_minor=${compose_minor:-0}
if [ "${compose_major:-0}" -lt 2 ] || { [ "${compose_major:-0}" -eq 2 ] && [ "${compose_minor:-0}" -lt 24 ]; }; then
  die "docker compose v${compose_ver} 过旧（!override 需 v2.24+），请重装: curl -fsSL https://get.docker.com | sh"
fi
log "docker compose v${compose_ver} 满足要求（>= 2.24）"

for bin in git curl openssl; do
  command -v "$bin" >/dev/null 2>&1 || { log "安装 $bin..."; $SUDO apt-get update -qq && $SUDO apt-get install -y -qq "$bin"; }
done

# docker 组权限：非 root 且当前会话无权限时，usermod 后经 sg 重入本脚本
if ! docker ps >/dev/null 2>&1; then
  [ "${_DEPLOY_REENTERED:-}" = "1" ] && die "docker 组已加入但当前会话未生效，请退出 SSH 重新登录后再跑一次"
  log "当前用户无 docker 权限，加入 docker 组..."
  $SUDO usermod -aG docker "$USER"
  log "通过 sg 以新组身份重新进入脚本（无需重新登录）..."
  _DEPLOY_REENTERED=1 exec sg docker -c "$(printf '%q ' "$0" "$@")"
fi

# ---------- 2. 部署目录与仓库 ----------
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)
DEPLOY_DIR="${DEPLOY_DIR_ARG:-${REPO_ROOT:-/opt/droneenergy-os}}"

if [ -d "$DEPLOY_DIR/.git" ]; then
  log "仓库已存在: $DEPLOY_DIR（git pull 更新）"
  git -C "$DEPLOY_DIR" pull --ff-only origin main
else
  log "克隆仓库到 $DEPLOY_DIR ..."
  git clone https://github.com/mutongsun/DroneEnergy-OS.git "$DEPLOY_DIR"
fi
cd "$DEPLOY_DIR"
[ -f docker-compose.yml ] && [ -f docker-compose.prod.yml ] \
  || die "$DEPLOY_DIR 下缺少 compose 文件，请确认目录正确"

# CD（deploy.yml）约定路径为 /opt/droneenergy-os；用别的目录时提醒
if [ "$DEPLOY_DIR" != "/opt/droneenergy-os" ]; then
  warn "部署目录 $DEPLOY_DIR 与 deploy.yml 约定的 /opt/droneenergy-os 不一致：GitHub Actions 自动部署将不作用于本目录"
fi

PROFILE_ARGS=""
[ "$WITH_MONITORING" = "1" ] && PROFILE_ARGS="--profile monitoring"

# ---------- 3. .env 生成（已存在则保留，绝不覆盖）----------
if [ ! -f .env ]; then
  gen_hex() { openssl rand -hex "$1" 2>/dev/null || head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
  if [ -z "$DEEPSEEK_KEY" ] && [ -t 0 ]; then
    read -rsp "DeepSeek API Key（直接回车跳过，AI 诊断走 fallback）: " DEEPSEEK_KEY; echo
  fi
  cat > .env <<EOF
# 由 deploy-server.sh 生成于 $(date '+%F %T')；重新生成需先删除本文件
MYSQL_ROOT_PASSWORD=$(gen_hex 16)
DEEPSEEK_API_KEY=${DEEPSEEK_KEY}
JWT_SECRET=$(gen_hex 32)
API_USER=operator
API_PASSWORD=operator123
EOF
  chmod 600 .env
  log ".env 已生成（随机强密码/密钥，权限 600）——口令查看: grep MYSQL .env"
else
  log ".env 已存在，保留现有配置"
fi
set -a; . ./.env; set +a   # 后续冒烟测试要用 MYSQL_ROOT_PASSWORD

# ---------- 4. GHCR 镜像拉取（失败时交互补登录，重试一次）----------
ghcr_login() {
  local token="$1"
  echo "$token" | docker login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null 2>&1
}

pull_images() {
  log "拉取 GHCR 镜像..."
  $COMPOSE $PROFILE_ARGS pull
}

[ -n "$GHCR_TOKEN" ] && { ghcr_login "$GHCR_TOKEN" || die "GHCR 登录失败（检查 PAT 是否勾选 read:packages）"; log "GHCR 登录成功"; }

if ! pull_images; then
  warn "镜像拉取失败——常见原因：GHCR 包为私有且本机未登录"
  if [ -t 0 ]; then
    read -rsp "请输入 GitHub PAT（classic，勾选 read:packages；或把包设为 public 后直接回车重试）: " pat; echo
    if [ -n "$pat" ]; then ghcr_login "$pat" || die "登录仍失败"; fi
    pull_images || die "镜像拉取再次失败，请人工排查网络/PAT 权限"
  else
    die "非交互环境无法补登录：用 --ghcr-token 传入 PAT，或将 GHCR 包设为 public"
  fi
fi

# ---------- 5. 启动容器 ----------
log "启动容器（首次启动含 MySQL 初始化 + 迁移 + 种子，约 30~60s）..."
$COMPOSE $PROFILE_ARGS up -d --no-build

# ---------- 6. 健康检查（150s 预算）----------
log "健康检查（backend 宿主机 127.0.0.1:8001）..."
healthy=0
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8001/api/v1/health >/dev/null 2>&1; then healthy=1; break; fi
  sleep 5
done
if [ "$healthy" != "1" ]; then
  warn "健康检查失败，backend 最近 30 行日志："
  $COMPOSE logs --tail 30 backend || true
  die "排查后重跑本脚本即可（幂等）"
fi
log "健康检查通过（第 $((i*5))s）"

# ---------- 7. API 冒烟测试（失败仅告警，不中断）----------
PASS=0; FAIL=0
check() {  # check <名称> <命令...>（命令输出 HTTP 码）
  local name="$1"; shift
  if "$@"; then log "  ✓ $name"; PASS=$((PASS+1)); else warn "  ✗ $name（详见「故障排查速查表」）"; FAIL=$((FAIL+1)); fi
}
http_ok() {  # http_ok <预期码> <url> [curl参数...]
  local expect="$1" url="$2"; shift 2
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$@" "$url")" = "$expect" ]
}

BASE="http://127.0.0.1:8001/api/v1"
log "API 冒烟测试："

# 登录换 token（后续接口鉴权用）
TOKEN=$(curl -sf -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"viewer","password":"viewer123"}' \
  | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' || true)
if [ -n "$TOKEN" ]; then log "  ✓ 登录（viewer）签发 JWT"; PASS=$((PASS+1)); else warn "  ✗ 登录失败"; FAIL=$((FAIL+1)); fi

if [ -n "$TOKEN" ]; then
  check "设备列表 GET /drones"        http_ok 200 "$BASE/drones?page=1&page_size=5" -H "Authorization: Bearer $TOKEN"
  check "历史曲线 GET /sensor/history" http_ok 200 "$BASE/sensor/history/1?minutes=10&limit=5" -H "Authorization: Bearer $TOKEN"
  check "RBAC 越权拒绝（viewer 写设备应 403）" \
    http_ok 403 "$BASE/drones" -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name":"x","model":"y"}'
fi

# 落库流水：fake-data 推流 → sensor_snapshots 行数应增长（新库从 0 开始，最多等 2 分钟）
log "数据入库流水（等待模拟器首批数据，最长 120s）..."
rows0=$($COMPOSE exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N \
  -e "SELECT COUNT(*) FROM drone_energy.sensor_snapshots" 2>/dev/null || echo -1)
ingested=0
for i in $(seq 1 12); do
  sleep 10
  rows1=$($COMPOSE exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N \
    -e "SELECT COUNT(*) FROM drone_energy.sensor_snapshots" 2>/dev/null || echo -1)
  if [ "$rows1" != "-1" ] && [ "$rows1" -gt "${rows0:-0}" ]; then ingested=1; break; fi
done
if [ "$ingested" = "1" ]; then log "  ✓ 落库流水正常（$rows0 → $rows1 行）"; PASS=$((PASS+1))
else warn "  ✗ 未见数据增长（当前 ${rows1:-?} 行）：docker compose logs --tail 20 fake-data 查看"; FAIL=$((FAIL+1)); fi

# ---------- 8. 汇总 ----------
echo
log "容器状态："
$COMPOSE $PROFILE_ARGS ps
PUBLIC_IP=$(curl -sf --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')
PUBLIC_IP="${PUBLIC_IP:-<服务器IP>}"
echo
echo "====================================== 部署结果 ======================================"
echo " 冒烟测试：$PASS 通过 / $FAIL 失败"
echo " 访问入口：http://${PUBLIC_IP}:5173   账号 viewer/viewer123（admin/admin123 拥有全部权限）"
echo " 数据库口令：grep MYSQL_ROOT_PASSWORD .env    （JWT 密钥: grep JWT_SECRET .env）"
echo "======================================================================================"
echo " 剩余手动步骤（脚本无法代劳，对应检查清单章节）："
echo "  1. [清单§7] 云安全组只放行 22 + 5173（mysql/redis/backend 已由 prod 配置收敛，双保险）"
echo "  2. [清单§6] 配置 GitHub Secrets（TEST_SSH_HOST/USER/KEY）打通 Actions 手动部署"
echo "  3. [清单§9] 浏览器验证实时曲线 / 3D 姿态 / AI 诊断面板"
echo " 日常更新：git push -> CI 全绿 -> Actions 页面点 Deploy (test)"
echo "======================================================================================"
[ "$FAIL" = "0" ] || exit 1
