#!/bin/sh

# RAID 이동 하드디스크 건강상태 점검 스크립트 (12디스크)
# Red Hat OS 호환 | validator 스타일

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0
TOTAL=0

LOG_FILE="./raid_health_$(date +%Y%m%d_%H%M%S).log"

log() {
    echo "$1" | tee -a "$LOG_FILE"
}

# ──────────────────────────────────────────
# 헤더
# ──────────────────────────────────────────
log ""
log "========================================"
log "   RAID 이동 하드디스크 건강상태 점검"
log "   $(date '+%Y-%m-%d %H:%M:%S')"
log "========================================"
log ""

# root 권한 확인
if [ "$(id -u)" -ne 0 ]; then
    log "${YELLOW}[경고] root 권한 없음 - S.M.A.R.T. 일부 항목 제한될 수 있음${NC}"
    log "       sudo sh raid_disk_health.sh 로 실행 권장"
    log ""
fi

# ──────────────────────────────────────────
# RAID 상태 확인
# ──────────────────────────────────────────
log "${BLUE}[RAID 상태]${NC}"
log "----------------------------------------"

# mdadm RAID 확인
if command -v mdadm > /dev/null 2>&1; then
    RAID_DEVS=$(mdadm --detail --scan 2>/dev/null | awk '{print $2}')
    if [ -n "$RAID_DEVS" ]; then
        for RDEV in $RAID_DEVS; do
            log ">> $RDEV"
            mdadm --detail "$RDEV" 2>/dev/null | grep -E "State|Active|Failed|Spare|UUID" | while read line; do
                log "   $line"
            done
            log ""
        done
    else
        log "${YELLOW}mdadm RAID 장치 없음 또는 권한 부족${NC}"
    fi

    # /proc/mdstat 로 상태 요약
    if [ -f /proc/mdstat ]; then
        log "${CYAN}/proc/mdstat:${NC}"
        cat /proc/mdstat | tee -a "$LOG_FILE"
        log ""
    fi
else
    log "${YELLOW}mdadm 미설치 - 설치: sudo dnf install mdadm${NC}"
    if [ -f /proc/mdstat ]; then
        log "${CYAN}/proc/mdstat:${NC}"
        cat /proc/mdstat | tee -a "$LOG_FILE"
    fi
    log ""
fi

# ──────────────────────────────────────────
# 12개 디스크 자동 탐지
# ──────────────────────────────────────────
log "${BLUE}[디스크 탐지]${NC}"
log "----------------------------------------"

# 실제 연결된 디스크 목록 수집
DISKS=""
if command -v lsblk > /dev/null 2>&1; then
    DISKS=$(lsblk -d -o NAME,TYPE 2>/dev/null | awk '$2=="disk"{print "/dev/"$1}')
fi

DISK_COUNT=$(echo "$DISKS" | grep -c "/dev/" 2>/dev/null || echo 0)
log "탐지된 디스크: ${DISK_COUNT}개"

# 목표 12개와 비교
if [ "$DISK_COUNT" -lt 12 ]; then
    log "${YELLOW}[주의] 예상 12개 중 ${DISK_COUNT}개만 탐지됨${NC}"
elif [ "$DISK_COUNT" -ge 12 ]; then
    log "${GREEN}[정상] 12개 이상 디스크 탐지됨${NC}"
fi
log ""

# ──────────────────────────────────────────
# 각 디스크 S.M.A.R.T. 점검
# ──────────────────────────────────────────
log "${BLUE}[S.M.A.R.T. 개별 점검]${NC}"
log "========================================"

if ! command -v smartctl > /dev/null 2>&1; then
    log "${YELLOW}smartctl 미설치 - 설치: sudo dnf install smartmontools${NC}"
    log "S.M.A.R.T. 점검을 건너뜁니다."
else
    DISK_NUM=1
    for DISK in $DISKS; do
        if [ -b "$DISK" ]; then
            TOTAL=$((TOTAL + 1))
            log ""
            log "${CYAN}[디스크 ${DISK_NUM}/12] $DISK${NC}"
            log "----------------------------------------"

            # 디스크 기본 정보
            MODEL=$(smartctl -i "$DISK" 2>/dev/null | grep -E "Device Model|Product" | awk -F: '{print $2}' | xargs)
            SERIAL=$(smartctl -i "$DISK" 2>/dev/null | grep "Serial" | awk -F: '{print $2}' | xargs)
            SIZE=$(lsblk -d -o NAME,SIZE "$DISK" 2>/dev/null | awk 'NR==2{print $2}')
            ROTATION=$(lsblk -d -o NAME,ROTA "$DISK" 2>/dev/null | awk 'NR==2{print $2}')

            if [ "$ROTATION" = "0" ]; then
                DTYPE="SSD"
            else
                DTYPE="HDD"
            fi

            log "   모델   : ${MODEL:-알 수 없음}"
            log "   시리얼 : ${SERIAL:-알 수 없음}"
            log "   용량   : ${SIZE:-알 수 없음} ($DTYPE)"

            # S.M.A.R.T. 전반 상태
            SMART_RESULT=$(smartctl -H "$DISK" 2>/dev/null)
            if echo "$SMART_RESULT" | grep -q "PASSED"; then
                log "   건강상태: ${GREEN}[PASS] 정상${NC}"
                PASS=$((PASS + 1))
            elif echo "$SMART_RESULT" | grep -q "FAILED"; then
                log "   건강상태: ${RED}[FAIL] 불량 - 즉시 데이터 백업 필요!${NC}"
                FAIL=$((FAIL + 1))
            else
                log "   건강상태: ${YELLOW}[WARN] 확인 불가${NC}"
                WARN=$((WARN + 1))
            fi

            # 온도
            TEMP=$(smartctl -A "$DISK" 2>/dev/null | grep -i "temperature" | awk '{print $10}' | head -1)
            if [ -n "$TEMP" ]; then
                if [ "$TEMP" -ge 55 ] 2>/dev/null; then
                    log "   온도     : ${RED}${TEMP}°C (과열 주의!)${NC}"
                elif [ "$TEMP" -ge 45 ] 2>/dev/null; then
                    log "   온도     : ${YELLOW}${TEMP}°C (주의)${NC}"
                else
                    log "   온도     : ${GREEN}${TEMP}°C (정상)${NC}"
                fi
            fi

            # 불량 섹터 (Reallocated)
            REALLOCATED=$(smartctl -A "$DISK" 2>/dev/null | grep "Reallocated_Sector" | awk '{print $10}')
            if [ -n "$REALLOCATED" ]; then
                if [ "$REALLOCATED" -gt 0 ] 2>/dev/null; then
                    log "   불량섹터 : ${RED}${REALLOCATED}개 (교체 검토)${NC}"
                else
                    log "   불량섹터 : ${GREEN}없음${NC}"
                fi
            fi

            # 보류 섹터 (Pending)
            PENDING=$(smartctl -A "$DISK" 2>/dev/null | grep "Current_Pending_Sector" | awk '{print $10}')
            if [ -n "$PENDING" ] && [ "$PENDING" -gt 0 ] 2>/dev/null; then
                log "   보류섹터 : ${YELLOW}${PENDING}개 (주의)${NC}"
            fi

            # 전원 켠 시간 (수명)
            HOURS=$(smartctl -A "$DISK" 2>/dev/null | grep "Power_On_Hours" | awk '{print $10}')
            if [ -n "$HOURS" ]; then
                DAYS=$((HOURS / 24))
                log "   사용시간 : ${HOURS}시간 (약 ${DAYS}일)"
            fi

            DISK_NUM=$((DISK_NUM + 1))
        fi
    done
fi

# ──────────────────────────────────────────
# 디스크 사용량
# ──────────────────────────────────────────
log ""
log "${BLUE}[디스크 사용량]${NC}"
log "========================================"
df -h 2>/dev/null | grep -v tmpfs | grep -v devtmpfs | tee -a "$LOG_FILE"

# ──────────────────────────────────────────
# 최종 요약
# ──────────────────────────────────────────
log ""
log "========================================"
log "             점검 결과 요약"
log "========================================"
log "  총 점검 디스크 : ${TOTAL}개 (목표: 12개)"
log "  ${GREEN}정상 (PASS)   : ${PASS}개${NC}"
log "  ${YELLOW}주의 (WARN)   : ${WARN}개${NC}"
log "  ${RED}불량 (FAIL)   : ${FAIL}개${NC}"
log ""

if [ "$FAIL" -gt 0 ]; then
    log "${RED}[긴급] 불량 디스크 ${FAIL}개 발견! 즉시 데이터 백업 후 교체하세요.${NC}"
elif [ "$WARN" -gt 0 ]; then
    log "${YELLOW}[주의] 확인이 필요한 디스크가 있습니다.${NC}"
else
    log "${GREEN}[정상] 모든 디스크가 양호한 상태입니다.${NC}"
fi

log ""
log "로그 저장: $LOG_FILE"
log "========================================"
