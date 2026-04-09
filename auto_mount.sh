#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# auto_mount.sh  —  CRU 외장 하드 자동 마운트 스크립트
# udev 규칙에서 호출됨 (root로 실행)
# 사용법: /usr/local/bin/auto_mount.sh <device_name>  예) sdb
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

DEVICE="${1:-}"
MOUNT_BASE="/media/cru"
LOG="/var/log/cru_automount.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

# ── 인자 검증
if [ -z "$DEVICE" ]; then
    log "오류: 장치명 인자가 없습니다."
    exit 1
fi

DEV_PATH="/dev/${DEVICE}"

if [ ! -b "$DEV_PATH" ]; then
    log "오류: 블록 장치가 아닙니다: $DEV_PATH"
    exit 1
fi

log "CRU 드라이브 감지: $DEV_PATH"

# ── 안정화 대기 (파티션 테이블 읽기 완료 대기)
sleep 2

# ── 마운트 기본 경로 생성
mkdir -p "$MOUNT_BASE"

# ── 파티션 목록 탐색 및 마운트
MOUNTED=0
PARTITIONS=$(lsblk -ln -o NAME,TYPE "$DEV_PATH" 2>/dev/null | awk '$2=="part"{print $1}')

if [ -z "$PARTITIONS" ]; then
    # 파티션 없이 전체 디스크에 파일시스템이 있는 경우
    PARTITIONS="$DEVICE"
fi

for PART in $PARTITIONS; do
    PART_DEV="/dev/${PART}"
    [ -b "$PART_DEV" ] || continue

    # 이미 마운트 되어있는지 확인
    if grep -q "^${PART_DEV} " /proc/mounts 2>/dev/null; then
        log "$PART_DEV 이미 마운트 됨 - 건너뜀"
        continue
    fi

    # 파일시스템 타입 감지
    FSTYPE=$(blkid -o value -s TYPE "$PART_DEV" 2>/dev/null || true)
    if [ -z "$FSTYPE" ]; then
        log "$PART_DEV 파일시스템 감지 실패 - 건너뜀"
        continue
    fi

    # 레이블 가져오기 (마운트 경로명으로 사용)
    LABEL=$(blkid -o value -s LABEL "$PART_DEV" 2>/dev/null || true)
    UUID=$(blkid -o value -s UUID "$PART_DEV" 2>/dev/null | tr -d '-' | cut -c1-8 || true)
    DIR_NAME="${LABEL:-${PART}_${UUID:-$(date +%s)}}"
    MOUNT_POINT="${MOUNT_BASE}/${DIR_NAME}"

    mkdir -p "$MOUNT_POINT"

    # 파일시스템별 마운트 옵션
    case "$FSTYPE" in
        ntfs|ntfs-3g)
            MOUNT_OPTS="rw,uid=1000,gid=1000,umask=022"
            ;;
        vfat|fat32|exfat)
            MOUNT_OPTS="rw,uid=1000,gid=1000,umask=022"
            ;;
        ext4|ext3|ext2|xfs|btrfs)
            MOUNT_OPTS="rw"
            ;;
        *)
            MOUNT_OPTS="rw"
            ;;
    esac

    if mount -t "$FSTYPE" -o "$MOUNT_OPTS" "$PART_DEV" "$MOUNT_POINT" 2>>"$LOG"; then
        log "마운트 성공: $PART_DEV  →  $MOUNT_POINT  ($FSTYPE)"
        MOUNTED=$((MOUNTED + 1))

        # 데스크탑 알림 (로그인된 사용자에게)
        LOGIN_USER=$(who | awk 'NR==1{print $1}' 2>/dev/null || true)
        if [ -n "$LOGIN_USER" ]; then
            DISPLAY_ENV=$(grep -z "DISPLAY" /proc/$(pgrep -u "$LOGIN_USER" -n)/environ 2>/dev/null \
                          | tr '\0' '\n' | grep DISPLAY | head -1 || true)
            DBUS_ENV=$(grep -z "DBUS_SESSION_BUS_ADDRESS" \
                       /proc/$(pgrep -u "$LOGIN_USER" -n)/environ 2>/dev/null \
                       | tr '\0' '\n' | grep DBUS | head -1 || true)
            if [ -n "$DISPLAY_ENV" ] && [ -n "$DBUS_ENV" ]; then
                su - "$LOGIN_USER" -c "export $DISPLAY_ENV; export $DBUS_ENV; \
                    notify-send '💾 CRU 드라이브 마운트' \
                    '${PART_DEV}  →  ${MOUNT_POINT}' \
                    --icon=drive-harddisk 2>/dev/null" || true
            fi
        fi
    else
        log "마운트 실패: $PART_DEV ($FSTYPE)"
        rmdir "$MOUNT_POINT" 2>/dev/null || true
    fi
done

log "처리 완료: $DEV_PATH  (마운트: ${MOUNTED}개)"
exit 0
