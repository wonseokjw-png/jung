#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  setup_usb.sh  —  검수 PC USB 부팅 환경 일괄 설치 스크립트
#  Ubuntu Live / Persistent USB 에서 실행
#  실행 방법:  sudo bash setup_usb.sh
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# ── 색상
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ── root 확인
[ "$(id -u)" -eq 0 ] || fail "root 권한으로 실행하세요: sudo bash setup_usb.sh"

echo ""
echo -e "${BOLD}══════════════════════════════════════════${NC}"
echo -e "${BOLD}   검수 PC 환경 설치 스크립트             ${NC}"
echo -e "${BOLD}   Ubuntu USB 부팅 디스크 전용            ${NC}"
echo -e "${BOLD}══════════════════════════════════════════${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/inspection"
DESKTOP_DIR="/etc/skel/Desktop"   # 신규 사용자 데스크탑 (라이브 세션용)

# 로그인된 일반 사용자 감지
LOGIN_USER="${SUDO_USER:-$(who | awk 'NR==1{print $1}')}"
USER_DESKTOP=""
if [ -n "$LOGIN_USER" ]; then
    USER_HOME=$(eval echo "~$LOGIN_USER")
    USER_DESKTOP="${USER_HOME}/Desktop"
fi

# ───────────────────────────────────────
# 1. 패키지 설치
# ───────────────────────────────────────
info "필요 패키지 설치 중..."
apt-get update -qq

PKGS=(
    python3
    python3-tk
    smartmontools        # smartctl
    udisks2              # udisksctl
    util-linux           # lsblk, blkid
    ntfs-3g              # NTFS 마운트
    exfatprogs           # exFAT 마운트
    udev
    libnotify-bin        # notify-send
    policykit-1          # pkexec
)

for pkg in "${PKGS[@]}"; do
    if dpkg -l "$pkg" &>/dev/null 2>&1; then
        ok "$pkg 이미 설치됨"
    else
        info "$pkg 설치 중..."
        apt-get install -y -qq "$pkg" && ok "$pkg 설치 완료" || warn "$pkg 설치 실패 (계속)"
    fi
done

# ───────────────────────────────────────
# 2. 프로그램 파일 설치
# ───────────────────────────────────────
info "프로그램 파일 복사 중..."
mkdir -p "$INSTALL_DIR"

for f in disk_health_gui.py hash_checker_gui.py; do
    if [ -f "${SCRIPT_DIR}/${f}" ]; then
        cp "${SCRIPT_DIR}/${f}" "${INSTALL_DIR}/${f}"
        chmod 755 "${INSTALL_DIR}/${f}"
        ok "$f → $INSTALL_DIR"
    else
        warn "$f 파일을 찾을 수 없습니다: ${SCRIPT_DIR}/${f}"
    fi
done

# ───────────────────────────────────────
# 3. 자동 마운트 스크립트 설치
# ───────────────────────────────────────
info "자동 마운트 스크립트 설치 중..."
if [ -f "${SCRIPT_DIR}/auto_mount.sh" ]; then
    cp "${SCRIPT_DIR}/auto_mount.sh" /usr/local/bin/auto_mount.sh
    chmod 755 /usr/local/bin/auto_mount.sh
    ok "auto_mount.sh → /usr/local/bin/"
else
    warn "auto_mount.sh 파일이 없습니다."
fi

# ───────────────────────────────────────
# 4. udev 규칙 설치
# ───────────────────────────────────────
info "udev 규칙 설치 중..."
UDEV_RULES_SRC="${SCRIPT_DIR}/udev_rules/99-cru-automount.rules"
if [ -f "$UDEV_RULES_SRC" ]; then
    cp "$UDEV_RULES_SRC" /etc/udev/rules.d/99-cru-automount.rules
    chmod 644 /etc/udev/rules.d/99-cru-automount.rules
    udevadm control --reload-rules
    udevadm trigger
    ok "udev 규칙 설치 및 적용 완료"
else
    warn "udev 규칙 파일이 없습니다: $UDEV_RULES_SRC"
fi

# ───────────────────────────────────────
# 5. 마운트 기본 경로 생성
# ───────────────────────────────────────
info "CRU 마운트 경로 생성..."
mkdir -p /media/cru
chmod 777 /media/cru
ok "/media/cru 생성 완료"

# ───────────────────────────────────────
# 6. 데스크탑 바로가기 설치
# ───────────────────────────────────────
install_desktop_shortcut() {
    local target_dir="$1"
    mkdir -p "$target_dir"

    # 디스크 건강 검사기
    cat > "${target_dir}/디스크건강검사.desktop" << 'DESK_EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=디스크 건강 검사기
Name[ko]=디스크 건강 검사기
Comment=CRU 외장 하드 S.M.A.R.T 건강 상태 검사
Exec=bash -c "pkexec env DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY python3 /opt/inspection/disk_health_gui.py"
Icon=drive-harddisk
Terminal=false
Categories=System;Utility;
StartupNotify=true
DESK_EOF

    # 해시 검증기
    cat > "${target_dir}/해시검증기.desktop" << 'DESK_EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=해시 검증기
Name[ko]=해시 검증기
Comment=복사된 디스크/파일 무결성 해시 검증
Exec=python3 /opt/inspection/hash_checker_gui.py
Icon=document-properties
Terminal=false
Categories=System;Utility;
StartupNotify=true
DESK_EOF

    chmod +x "${target_dir}/디스크건강검사.desktop"
    chmod +x "${target_dir}/해시검증기.desktop"
}

info "데스크탑 바로가기 설치 중..."

# 로그인된 사용자 데스크탑
if [ -n "$USER_DESKTOP" ]; then
    install_desktop_shortcut "$USER_DESKTOP"
    [ -n "$LOGIN_USER" ] && chown -R "${LOGIN_USER}:${LOGIN_USER}" "$USER_DESKTOP" || true
    ok "바로가기 설치: $USER_DESKTOP"
fi

# /etc/skel (새 사용자용 기본)
install_desktop_shortcut "$DESKTOP_DIR"
ok "바로가기 설치: $DESKTOP_DIR"

# ───────────────────────────────────────
# 7. polkit 규칙 (smartctl 비밀번호 없이 실행)
# ───────────────────────────────────────
info "polkit 규칙 설정 중 (smartctl 권한)..."
POLKIT_DIR="/etc/polkit-1/rules.d"
mkdir -p "$POLKIT_DIR"
cat > "${POLKIT_DIR}/50-inspection-smart.rules" << 'POLKIT_EOF'
/* 검수 PC: 디스크 건강 검사 도구에 smartctl 권한 허용 */
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.policykit.exec" &&
        subject.isInGroup("sudo")) {
        return polkit.Result.YES;
    }
});
POLKIT_EOF
ok "polkit 규칙 설정 완료"

# ───────────────────────────────────────
# 8. sudoers 설정 (smartctl 패스워드 없이)
# ───────────────────────────────────────
info "sudoers 설정 중..."
SUDOERS_FILE="/etc/sudoers.d/inspection"
cat > "$SUDOERS_FILE" << 'SUDOERS_EOF'
# 검수 PC: 디스크 검사 도구 권한
%sudo ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
%sudo ALL=(ALL) NOPASSWD: /bin/umount
%sudo ALL=(ALL) NOPASSWD: /usr/bin/udisksctl
%sudo ALL=(ALL) NOPASSWD: /sbin/blkid
%sudo ALL=(ALL) NOPASSWD: /usr/local/bin/auto_mount.sh
SUDOERS_EOF
chmod 440 "$SUDOERS_FILE"
ok "sudoers 설정 완료"

# ───────────────────────────────────────
# 9. 자동 시작 설정 (선택)
# ───────────────────────────────────────
if [ -n "$USER_HOME" ] && [ -d "$USER_HOME" ]; then
    AUTOSTART_DIR="${USER_HOME}/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"

    cat > "${AUTOSTART_DIR}/inspection-health.desktop" << 'AUTOSTART_EOF'
[Desktop Entry]
Type=Application
Name=디스크 건강 검사기 (자동시작)
Exec=bash -c "sleep 3 && pkexec env DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY python3 /opt/inspection/disk_health_gui.py"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
AUTOSTART_EOF

    [ -n "$LOGIN_USER" ] && chown -R "${LOGIN_USER}:${LOGIN_USER}" "$AUTOSTART_DIR" || true
    ok "자동 시작 등록: $AUTOSTART_DIR"
fi

# ───────────────────────────────────────
# 완료 요약
# ───────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}   설치 완료!${NC}"
echo -e "${BOLD}══════════════════════════════════════════${NC}"
echo ""
echo -e "  설치 경로     : ${CYAN}${INSTALL_DIR}${NC}"
echo -e "  마운트 경로   : ${CYAN}/media/cru${NC}"
echo -e "  udev 규칙     : ${CYAN}/etc/udev/rules.d/99-cru-automount.rules${NC}"
echo -e "  데스크탑 바로가기:"
[ -n "$USER_DESKTOP" ] && echo -e "    ${CYAN}${USER_DESKTOP}${NC}"
echo ""
echo -e "  ${YELLOW}CRU 드라이브를 꽂으면 자동으로 /media/cru 에 마운트 됩니다.${NC}"
echo -e "  ${YELLOW}바탕화면 아이콘을 더블클릭하여 프로그램을 실행하세요.${NC}"
echo ""
echo -e "  ${GREEN}[디스크 건강 검사기]${NC} 직접 실행:"
echo -e "    ${CYAN}sudo python3 ${INSTALL_DIR}/disk_health_gui.py${NC}"
echo ""
echo -e "  ${GREEN}[해시 검증기]${NC} 직접 실행:"
echo -e "    ${CYAN}python3 ${INSTALL_DIR}/hash_checker_gui.py${NC}"
echo ""
