#!/usr/bin/env bash
# 一键发布 career-loop 到 GitHub：建仓 → 推送 → 开 Pages → 自检
#
# 用法（在能访问 github.com 的网络下）：
#   bash scripts/publish_github.sh
#
# 认证二选一（脚本自动检测，优先用 gh）：
#   A) 已装并登录 GitHub CLI：  gh auth login        → 脚本直接用 gh
#   B) 只有 PAT：               export GH_TOKEN=ghp_xxx（classic token 需 repo 权限）
#
# 本脚本不会把 token 写进任何文件、不会打印 token 内容。

set -euo pipefail

OWNER="jian935"
REPO="career-loop"
SLUG="${OWNER}/${REPO}"
BRANCH="main"
PAGES_PATH="/docs"

cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"

say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m  ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m  !\033[0m %s\n' "$*"; }
die()  { printf '\033[31m  ✗\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. 网络体检
say "0/6 网络体检（github.com 可达性）"
# 取 github.com 的 IP（Git Bash 没有 getent；nslookup 在中文 Windows 下输出乱码，
# 用 Python 解析最稳）
resolve_ip() {
  for py in python python3 py; do
    if command -v "$py" >/dev/null 2>&1; then
      "$py" -c "import socket,sys; sys.stdout.write(socket.gethostbyname('github.com'))" 2>/dev/null && return 0
    fi
  done
  nslookup github.com 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | tail -1
}
GH_IP="$(resolve_ip)"
if curl -sS -o /dev/null --max-time 15 https://github.com/ 2>/dev/null; then
  ok "github.com 可直接访问"
elif [ -n "$GH_IP" ] && curl -sS -o /dev/null --max-time 15 --resolve "github.com:443:${GH_IP}" https://github.com/ 2>/dev/null; then
  warn "github.com 直连失败，但用固定 IP ${GH_IP} 可通 —— 疑似 DNS 污染"
  warn "可临时加 hosts：echo '${GH_IP} github.com' >> /etc/hosts（Git Bash 需管理员）"
else
  die "连不上 github.com。请换一个能访问 GitHub 的网络（代理/VPN/手机热点）后重跑本脚本。"
fi

# ---------------------------------------------------------------- 1. 本地体检
say "1/6 本地体检"
[ -z "$(git status --porcelain)" ] || die "工作区有未提交改动，请先提交或 stash。"
ok "工作区干净（分支 $(git rev-parse --abbrev-ref HEAD)，$(git rev-list --count HEAD) 个提交）"

if git grep -qEI 'sk-[a-zA-Z0-9]{16,}|ghp_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{20,}' -- . 2>/dev/null; then
  die "已跟踪文件里疑似有密钥，终止推送。"
fi
ok "密钥扫描干净"

[ -f docs/index.html ] || die "缺 docs/index.html（Pages 站点根）"
ok "docs/ 站点根就绪"

# ---------------------------------------------------------------- 2. 认证
say "2/6 认证"
USE_GH=0
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  USE_GH=1
  ok "使用 GitHub CLI（gh auth status 通过）"
elif [ -n "${GH_TOKEN:-}" ]; then
  ok "使用环境变量 GH_TOKEN"
else
  die "没有可用凭证。二选一：
  A) 安装并登录 GitHub CLI：https://cli.github.com/  →  gh auth login
  B) 设置 PAT：export GH_TOKEN=ghp_xxx（classic token 勾选 repo 权限）"
fi

api() { # api <method> <path> [json-body]
  local method="$1" path="$2" body="${3:-}"
  if [ "$USE_GH" = "1" ]; then
    if [ -n "$body" ]; then
      gh api -X "$method" "$path" --input - <<<"$body"
    else
      gh api -X "$method" "$path"
    fi
  else
    if [ -n "$body" ]; then
      curl -sS -X "$method" "https://api.github.com${path}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        --data-binary "$body"
    else
      curl -sS -X "$method" "https://api.github.com${path}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28"
    fi
  fi
}

# ---------------------------------------------------------------- 3. 建仓
say "3/6 创建仓库 ${SLUG}（public）"
if api GET "/repos/${SLUG}" >/dev/null 2>&1; then
  ok "仓库已存在，跳过创建"
else
  if [ "$USE_GH" = "1" ]; then
    gh repo create "${SLUG}" --public --description "Job-fit scoring you can falsify: JD x experience -> score + gaps + counterfactual, then calibrate against real outcomes." >/dev/null
  else
    api POST "/user/repos" "{\"name\":\"${REPO}\",\"private\":false,\"description\":\"Job-fit scoring you can falsify.\"}" >/dev/null
  fi
  ok "已创建 public 仓库"
fi

# ---------------------------------------------------------------- 4. 推送
say "4/6 推送 ${BRANCH} 分支"
git remote set-url origin "https://github.com/${SLUG}.git"
if git push -u origin "${BRANCH}"; then
  ok "推送完成"
else
  die "推送失败。若提示认证错误，请先配好 gh auth 或 GH_TOKEN；若提示网络错误，确认当前网络能访问 github.com。"
fi

# ---------------------------------------------------------------- 5. 开 Pages
say "5/6 开启 GitHub Pages（来源：${BRANCH} / ${PAGES_PATH}）"
sleep 3
if api POST "/repos/${SLUG}/pages" \
   "{\"source\":{\"branch\":\"${BRANCH}\",\"path\":\"${PAGES_PATH}\"}}" >/dev/null 2>&1; then
  ok "Pages 已开启"
elif api PUT "/repos/${SLUG}/pages" \
   "{\"source\":{\"branch\":\"${BRANCH}\",\"path\":\"${PAGES_PATH}\"}}" >/dev/null 2>&1; then
  ok "Pages 配置已更新"
else
  warn "API 开 Pages 失败（可能已开启或权限不足）——手动设置："
  warn "  Settings → Pages → Source: Deploy from a branch → ${BRANCH} / ${PAGES_PATH}"
fi

# ---------------------------------------------------------------- 6. 自检
say "6/6 自检"
sleep 5
PAGE_URL="https://${OWNER}.github.io/${REPO}/"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "${PAGE_URL}" 2>/dev/null || echo 000)"
if [ "$CODE" = "200" ]; then
  ok "站点可访问：${PAGE_URL}"
else
  warn "站点暂未就绪（HTTP ${CODE}，Pages 首次构建通常需 1–2 分钟）——稍后访问：${PAGE_URL}"
fi

cat <<EOF

────────────────────────────────────────────
发布完成。核对清单：

  仓库      https://github.com/${SLUG}
  在线 Demo ${PAGE_URL}
  CI        https://github.com/${SLUG}/actions

投稿表单第 3 节要填的链接已就位：
  ${PAGE_URL}

下一步（活动相关）：
  1. 确认仓库 Description / Topics（话题标签以活动官方公布为准）
  2. 把 README 顶部截图（docs/demo.png）和演示视频（docs/career-loop-demo.mp4）确认能正常显示
  3. 按 docs/submission.md 抄填投稿表单
────────────────────────────────────────────
EOF
