#!/bin/sh

# 하드디스크 건강상태 점검 스크립트
# Red Hat OS 호환

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================"
echo "      하드디스크 건강상태 점검"
echo "========================================"
echo ""

# root 권한 확인
if [ "$(id -u)" -ne 0 ]; then
    echo "${YELLOW}[경고] 일부 항목은 root 권한이 필요합니다.${NC}"
    echo "       sudo sh disk_health.sh 으로 실행하면 더 많은 정보를 확인할 수 있습니다."
    echo ""
fi

# ──────────────────────────────────────────
# 1. 디스크 목록
# ──────────────────────────────────────────
echo "${BLUE}[1] 디스크 목록${NC}"
echo "----------------------------------------"
lsblk -d -o NAME,SIZE,ROTA,TYPE,MOUNTPOINT 2>/dev/null || fdisk -l 2>/dev/null | grep "^Disk /dev"
echo ""

# ──────────────────────────────────────────
# 2. 디스크 사용량
# ──────────────────────────────────────────
echo "${BLUE}[2] 디스크 사용량${NC}"
echo "----------------------------------------"
df -h | grep -v tmpfs | grep -v devtmpfs
echo ""

# ──────────────────────────────────────────
# 3. S.M.A.R.T. 상태 (smartctl 필요)
# ──────────────────────────────────────────
echo "${BLUE}[3] S.M.A.R.T. 건강 상태${NC}"
echo "----------------------------------------"

if command -v smartctl > /dev/null 2>&1; then
    # 디스크 목록 자동 탐지
    DISKS=$(lsblk -d -o NAME,TYPE | awk '$2=="disk"{print "/dev/"$1}')

    if [ -z "$DISKS" ]; then
        DISKS="/dev/sda /dev/sdb /dev/nvme0n1"
    fi

    for DISK in $DISKS; do
        if [ -b "$DISK" ]; then
            echo ">> $DISK"
            RESULT=$(smartctl -H "$DISK" 2>/dev/null)
            if echo "$RESULT" | grep -q "PASSED"; then
                echo "   상태: ${GREEN}정상 (PASSED)${NC}"
            elif echo "$RESULT" | grep -q "FAILED"; then
                echo "   상태: ${RED}불량 (FAILED) - 즉시 백업 권장!${NC}"
            else
                echo "   상태: ${YELLOW}확인 불가 (권한 또는 미지원)${NC}"
            fi

            # 온도 출력
            TEMP=$(smartctl -A "$DISK" 2>/dev/null | grep -i "temperature" | awk '{print $10}' | head -1)
            if [ -n "$TEMP" ]; then
                echo "   온도: ${TEMP}°C"
            fi

            # 재할당 섹터 (불량 섹터)
            REALLOCATED=$(smartctl -A "$DISK" 2>/dev/null | grep "Reallocated_Sector" | awk '{print $10}')
            if [ -n "$REALLOCATED" ]; then
                if [ "$REALLOCATED" -gt 0 ] 2>/dev/null; then
                    echo "   불량 섹터: ${RED}${REALLOCATED}개 (주의!)${NC}"
                else
                    echo "   불량 섹터: ${GREEN}없음${NC}"
                fi
            fi

            echo ""
        fi
    done
else
    echo "${YELLOW}smartctl 이 설치되어 있지 않습니다.${NC}"
    echo "설치하려면: sudo dnf install smartmontools"
    echo ""
fi

# ──────────────────────────────────────────
# 4. 디스크 I/O 통계
# ──────────────────────────────────────────
echo "${BLUE}[4] 디스크 I/O 통계${NC}"
echo "----------------------------------------"
if command -v iostat > /dev/null 2>&1; then
    iostat -d -h 1 1 2>/dev/null | grep -v "^$" | grep -v "Linux"
else
    echo "${YELLOW}iostat 이 없습니다. 설치: sudo dnf install sysstat${NC}"
    cat /proc/diskstats 2>/dev/null | awk '{print $3, "읽기:", $6, "쓰기:", $10}' | grep -v "^loop" | grep -v "^ram"
fi
echo ""

# ──────────────────────────────────────────
# 5. 마운트 상태
# ──────────────────────────────────────────
echo "${BLUE}[5] 마운트 상태${NC}"
echo "----------------------------------------"
mount | grep "^/dev" | awk '{print $1, "→", $3, "("$5")"}'
echo ""

# ──────────────────────────────────────────
# 6. 최근 디스크 오류 로그
# ──────────────────────────────────────────
echo "${BLUE}[6] 최근 디스크 오류 로그 (dmesg)${NC}"
echo "----------------------------------------"
dmesg 2>/dev/null | grep -iE "error|fail|bad sector|i/o error|ata.*error" | tail -10
if [ $? -ne 0 ] || [ -z "$(dmesg 2>/dev/null | grep -iE 'error|fail|bad sector')" ]; then
    echo "${GREEN}최근 디스크 오류 없음${NC}"
fi
echo ""

echo "========================================"
echo "           점검 완료"
echo "========================================"
