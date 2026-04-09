#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
검수 PC - 디스크 건강 상태 검사기
Ubuntu 부팅 USB용 | CRU 외장 하드 12개 지원
자동 감지 → SMART 검사 → 색상 표시 → 자동 언마운트
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import threading
import json
import os
import time
from datetime import datetime


# ─────────────────────────────────────────────
# 색상 팔레트
# ─────────────────────────────────────────────
BG_DARK    = "#0d1117"
BG_CARD    = "#161b22"
BG_HEADER  = "#1f2937"
COL_PASS   = "#22c55e"   # 녹색  - 정상
COL_WARN   = "#f59e0b"   # 주황  - 주의
COL_FAIL   = "#ef4444"   # 빨강  - 불량
COL_SCAN   = "#38bdf8"   # 하늘  - 스캔 중
COL_IDLE   = "#6b7280"   # 회색  - 대기
COL_ACCENT = "#38bdf8"
COL_TEXT   = "#e2e8f0"
COL_DIM    = "#94a3b8"


def run_cmd(cmd, timeout=30):
    """명령어 실행 후 stdout 반환. 실패 시 빈 문자열."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout + r.stderr
    except Exception:
        return ""


def get_block_disks():
    """lsblk JSON으로 디스크(type=disk) 목록 반환."""
    try:
        out = run_cmd([
            "lsblk", "-J",
            "-o", "NAME,SIZE,TYPE,MOUNTPOINT,VENDOR,MODEL,SERIAL,TRAN,HOTPLUG,ROTA"
        ])
        data = json.loads(out)
        return [d for d in data.get("blockdevices", []) if d.get("type") == "disk"]
    except Exception:
        return []


def get_smart(device):
    """smartctl로 SMART 정보 파싱 후 dict 반환."""
    info = {
        "health":       "UNKNOWN",
        "model":        "",
        "serial":       "",
        "temperature":  None,
        "reallocated":  None,
        "pending":      None,
        "uncorrectable":None,
        "power_hours":  None,
        "ssd":          False,
    }
    raw_info = run_cmd(["sudo", "smartctl", "-i", f"/dev/{device}"])
    raw_attr = run_cmd(["sudo", "smartctl", "-H", "-A", f"/dev/{device}"])
    combined = raw_info + raw_attr

    # 건강 상태
    if "PASSED" in combined or ": OK" in combined:
        info["health"] = "PASSED"
    elif "FAILED" in combined:
        info["health"] = "FAILED"

    # SSD 판별
    if "Solid State" in combined or "SSD" in combined or "NVM" in combined:
        info["ssd"] = True

    for line in combined.splitlines():
        l = line.strip()

        if "Device Model" in l or "Product:" in l:
            info["model"] = l.split(":", 1)[-1].strip()

        if "Serial Number" in l or "Serial number" in l:
            info["serial"] = l.split(":", 1)[-1].strip()

        # SMART 속성값 (10번째 컬럼 = RAW_VALUE)
        parts = l.split()
        if len(parts) >= 10:
            attr = parts[1] if len(parts) > 1 else ""
            try:
                raw_val = int(parts[9])
            except (ValueError, IndexError):
                raw_val = None

            if raw_val is None:
                continue

            if "Temperature" in attr or "Airflow_Temp" in attr:
                info["temperature"] = raw_val
            elif "Reallocated_Sector" in attr or "Reallocated_Event" in attr:
                info["reallocated"] = raw_val
            elif "Current_Pending_Sector" in attr:
                info["pending"] = raw_val
            elif "Offline_Uncorrectable" in attr:
                info["uncorrectable"] = raw_val
            elif "Power_On_Hours" in attr:
                info["power_hours"] = raw_val

    return info


def unmount_device(device):
    """디스크의 마운트된 파티션 전체 언마운트."""
    msgs = []
    try:
        out = run_cmd(["lsblk", "-J", "-o", "NAME,MOUNTPOINT", f"/dev/{device}"])
        data = json.loads(out)
        for dev in data.get("blockdevices", []):
            # 자기 자신 마운트
            mp = dev.get("mountpoint")
            if mp:
                run_cmd(["umount", f"/dev/{dev['name']}"])
                msgs.append(f"/dev/{dev['name']} 언마운트")
            # 파티션
            for child in dev.get("children", []):
                mp = child.get("mountpoint")
                if mp:
                    run_cmd(["umount", f"/dev/{child['name']}"])
                    msgs.append(f"/dev/{child['name']} 언마운트")
    except Exception as e:
        msgs.append(f"오류: {e}")
    return msgs


# ─────────────────────────────────────────────
# 디스크 카드 위젯
# ─────────────────────────────────────────────
class DiskCard(tk.Frame):
    def __init__(self, parent, index, device_info, on_unmount_cb, **kwargs):
        super().__init__(parent, bg=BG_CARD, bd=1, relief="solid", **kwargs)
        self.device  = device_info.get("name", "?")
        self.index   = index
        self.on_unmount_cb = on_unmount_cb
        self._build(device_info)

    def _build(self, dev):
        pad = {"padx": 8, "pady": 2}

        # ── 슬롯 번호 + 장치명
        top = tk.Frame(self, bg=BG_HEADER)
        top.pack(fill="x")
        tk.Label(top, text=f"슬롯 {self.index:02d}",
                 font=("Ubuntu Mono", 9, "bold"),
                 fg=COL_DIM, bg=BG_HEADER).pack(side="left", padx=6, pady=3)
        tk.Label(top, text=f"/dev/{self.device}",
                 font=("Ubuntu Mono", 11, "bold"),
                 fg=COL_ACCENT, bg=BG_HEADER).pack(side="left")

        size  = dev.get("size", "-")
        tran  = (dev.get("tran") or "").upper()
        vendor = (dev.get("vendor") or "").strip()
        model  = (dev.get("model") or "").strip() or vendor or "알 수 없음"
        tk.Label(top, text=f"{tran}  {size}",
                 font=("Ubuntu", 9), fg=COL_DIM, bg=BG_HEADER).pack(side="right", padx=6)

        # ── 모델명
        tk.Label(self, text=model[:28],
                 font=("Ubuntu", 9), fg=COL_DIM, bg=BG_CARD).pack(**pad)

        # ── 상태 표시등
        self.status_var = tk.StringVar(value="● 대기 중")
        self.status_lbl = tk.Label(self,
                                   textvariable=self.status_var,
                                   font=("Ubuntu", 13, "bold"),
                                   fg=COL_IDLE, bg=BG_CARD)
        self.status_lbl.pack(pady=(4, 2))

        # ── 세부 정보
        self.temp_var    = tk.StringVar(value="온도: -")
        self.sect_var    = tk.StringVar(value="불량섹터: -")
        self.hours_var   = tk.StringVar(value="사용시간: -")
        self.serial_var  = tk.StringVar(value="S/N: -")

        for v in [self.temp_var, self.sect_var, self.hours_var, self.serial_var]:
            tk.Label(self, textvariable=v,
                     font=("Ubuntu Mono", 8), fg=COL_DIM, bg=BG_CARD).pack()

        # ── 버튼
        btn_row = tk.Frame(self, bg=BG_CARD)
        btn_row.pack(pady=6)
        self.scan_btn = tk.Button(btn_row, text="검사",
                                  command=self.start_scan,
                                  bg="#1d4ed8", fg="white",
                                  font=("Ubuntu", 9, "bold"),
                                  padx=10, pady=3, relief="flat", cursor="hand2")
        self.scan_btn.pack(side="left", padx=3)

        tk.Button(btn_row, text="언마운트",
                  command=self.do_unmount,
                  bg="#7f1d1d", fg="white",
                  font=("Ubuntu", 9),
                  padx=8, pady=3, relief="flat", cursor="hand2").pack(side="left", padx=3)

    # ── 상태 변경
    def set_status(self, text, color):
        self.status_var.set(text)
        self.status_lbl.config(fg=color)

    # ── SMART 스캔
    def start_scan(self, callback=None):
        self.scan_btn.config(state="disabled")
        self.set_status("● 스캔 중...", COL_SCAN)

        def _run():
            smart = get_smart(self.device)
            health = smart["health"]

            if health == "PASSED":
                # 추가 경고 확인
                realloc = smart.get("reallocated") or 0
                pending = smart.get("pending") or 0
                unc     = smart.get("uncorrectable") or 0
                temp    = smart.get("temperature") or 0

                if realloc > 0 or pending > 0 or unc > 0 or temp >= 55:
                    self.set_status("● 주의 필요", COL_WARN)
                else:
                    self.set_status("● 정상 (PASSED)", COL_PASS)
            elif health == "FAILED":
                self.set_status("● 불량 (FAILED)", COL_FAIL)
            else:
                self.set_status("● 확인 불가", COL_WARN)

            # 세부 정보 업데이트
            temp = smart.get("temperature")
            if temp is not None:
                color = COL_FAIL if temp >= 55 else COL_WARN if temp >= 45 else COL_PASS
                self.temp_var.set(f"온도: {temp}°C")
                # 온도 라벨 색상은 직접 접근 불가 → 변수만 업데이트

            realloc = smart.get("reallocated")
            if realloc is not None:
                self.sect_var.set(f"불량섹터: {realloc}개{'  ⚠' if realloc > 0 else ''}")

            hours = smart.get("power_hours")
            if hours is not None:
                self.hours_var.set(f"사용시간: {hours:,}h ({hours//24}일)")

            serial = smart.get("serial")
            if serial:
                self.serial_var.set(f"S/N: {serial[:18]}")

            self.scan_btn.config(state="normal")
            if callback:
                callback(self.device, health, smart)

        threading.Thread(target=_run, daemon=True).start()

    def do_unmount(self):
        msgs = unmount_device(self.device)
        if msgs:
            messagebox.showinfo("언마운트 완료", "\n".join(msgs))
        else:
            messagebox.showinfo("언마운트", f"/dev/{self.device}: 마운트된 파티션 없음")


# ─────────────────────────────────────────────
# 메인 앱
# ─────────────────────────────────────────────
class DiskHealthApp:
    def __init__(self, root):
        self.root = root
        self.root.title("검수 PC - 디스크 건강 상태 검사기")
        self.root.geometry("1280x860")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(True, True)

        self.cards = {}           # device_name → DiskCard
        self.scan_results = {}    # device_name → (health, smart_dict)
        self._prev_devices = set()
        self._auto_running = False

        self._build_ui()
        self._start_monitor()

    # ────────────────────────────────
    # UI 구성
    # ────────────────────────────────
    def _build_ui(self):
        # 헤더
        hdr = tk.Frame(self.root, bg=BG_HEADER, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔍  검수 PC  —  디스크 건강 상태 검사기",
                 font=("Ubuntu", 18, "bold"), fg=COL_ACCENT, bg=BG_HEADER).pack()
        tk.Label(hdr, text="CRU 외장 하드 최대 12개 | S.M.A.R.T 자동 분석 | 완료 후 자동 언마운트",
                 font=("Ubuntu", 10), fg=COL_DIM, bg=BG_HEADER).pack()

        # 툴바
        bar = tk.Frame(self.root, bg=BG_DARK, pady=6)
        bar.pack(fill="x", padx=16)

        self._btn("전체 스캔",    bar, self._scan_all,    "#1d4ed8")
        self._btn("전체 언마운트", bar, self._unmount_all,  "#991b1b")
        self._btn("목록 새로고침", bar, self._refresh_cards, "#065f46")

        self.status_var = tk.StringVar(value="디스크 감지 중...")
        tk.Label(bar, textvariable=self.status_var,
                 font=("Ubuntu", 10), fg=COL_DIM, bg=BG_DARK).pack(side="right", padx=10)

        # 범례
        leg = tk.Frame(self.root, bg=BG_HEADER, pady=4)
        leg.pack(fill="x", padx=16)
        legends = [
            ("● 정상 (PASSED)", COL_PASS),
            ("● 주의 필요",     COL_WARN),
            ("● 불량 (FAILED)", COL_FAIL),
            ("● 스캔 중",       COL_SCAN),
            ("● 대기 중",       COL_IDLE),
        ]
        for txt, col in legends:
            tk.Label(leg, text=txt, font=("Ubuntu", 9), fg=col, bg=BG_HEADER).pack(side="left", padx=12)

        # 카드 그리드 (스크롤 가능)
        outer = tk.Frame(self.root, bg=BG_DARK)
        outer.pack(fill="both", expand=True, padx=16, pady=8)

        self.canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.grid_frame = tk.Frame(self.canvas, bg=BG_DARK)
        self.grid_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 로그
        log_frm = tk.LabelFrame(self.root, text=" 실시간 로그 ",
                                 bg=BG_DARK, fg=COL_DIM,
                                 font=("Ubuntu", 9))
        log_frm.pack(fill="x", padx=16, pady=(0, 10))
        self.log_box = scrolledtext.ScrolledText(
            log_frm, height=7, bg="#0a0e14", fg=COL_PASS,
            font=("Ubuntu Mono", 9), state="disabled",
            insertbackground="white")
        self.log_box.pack(fill="x", padx=4, pady=4)

    def _btn(self, text, parent, cmd, bg):
        tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg="white",
                  font=("Ubuntu", 10, "bold"),
                  padx=16, pady=6, relief="flat", cursor="hand2").pack(side="left", padx=4)

    # ────────────────────────────────
    # 로그
    # ────────────────────────────────
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ────────────────────────────────
    # 카드 그리드 갱신
    # ────────────────────────────────
    def _refresh_cards(self):
        disks = get_block_disks()

        # 부팅 USB 자신은 제외 (루트 마운트 된 디스크)
        boot_disk = self._detect_boot_disk()
        disks = [d for d in disks if d.get("name") != boot_disk]

        current_devs = {d["name"] for d in disks}

        # 사라진 디스크 카드 제거
        removed = set(self.cards.keys()) - current_devs
        for name in removed:
            self.cards[name].destroy()
            del self.cards[name]
            self.log(f"/dev/{name} 제거됨")

        # 새 디스크 카드 추가
        added = current_devs - set(self.cards.keys())
        for d in disks:
            name = d["name"]
            if name in added:
                self.log(f"/dev/{name} 감지됨 ({d.get('size','-')})")

        # 전체 재배치 (4열)
        for w in self.grid_frame.winfo_children():
            w.grid_forget()

        for col in range(4):
            self.grid_frame.columnconfigure(col, weight=1, minsize=290)

        self.cards = {}
        for i, d in enumerate(disks):
            name = d["name"]
            card = DiskCard(
                self.grid_frame, i + 1, d,
                on_unmount_cb=self.log,
                width=280
            )
            card.grid(row=i // 4, column=i % 4, padx=6, pady=6, sticky="nsew")
            self.cards[name] = card

        count = len(disks)
        icon  = "✅" if count >= 12 else "⚠️" if count > 0 else "❌"
        self.status_var.set(
            f"{icon}  감지된 디스크: {count}개  "
            f"(목표 12개)  |  {datetime.now().strftime('%H:%M:%S')}"
        )
        self._prev_devices = current_devs

    def _detect_boot_disk(self):
        """루트(/) 마운트 포인트를 가진 디스크 이름 반환."""
        try:
            out = run_cmd(["lsblk", "-J", "-o", "NAME,TYPE,MOUNTPOINT"])
            data = json.loads(out)
            for disk in data.get("blockdevices", []):
                if disk.get("mountpoint") == "/":
                    return disk["name"]
                for child in disk.get("children", []):
                    if child.get("mountpoint") == "/":
                        return disk["name"]
        except Exception:
            pass
        return None

    # ────────────────────────────────
    # 전체 스캔
    # ────────────────────────────────
    def _scan_all(self):
        if not self.cards:
            messagebox.showinfo("알림", "감지된 디스크가 없습니다.\n먼저 CRU 드라이브를 연결하세요.")
            return

        def _run():
            self.log("=" * 48)
            self.log(f"전체 스캔 시작 — {len(self.cards)}개 디스크")
            done_event = threading.Event()
            results = {}
            remaining = [len(self.cards)]

            def _on_done(device, health, smart):
                results[device] = (health, smart)
                remaining[0] -= 1
                self.log(f"/dev/{device}  →  {health}")
                if remaining[0] == 0:
                    done_event.set()

            for card in self.cards.values():
                card.start_scan(callback=_on_done)
                time.sleep(0.3)   # SMART 충돌 방지

            done_event.wait(timeout=120)

            # 요약
            passed = sum(1 for h, _ in results.values() if h == "PASSED")
            failed = sum(1 for h, _ in results.values() if h == "FAILED")
            warn   = len(results) - passed - failed
            self.log(f"스캔 완료 ▶ 정상:{passed}  주의:{warn}  불량:{failed}")
            self.log("=" * 48)

            # 완료 후 자동 언마운트 확인
            self.root.after(0, lambda: self._post_scan_dialog(passed, warn, failed))

        threading.Thread(target=_run, daemon=True).start()

    def _post_scan_dialog(self, passed, warn, failed):
        total = passed + warn + failed
        if failed > 0:
            msg = (f"⚠ 불량 디스크 {failed}개 발견!\n\n"
                   f"정상: {passed}개  /  주의: {warn}개  /  불량: {failed}개\n\n"
                   "검사 완료 후 언마운트 하시겠습니까?")
            icon = "warning"
        elif warn > 0:
            msg = (f"주의 필요 디스크 {warn}개 있음\n\n"
                   f"정상: {passed}개  /  주의: {warn}개\n\n"
                   "검사 완료 후 언마운트 하시겠습니까?")
            icon = "warning"
        else:
            msg = (f"✅ 모든 디스크 정상!\n\n"
                   f"총 {total}개 디스크 모두 PASSED\n\n"
                   "언마운트 하시겠습니까?")
            icon = "info"

        if messagebox.askyesno("검사 완료", msg, icon=icon):
            self._unmount_all(silent=True)

    # ────────────────────────────────
    # 전체 언마운트
    # ────────────────────────────────
    def _unmount_all(self, silent=False):
        if not silent:
            if not messagebox.askyesno("확인", "모든 CRU 외장 디스크를 언마운트 하시겠습니까?"):
                return
        all_msgs = []
        for name in list(self.cards.keys()):
            msgs = unmount_device(name)
            all_msgs.extend(msgs)
            for m in msgs:
                self.log(m)
        self.log("전체 언마운트 완료")
        if not silent:
            messagebox.showinfo("완료", "전체 언마운트 완료\n\n" + "\n".join(all_msgs) if all_msgs else "마운트된 파티션 없음")

    # ────────────────────────────────
    # 새 디스크 자동 감지 모니터
    # ────────────────────────────────
    def _start_monitor(self):
        self._refresh_cards()

        def _monitor():
            while True:
                time.sleep(4)
                disks = get_block_disks()
                boot  = self._detect_boot_disk()
                disks = [d for d in disks if d.get("name") != boot]
                current = {d["name"] for d in disks}
                if current != self._prev_devices:
                    self.root.after(0, self._refresh_cards)

        t = threading.Thread(target=_monitor, daemon=True)
        t.start()


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = DiskHealthApp(root)
    root.mainloop()
