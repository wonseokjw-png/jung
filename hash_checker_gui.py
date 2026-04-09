#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
검수 PC - 해시 검증기 (복사 무결성 검사)
Ubuntu 부팅 USB용
모드: 파일 검사 / 폴더 검사(복수 선택 가능)
완료 후 자동 언마운트
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import threading
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# 색상
# ─────────────────────────────────────────────
BG_DARK   = "#0d1117"
BG_CARD   = "#161b22"
BG_HDR    = "#1f2937"
COL_PASS  = "#22c55e"
COL_FAIL  = "#ef4444"
COL_WARN  = "#f59e0b"
COL_SCAN  = "#38bdf8"
COL_TEXT  = "#e2e8f0"
COL_DIM   = "#94a3b8"
COL_SRC   = "#38bdf8"
COL_DST   = "#fb923c"


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except Exception:
        return ""


def get_mounted_partitions():
    """마운트된 파티션 목록 반환: [(표시명, 마운트포인트), ...]"""
    results = []
    try:
        out = run_cmd(["lsblk", "-J", "-o", "NAME,SIZE,MOUNTPOINT,LABEL,FSTYPE"])
        data = json.loads(out)
        for disk in data.get("blockdevices", []):
            for child in disk.get("children", []):
                mp = child.get("mountpoint") or ""
                if not mp or mp in ["/", "/boot", "/boot/efi", "[SWAP]"]:
                    continue
                if mp.startswith("/snap"):
                    continue
                name   = child.get("name", "")
                size   = child.get("size", "")
                label  = child.get("label") or ""
                fstype = child.get("fstype") or ""
                display = f"/dev/{name}  {size}  {mp}"
                if label:
                    display += f"  [{label}]"
                results.append((display, mp))
    except Exception:
        pass
    return results


def compute_file_hash(filepath, algo, progress_cb=None):
    """파일 해시 계산. 진행 콜백(완료 바이트)."""
    h = hashlib.new(algo)
    try:
        size = os.path.getsize(filepath)
        done = 0
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, size)
        return h.hexdigest(), None
    except Exception as e:
        return None, str(e)


def collect_files(base_path):
    """경로 아래 모든 파일을 {상대경로: 절대경로} dict 로 반환."""
    base = Path(base_path)
    result = {}
    if base.is_file():
        result[base.name] = str(base)
    elif base.is_dir():
        for p in base.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(base))
                result[rel] = str(p)
    return result


def format_size(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def unmount_path(mount_point):
    try:
        r = subprocess.run(["umount", mount_point], capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


# ─────────────────────────────────────────────
# 경로 선택 패널
# ─────────────────────────────────────────────
class PathPanel(tk.LabelFrame):
    """원본 또는 대상 경로를 여러 개 담는 패널."""

    def __init__(self, parent, title, accent_color, **kwargs):
        super().__init__(parent, text=f"  {title}  ",
                         bg=BG_CARD, fg=accent_color,
                         font=("Ubuntu", 11, "bold"),
                         bd=1, relief="solid", **kwargs)
        self.accent = accent_color
        self._build()

    def _build(self):
        # 모드 선택
        mode_row = tk.Frame(self, bg=BG_CARD)
        mode_row.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(mode_row, text="선택 모드:", bg=BG_CARD,
                 fg=COL_DIM, font=("Ubuntu", 9)).pack(side="left")
        self.mode = tk.StringVar(value="disk")
        for val, lbl in [("disk", "디스크"), ("folder", "폴더"), ("file", "파일")]:
            tk.Radiobutton(mode_row, text=lbl,
                           variable=self.mode, value=val,
                           bg=BG_CARD, fg=COL_TEXT,
                           selectcolor=self.accent,
                           activebackground=BG_CARD,
                           font=("Ubuntu", 9)).pack(side="left", padx=6)

        # 마운트된 디스크 드롭다운
        disk_row = tk.Frame(self, bg=BG_CARD)
        disk_row.pack(fill="x", padx=8, pady=2)
        tk.Label(disk_row, text="마운트 디스크:", bg=BG_CARD,
                 fg=COL_DIM, font=("Ubuntu", 9)).pack(side="left")
        self.disk_var = tk.StringVar()
        self.disk_cb = ttk.Combobox(disk_row, textvariable=self.disk_var,
                                    font=("Ubuntu", 9), state="readonly", width=40)
        self.disk_cb.pack(side="left", padx=4)
        tk.Button(disk_row, text="↻", command=self.refresh_disks,
                  bg=BG_HDR, fg=COL_TEXT,
                  font=("Ubuntu", 10), padx=4, pady=0, relief="flat").pack(side="left")

        # 경로 목록
        list_row = tk.Frame(self, bg=BG_CARD)
        list_row.pack(fill="both", expand=True, padx=8, pady=2)
        self.listbox = tk.Listbox(list_row, bg="#0a0e14", fg=self.accent,
                                  font=("Ubuntu Mono", 9),
                                  selectbackground="#1e3a5f",
                                  height=7, activestyle="none")
        sb = ttk.Scrollbar(list_row, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 버튼 행
        btn_row = tk.Frame(self, bg=BG_CARD)
        btn_row.pack(fill="x", padx=8, pady=(2, 6))
        for txt, cmd, bg in [
            ("+ 추가",    self.add_path,  "#166534"),
            ("- 제거",    self.remove_path,"#7f1d1d"),
            ("전체 삭제", self.clear_all,  "#374151"),
        ]:
            tk.Button(btn_row, text=txt, command=cmd,
                      bg=bg, fg="white",
                      font=("Ubuntu", 9), padx=8, pady=3,
                      relief="flat", cursor="hand2").pack(side="left", padx=2)

        self.refresh_disks()

    def refresh_disks(self):
        parts = get_mounted_partitions()
        self._disk_map = {d: mp for d, mp in parts}
        self.disk_cb["values"] = list(self._disk_map.keys())
        if self._disk_map:
            self.disk_cb.current(0)

    def add_path(self):
        mode = self.mode.get()
        if mode == "disk":
            key = self.disk_var.get()
            mp  = self._disk_map.get(key)
            if mp:
                self._add(mp)
            else:
                messagebox.showwarning("알림", "마운트된 디스크를 선택하거나 ↻ 로 새로고침 하세요.")
        elif mode == "folder":
            paths = []
            # 복수 폴더 선택 반복
            while True:
                p = filedialog.askdirectory(title="폴더 선택 (취소 시 완료)")
                if not p:
                    break
                paths.append(p)
                if not messagebox.askyesno("계속", "폴더를 더 추가하시겠습니까?"):
                    break
            for p in paths:
                self._add(p)
        else:  # file
            paths = filedialog.askopenfilenames(title="파일 선택")
            for p in paths:
                self._add(p)

    def _add(self, path):
        existing = self.listbox.get(0, "end")
        if path not in existing:
            self.listbox.insert("end", path)

    def remove_path(self):
        sel = self.listbox.curselection()
        if sel:
            self.listbox.delete(sel[0])

    def clear_all(self):
        self.listbox.delete(0, "end")

    def get_paths(self):
        return list(self.listbox.get(0, "end"))


# ─────────────────────────────────────────────
# 결과 행
# ─────────────────────────────────────────────
ROW_COLS = ("파일 경로", "크기", "원본 해시 (앞 16자)", "대상 해시 (앞 16자)", "결과")

class ResultTable(ttk.Treeview):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, columns=ROW_COLS, show="headings", **kwargs)
        widths = [360, 80, 160, 160, 90]
        for col, w in zip(ROW_COLS, widths):
            self.heading(col, text=col)
            self.column(col, width=w, anchor="w")
        self.tag_configure("match",   foreground=COL_PASS)
        self.tag_configure("mismatch",foreground=COL_FAIL)
        self.tag_configure("missing", foreground=COL_WARN)
        self.tag_configure("extra",   foreground=COL_DIM)

    def clear(self):
        for item in self.get_children():
            self.delete(item)

    def add_row(self, path, size, src_h, dst_h, tag, result_text):
        self.insert("", "end",
                    values=(path,
                            size,
                            (src_h[:16] if src_h else "-"),
                            (dst_h[:16] if dst_h else "-"),
                            result_text),
                    tags=(tag,))
        self.yview_moveto(1.0)


# ─────────────────────────────────────────────
# 메인 앱
# ─────────────────────────────────────────────
class HashCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("검수 PC — 해시 검증기 (복사 무결성 검사)")
        self.root.geometry("1400x920")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(True, True)
        self._running = False
        self._build_ui()

    def _build_ui(self):
        # 헤더
        hdr = tk.Frame(self.root, bg=BG_HDR, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="✔  검수 PC  —  해시 검증기  (복사 무결성 검사)",
                 font=("Ubuntu", 18, "bold"), fg=COL_SCAN, bg=BG_HDR).pack()
        tk.Label(hdr,
                 text="디스크 / 폴더 / 파일 단위 검증  |  MD5 · SHA1 · SHA256 · SHA512  |  완료 후 자동 언마운트",
                 font=("Ubuntu", 10), fg=COL_DIM, bg=BG_HDR).pack()

        # 경로 패널 (좌우)
        panel_row = tk.Frame(self.root, bg=BG_DARK)
        panel_row.pack(fill="x", padx=16, pady=8)
        panel_row.columnconfigure(0, weight=1)
        panel_row.columnconfigure(1, weight=1)

        self.src_panel = PathPanel(panel_row, "원본 경로 (Source)", COL_SRC)
        self.src_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.dst_panel = PathPanel(panel_row, "대상 경로 (Destination)", COL_DST)
        self.dst_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # 옵션 + 제어 버튼
        ctrl = tk.Frame(self.root, bg=BG_DARK)
        ctrl.pack(fill="x", padx=16, pady=2)

        # 해시 알고리즘
        tk.Label(ctrl, text="해시 알고리즘:", bg=BG_DARK,
                 fg=COL_DIM, font=("Ubuntu", 10)).pack(side="left")
        self.algo_var = tk.StringVar(value="sha256")
        for algo in ["md5", "sha1", "sha256", "sha512"]:
            tk.Radiobutton(ctrl, text=algo.upper(),
                           variable=self.algo_var, value=algo,
                           bg=BG_DARK, fg=COL_TEXT,
                           selectcolor="#1d4ed8",
                           activebackground=BG_DARK,
                           font=("Ubuntu", 10)).pack(side="left", padx=6)

        # 비교 방식
        tk.Label(ctrl, text="  비교:", bg=BG_DARK,
                 fg=COL_DIM, font=("Ubuntu", 10)).pack(side="left", padx=(12, 0))
        self.mode_var = tk.StringVar(value="paired")
        for val, lbl in [("paired", "순서 대응 (1:1)"), ("flat", "파일명만 비교")]:
            tk.Radiobutton(ctrl, text=lbl,
                           variable=self.mode_var, value=val,
                           bg=BG_DARK, fg=COL_TEXT,
                           selectcolor="#1d4ed8",
                           activebackground=BG_DARK,
                           font=("Ubuntu", 10)).pack(side="left", padx=6)

        # 오른쪽 버튼
        self.start_btn = tk.Button(ctrl, text="▶  해시 검증 시작",
                                   command=self._start_check,
                                   bg="#1d4ed8", fg="white",
                                   font=("Ubuntu", 11, "bold"),
                                   padx=18, pady=5, relief="flat", cursor="hand2")
        self.start_btn.pack(side="right", padx=4)

        tk.Button(ctrl, text="전체 언마운트",
                  command=self._unmount_all,
                  bg="#991b1b", fg="white",
                  font=("Ubuntu", 11, "bold"),
                  padx=14, pady=5, relief="flat", cursor="hand2").pack(side="right", padx=4)

        tk.Button(ctrl, text="결과 저장",
                  command=self._save_results,
                  bg="#065f46", fg="white",
                  font=("Ubuntu", 11),
                  padx=12, pady=5, relief="flat", cursor="hand2").pack(side="right", padx=4)

        # 진행 바
        prog_row = tk.Frame(self.root, bg=BG_DARK)
        prog_row.pack(fill="x", padx=16, pady=4)
        self.prog_var = tk.DoubleVar()
        self.prog_bar = ttk.Progressbar(prog_row, variable=self.prog_var, maximum=100)
        self.prog_bar.pack(fill="x")
        self.prog_lbl_var = tk.StringVar(value="대기 중...")
        tk.Label(prog_row, textvariable=self.prog_lbl_var,
                 bg=BG_DARK, fg=COL_DIM, font=("Ubuntu", 9")).pack(anchor="e")

        # 결과 테이블
        tbl_frm = tk.Frame(self.root, bg=BG_DARK)
        tbl_frm.pack(fill="both", expand=True, padx=16, pady=4)

        style = ttk.Style()
        style.configure("Treeview",
                         background="#0a0e14",
                         foreground=COL_TEXT,
                         fieldbackground="#0a0e14",
                         font=("Ubuntu Mono", 9),
                         rowheight=22)
        style.configure("Treeview.Heading",
                         background=BG_HDR, foreground=COL_SCAN,
                         font=("Ubuntu", 9, "bold"))
        style.map("Treeview", background=[("selected", "#1e3a5f")])

        self.table = ResultTable(tbl_frm, height=14)
        vsb = ttk.Scrollbar(tbl_frm, orient="vertical",   command=self.table.yview)
        hsb = ttk.Scrollbar(tbl_frm, orient="horizontal",  command=self.table.xview)
        self.table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self.table.pack(fill="both", expand=True)

        # 요약 바
        sum_frm = tk.Frame(self.root, bg=BG_HDR, pady=5)
        sum_frm.pack(fill="x", padx=16, pady=(0, 8))
        self.sum_var = tk.StringVar(value="검증 대기 중...")
        self.sum_lbl = tk.Label(sum_frm, textvariable=self.sum_var,
                                font=("Ubuntu", 12, "bold"),
                                fg=COL_DIM, bg=BG_HDR)
        self.sum_lbl.pack()

        # 로그
        log_frm = tk.LabelFrame(self.root, text=" 로그 ",
                                 bg=BG_DARK, fg=COL_DIM,
                                 font=("Ubuntu", 9))
        log_frm.pack(fill="x", padx=16, pady=(0, 10))
        self.log_box = scrolledtext.ScrolledText(
            log_frm, height=5, bg="#0a0e14", fg=COL_PASS,
            font=("Ubuntu Mono", 9), state="disabled")
        self.log_box.pack(fill="x", padx=4, pady=4)

    # ────────────────────────────────
    # 로그
    # ────────────────────────────────
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _set_progress(self, value, label=""):
        self.prog_var.set(value)
        if label:
            self.prog_lbl_var.set(label)

    # ────────────────────────────────
    # 검증 시작
    # ────────────────────────────────
    def _start_check(self):
        if self._running:
            messagebox.showwarning("실행 중", "이미 검증이 진행 중입니다.")
            return

        src_paths = self.src_panel.get_paths()
        dst_paths = self.dst_panel.get_paths()

        if not src_paths:
            messagebox.showerror("오류", "원본 경로를 하나 이상 추가하세요.")
            return
        if not dst_paths:
            messagebox.showerror("오류", "대상 경로를 하나 이상 추가하세요.")
            return

        mode = self.mode_var.get()
        if mode == "paired" and len(src_paths) != len(dst_paths):
            messagebox.showerror("오류",
                "순서 대응(1:1) 모드에서는 원본과 대상 경로 수가 같아야 합니다.\n"
                f"원본: {len(src_paths)}개  /  대상: {len(dst_paths)}개")
            return

        self.table.clear()
        self._running = True
        self.start_btn.config(state="disabled")
        self._check_stats = {"match": 0, "mismatch": 0, "missing": 0, "error": 0}

        threading.Thread(target=self._run_check,
                         args=(src_paths, dst_paths, mode),
                         daemon=True).start()

    def _run_check(self, src_paths, dst_paths, mode):
        algo = self.algo_var.get()
        stats = self._check_stats
        self.log("=" * 56)
        self.log(f"해시 검증 시작  알고리즘:{algo.upper()}  모드:{mode}")

        try:
            if mode == "paired":
                pairs = list(zip(src_paths, dst_paths))
            else:
                # flat: 모든 src x 모든 dst 파일을 이름으로 매칭
                pairs = [(s, d) for s in src_paths for d in dst_paths]

            # 전체 파일 목록 수집
            all_pairs = []   # (rel_path, src_file, dst_file_or_None)
            for src_base, dst_base in pairs:
                src_files = collect_files(src_base)
                dst_files = collect_files(dst_base)
                for rel, src_file in src_files.items():
                    dst_file = dst_files.get(rel)
                    all_pairs.append((rel, src_file, dst_file))
                # 대상에만 있는 파일
                for rel, dst_file in dst_files.items():
                    if rel not in src_files:
                        all_pairs.append((rel, None, dst_file))

            total = len(all_pairs)
            if total == 0:
                self.root.after(0, lambda: messagebox.showwarning("알림", "비교할 파일이 없습니다."))
                return

            self.log(f"총 비교 파일 수: {total:,}개")

            for i, (rel, src_file, dst_file) in enumerate(all_pairs):
                pct = (i + 1) / total * 100
                self.root.after(0, self._set_progress, pct,
                                f"({i+1:,}/{total:,})  {rel[:60]}")

                if src_file is None:
                    # 대상에만 존재
                    size_s = format_size(os.path.getsize(dst_file)) if dst_file else "-"
                    self.root.after(0, self.table.add_row,
                                    rel, size_s, None, None, "extra", "⊕ 대상 추가")
                    stats["missing"] += 1

                elif dst_file is None:
                    # 원본에만 존재 (누락)
                    size_s = format_size(os.path.getsize(src_file))
                    src_h, err = compute_file_hash(src_file, algo)
                    self.root.after(0, self.table.add_row,
                                    rel, size_s, src_h, None, "missing", "⚠ 누락")
                    stats["missing"] += 1

                else:
                    size_s = format_size(os.path.getsize(src_file))
                    src_h, err1 = compute_file_hash(src_file, algo)
                    dst_h, err2 = compute_file_hash(dst_file, algo)

                    if err1 or err2:
                        self.root.after(0, self.table.add_row,
                                        rel, size_s, src_h, dst_h, "missing",
                                        f"오류: {err1 or err2}")
                        stats["error"] += 1
                    elif src_h == dst_h:
                        self.root.after(0, self.table.add_row,
                                        rel, size_s, src_h, dst_h, "match", "✓ 일치")
                        stats["match"] += 1
                    else:
                        self.root.after(0, self.table.add_row,
                                        rel, size_s, src_h, dst_h, "mismatch", "✗ 불일치")
                        stats["mismatch"] += 1
                        self.log(f"불일치: {rel}")

        except Exception as e:
            self.log(f"검증 오류: {e}")
        finally:
            self._running = False
            self.root.after(0, self._finish_check)

    def _finish_check(self):
        s = self._check_stats
        self.start_btn.config(state="normal")
        self._set_progress(100, "완료")

        total = s["match"] + s["mismatch"] + s["missing"] + s["error"]
        if s["mismatch"] == 0 and s["missing"] == 0 and s["error"] == 0:
            summary = f"✅  모든 파일 일치  ({s['match']:,}개 / {total:,}개)"
            self.sum_lbl.config(fg=COL_PASS)
            icon = "info"
        elif s["mismatch"] > 0:
            summary = (f"❌  불일치 발견  "
                       f"일치:{s['match']:,}  불일치:{s['mismatch']:,}  "
                       f"누락:{s['missing']:,}  오류:{s['error']:,}")
            self.sum_lbl.config(fg=COL_FAIL)
            icon = "warning"
        else:
            summary = (f"⚠  주의  "
                       f"일치:{s['match']:,}  누락:{s['missing']:,}  오류:{s['error']:,}")
            self.sum_lbl.config(fg=COL_WARN)
            icon = "warning"

        self.sum_var.set(summary)
        self.log(summary)
        self.log("=" * 56)

        # 완료 팝업 + 언마운트 확인
        msg = summary + "\n\n언마운트 하시겠습니까?"
        if messagebox.askyesno("검증 완료", msg, icon=icon):
            self._unmount_all(silent=True)

    # ────────────────────────────────
    # 언마운트
    # ────────────────────────────────
    def _unmount_all(self, silent=False):
        if not silent:
            if not messagebox.askyesno("확인", "선택된 경로의 디스크를 언마운트 하시겠습니까?"):
                return
        paths = self.src_panel.get_paths() + self.dst_panel.get_paths()
        done = []
        for p in paths:
            if unmount_path(p):
                done.append(p)
                self.log(f"언마운트: {p}")
        if not silent:
            messagebox.showinfo("완료", "언마운트 완료\n\n" + "\n".join(done) if done else "마운트된 경로 없음")

    # ────────────────────────────────
    # 결과 저장
    # ────────────────────────────────
    def _save_results(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("CSV", "*.csv")],
            initialfile=f"hash_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        if not path:
            return
        try:
            lines = ["\t".join(ROW_COLS)]
            for item in self.table.get_children():
                vals = self.table.item(item, "values")
                lines.append("\t".join(str(v) for v in vals))
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo("저장 완료", f"결과 저장됨:\n{path}")
        except Exception as e:
            messagebox.showerror("오류", f"저장 실패: {e}")


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = HashCheckerApp(root)
    root.mainloop()
