#!/usr/bin/env bash
# Back up the parts of the deployment that cannot be rebuilt: the encrypted
# credential store, the employee access-code registry, usage records, the
# machine key file and the service configuration.
#
# Not included: uploaded images and results (they expire after three days and
# are far too large). Nothing is printed except paths, sizes and a digest.
#
# Usage: backup.sh [destination-directory]   (default /var/backups/hsd-agent)
set -euo pipefail

DESTINATION="${1:-/var/backups/hsd-agent}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${DESTINATION}/hsd-agent-${STAMP}.tar.gz"

mkdir -p "${DESTINATION}"
chmod 700 "${DESTINATION}"

# --warning=no-file-changed: the service may rewrite a manifest mid-copy; a
# consistent manifest is not needed to restore credentials, and the archive is
# verified below. Salted hashes and ciphertext are safe to store, plaintext is
# not: this file must still be treated as a secret.
tar -czf "${ARCHIVE}" --warning=no-file-changed \
  -C / etc/hsd-agent \
  -C /var/lib/hsd-agent settings 2>/dev/null || true

chmod 600 "${ARCHIVE}"
gzip -t "${ARCHIVE}"
sha256sum "${ARCHIVE}" > "${ARCHIVE}.sha256"
chmod 600 "${ARCHIVE}.sha256"

size=$(du -h "${ARCHIVE}" | cut -f1)
echo "備份完成：${ARCHIVE} (${size})"
echo "校验：$(cut -d' ' -f1 "${ARCHIVE}.sha256")"
echo "恢复：停止 hsd-agent.service，解包到 /，恢复文件权限后启动；详见 docs/运维与备份.md"
