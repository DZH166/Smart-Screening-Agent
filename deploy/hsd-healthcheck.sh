#!/usr/bin/env bash
# Read-only health probe for the HSD employee site.
#
# It never restarts anything: a failed check only records an alert in the
# journal (and marks this unit failed, so `systemctl --failed` shows it).
# Deliberately no unauthenticated detail: /healthz answers "ok" and nothing
# else, so this probe works without an employee access code.
set -uo pipefail

PUBLIC_HOST="${HSD_PUBLIC_HOST:-39.106.45.116:8443}"
LOOPBACK_URL="${HSD_LOOPBACK_URL:-https://127.0.0.1:8443}"
STORAGE="${HSD_STORAGE:-/var/lib/hsd-agent/storage}"
MIN_FREE_MB="${HSD_MIN_FREE_MB:-1024}"
failed=0

alert() { echo "ALERT $*"; failed=1; }

if ! systemctl is-active --quiet hsd-agent.service; then
  alert "hsd-agent.service 未运行"
fi

code=$(curl -sk -m 8 -o /dev/null -w '%{http_code}' -H "Host: ${PUBLIC_HOST}" "${LOOPBACK_URL}/healthz" || true)
case "${code}" in
  200) ;;
  *) alert "/healthz 返回 ${code:-无响应}" ;;
esac

if ! mountpoint -q "${STORAGE}"; then
  alert "数据卷未挂载：${STORAGE}"
else
  free_mb=$(df -Pm "${STORAGE}" | awk 'NR==2 {print $4}')
  if [ "${free_mb:-0}" -lt "${MIN_FREE_MB}" ]; then
    alert "数据卷剩余 ${free_mb}MB，低于 ${MIN_FREE_MB}MB"
  fi
fi

workers=$(pgrep -fc 'hsd_tool.cloud_server' || true)
if [ "${workers:-0}" -eq 0 ]; then
  alert "没有找到服务进程"
elif [ "${workers}" -gt 3 ]; then
  # One CloudWorker plus its arbiter is expected; more means a second copy.
  alert "发现 ${workers} 个服务进程，可能启动了第二个实例"
fi

if [ "${failed}" -eq 0 ]; then
  echo "ok host=${PUBLIC_HOST} free_mb=${free_mb:-unknown}"
fi
exit "${failed}"
