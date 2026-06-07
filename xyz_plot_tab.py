"""
xyz_plot_tab.py
XY표 만들기 탭의 UI 모듈.
main.py의 Notebook에 탭으로 추가되어 사용됩니다.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from utils import ScrollableFrame
from xyz_plot_engine import (
    AXIS_COL, AXIS_ROW,
    CELL_LONGEST_EDGE, CELL_TIGHT,
    FONT_AUTO, FONT_FIT, FONT_MANUAL,
    METHOD_CROP, METHOD_SCALE,
    RESIZE_CUSTOM, RESIZE_LARGEST, RESIZE_SMALLEST,
    BuildResult, FolderEntry, XYPlotConfig,
    build_plot, build_preview, save_image, save_preview_image,
    collect_images,
)

GRID_CELL = 60
GRID_MAX  = 12


class XYPlotGUI:
    """
    XY표 만들기 탭 전체 UI.
    main.py에서 아래처럼 사용합니다:

        tab = ttk.Frame(notebook)
        notebook.add(tab, text="XY표 만들기")
        XYPlotGUI(tab, get_cores_func, logger)
    """

    def __init__(self, parent: ttk.Frame, get_num_cores, logger=None):
        self.parent        = parent
        self.get_num_cores = get_num_cores
        self.logger        = logger

        self._folder_entries: list[tuple[tk.StringVar, tk.StringVar]] = []
        self._label_entry_vars: list[list[Optional[tk.StringVar]]] = []

        self._setup_vars()
        self._create_widgets()

    # ---------------------------------------------------------------- #
    #  변수 초기화
    # ---------------------------------------------------------------- #

    def _setup_vars(self):
        sv = lambda v: tk.StringVar(value=v)
        bv = lambda v: tk.BooleanVar(value=v)
        iv = lambda v: tk.IntVar(value=v)

        self.mode_var          = sv("folder")
        self.parent_folder     = sv("")
        self.fill_mode_var     = sv("grid")   # grid | data
        self.axis_var          = sv(AXIS_ROW)
        self.grid_rows_var     = iv(3)
        self.grid_cols_var     = iv(3)
        self.sort_key_var      = sv("name")   # name | date | size
        self.sort_dir_var      = sv("asc")    # asc  | desc
        self.cell_mode_var     = sv(CELL_TIGHT)
        self.resize_base_var   = sv(RESIZE_LARGEST)
        self.resize_method_var = sv(METHOD_SCALE)
        self.resize_w_var      = iv(512)
        self.resize_h_var      = iv(512)
        self.title_en_var      = bv(False)
        self.title_text_var    = sv("")
        self.title_fs_auto     = bv(True)
        self.title_fs_var      = iv(36)
        self.lbl_fs_mode_var   = sv(FONT_AUTO)
        self.lbl_fs_var        = iv(18)
        self.lbl_align_h_var   = sv("center")
        self.lbl_align_v_var   = sv("center")
        self.pad_en_var        = bv(False)
        self.pad_px_var        = iv(4)
        self.ds_en_var         = bv(False)
        self.ds_pct_var        = iv(100)
        self.save_fmt_var      = sv("png")
        self.save_lossless     = bv(True)
        self.save_quality      = iv(95)
        self.save_path_var     = sv("")

    # ---------------------------------------------------------------- #
    #  UI 빌드
    # ---------------------------------------------------------------- #

    def _create_widgets(self):
        paned = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 좌측: 설정 패널 (ScrollableFrame)
        left_outer = ttk.Frame(paned)
        paned.add(left_outer, weight=1)
        left_scroll = ScrollableFrame(left_outer)
        left_scroll.pack(fill=tk.BOTH, expand=True)
        left = left_scroll.scrollable_frame

        # 우측: 격자 패널
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        self._build_left(left)
        self._build_right(right_frame)

    # ── 좌측 설정 패널 ───────────────────────────────────────────────

    def _build_left(self, parent):
        self._build_folder_group(parent)
        self._build_fill_mode_group(parent)
        self._build_sort_group(parent)
        self._build_axis_group(parent)
        self._build_cell_group(parent)
        self._build_resize_group(parent)
        self._build_title_group(parent)
        self._build_label_group(parent)
        self._build_padding_group(parent)
        self._build_save_group(parent)
        self._build_action_group(parent)

    def _build_folder_group(self, parent):
        grp = ttk.LabelFrame(parent, text="폴더 입력 방식", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        mode_f = ttk.Frame(grp)
        mode_f.pack(anchor=tk.W)
        ttk.Radiobutton(mode_f, text="셀프 선택", variable=self.mode_var,
                        value="manual", command=self._on_mode_change).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_f, text="폴더 자동 감지", variable=self.mode_var,
                        value="folder", command=self._on_mode_change).pack(side=tk.LEFT, padx=(8, 0))

        # 셀프선택 영역
        self._manual_frame = ttk.LabelFrame(grp, text="폴더 목록", padding="5")
        self._manual_frame.pack(fill=tk.X, pady=(5, 0))
        self._folder_list_frame = ttk.Frame(self._manual_frame)
        self._folder_list_frame.pack(fill=tk.X)
        btn_f = ttk.Frame(self._manual_frame)
        btn_f.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(btn_f, text="+ 폴더 추가", command=self._add_folder_row).pack(side=tk.LEFT)
        ttk.Button(btn_f, text="− 마지막 제거", command=self._remove_last_folder).pack(side=tk.LEFT, padx=(5, 0))

        # 자동감지 영역
        self._auto_frame = ttk.LabelFrame(grp, text="상위 폴더", padding="5")
        self._auto_frame.pack(fill=tk.X, pady=(5, 0))
        af = ttk.Frame(self._auto_frame)
        af.pack(fill=tk.X)
        ttk.Entry(af, textvariable=self.parent_folder).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(af, text="선택", width=5, command=self._browse_parent_folder).pack(side=tk.LEFT)

        self._on_mode_change()

    def _build_fill_mode_group(self, parent):
        grp = ttk.LabelFrame(parent, text="빈 칸 채우기 방식", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        ttk.Radiobutton(
            grp, text="격자 우선  (격자 크기 고정, 부족한 칸은 NO IMAGE)",
            variable=self.fill_mode_var, value="grid",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            grp, text="데이터 우선  (폴더·이미지 수 기준으로 표 크기 결정)",
            variable=self.fill_mode_var, value="data",
        ).pack(anchor=tk.W, pady=(4, 0))

    def _build_sort_group(self, parent):
        grp = ttk.LabelFrame(parent, text="이미지 정렬 순서", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        key_f = ttk.Frame(grp)
        key_f.pack(anchor=tk.W)
        ttk.Label(key_f, text="기준:").pack(side=tk.LEFT, padx=(0, 5))
        for lbl, val in [("이름", "name"), ("생성날짜", "date"), ("크기", "size")]:
            ttk.Radiobutton(key_f, text=lbl, variable=self.sort_key_var,
                            value=val).pack(side=tk.LEFT, padx=(0, 5))

        dir_f = ttk.Frame(grp)
        dir_f.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(dir_f, text="방향:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(dir_f, text="오름차순", variable=self.sort_dir_var, value="asc" ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(dir_f, text="내림차순", variable=self.sort_dir_var, value="desc").pack(side=tk.LEFT)

    def _build_axis_group(self, parent):
        grp = ttk.LabelFrame(parent, text="이미지 배치 방향  (행=가로로 | 열=세로로)", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))
        row = ttk.Frame(grp)
        row.pack(anchor=tk.W)
        ttk.Radiobutton(row, text="행", variable=self.axis_var, value=AXIS_ROW).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(row, text="열", variable=self.axis_var, value=AXIS_COL).pack(side=tk.LEFT)
        ttk.Button(row, text="행↔열 스왑", command=self._swap_axis).pack(side=tk.LEFT, padx=(12, 0))

    def _build_cell_group(self, parent):
        grp = ttk.LabelFrame(parent, text="이미지 셀 크기", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))
        ttk.Radiobutton(grp, text="바짝붙이기 (이미지 크기 그대로)",
                        variable=self.cell_mode_var, value=CELL_TIGHT).pack(anchor=tk.W)
        ttk.Radiobutton(grp, text="최장변 기준 정사각형 공간 확보",
                        variable=self.cell_mode_var, value=CELL_LONGEST_EDGE).pack(anchor=tk.W, pady=(3, 0))

    def _build_resize_group(self, parent):
        grp = ttk.LabelFrame(parent, text="혼합 해상도 처리", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        base_f = ttk.Frame(grp)
        base_f.pack(anchor=tk.W)
        for lbl, val in [("최대 기준", RESIZE_LARGEST), ("최소 기준", RESIZE_SMALLEST), ("직접 지정", RESIZE_CUSTOM)]:
            ttk.Radiobutton(base_f, text=lbl, variable=self.resize_base_var,
                            value=val, command=self._toggle_custom_resize).pack(side=tk.LEFT, padx=(0, 5))

        cust_f = ttk.Frame(grp)
        cust_f.pack(anchor=tk.W, pady=(3, 0))
        ttk.Label(cust_f, text="W:").pack(side=tk.LEFT)
        self._resize_w_entry = ttk.Entry(cust_f, textvariable=self.resize_w_var, width=6)
        self._resize_w_entry.pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(cust_f, text="H:").pack(side=tk.LEFT)
        self._resize_h_entry = ttk.Entry(cust_f, textvariable=self.resize_h_var, width=6)
        self._resize_h_entry.pack(side=tk.LEFT, padx=(2, 0))

        meth_f = ttk.Frame(grp)
        meth_f.pack(anchor=tk.W, pady=(3, 0))
        ttk.Label(meth_f, text="처리 방식:").pack(side=tk.LEFT, padx=(0, 5))
        for lbl, val in [("스케일 (종횡비 유지+레터박스)", METHOD_SCALE), ("크롭 (중앙 기준)", METHOD_CROP)]:
            ttk.Radiobutton(meth_f, text=lbl, variable=self.resize_method_var, value=val).pack(side=tk.LEFT, padx=(0, 8))

        self._toggle_custom_resize()

    def _build_title_group(self, parent):
        grp = ttk.LabelFrame(parent, text="제목", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        row1 = ttk.Frame(grp)
        row1.pack(fill=tk.X)
        ttk.Checkbutton(row1, text="제목 표시", variable=self.title_en_var,
                        command=self._toggle_title).pack(side=tk.LEFT)
        self._title_entry = ttk.Entry(row1, textvariable=self.title_text_var)
        self._title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        row2 = ttk.Frame(grp)
        row2.pack(anchor=tk.W, pady=(3, 0))
        ttk.Checkbutton(row2, text="글자크기 자동", variable=self.title_fs_auto,
                        command=self._toggle_title).pack(side=tk.LEFT)
        ttk.Label(row2, text="크기:").pack(side=tk.LEFT, padx=(8, 2))
        self._title_fs_entry = ttk.Entry(row2, textvariable=self.title_fs_var, width=5)
        self._title_fs_entry.pack(side=tk.LEFT)

        self._toggle_title()

    def _build_label_group(self, parent):
        grp = ttk.LabelFrame(parent, text="라벨 글자", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        row1 = ttk.Frame(grp)
        row1.pack(anchor=tk.W)
        for lbl, val in [("자동", FONT_AUTO), ("핏", FONT_FIT), ("직접 설정", FONT_MANUAL)]:
            ttk.Radiobutton(row1, text=lbl, variable=self.lbl_fs_mode_var,
                            value=val, command=self._toggle_lbl_fs).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(row1, text="크기:").pack(side=tk.LEFT, padx=(5, 2))
        self._lbl_fs_entry = ttk.Entry(row1, textvariable=self.lbl_fs_var, width=5)
        self._lbl_fs_entry.pack(side=tk.LEFT)

        row2 = ttk.Frame(grp)
        row2.pack(anchor=tk.W, pady=(5, 0))
        ttk.Label(row2, text="가로 정렬:").pack(side=tk.LEFT, padx=(0, 3))
        for lbl, val in [("좌", "left"), ("중앙", "center"), ("우", "right")]:
            ttk.Radiobutton(row2, text=lbl, variable=self.lbl_align_h_var, value=val).pack(side=tk.LEFT, padx=(0, 3))

        row3 = ttk.Frame(grp)
        row3.pack(anchor=tk.W, pady=(3, 0))
        ttk.Label(row3, text="세로 정렬:").pack(side=tk.LEFT, padx=(0, 3))
        for lbl, val in [("상", "top"), ("중앙", "center"), ("하", "bottom")]:
            ttk.Radiobutton(row3, text=lbl, variable=self.lbl_align_v_var, value=val).pack(side=tk.LEFT, padx=(0, 3))

        self._toggle_lbl_fs()

    def _build_padding_group(self, parent):
        grp = ttk.LabelFrame(parent, text="패딩 / 스케일조절", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        pad_f = ttk.Frame(grp)
        pad_f.pack(anchor=tk.W)
        ttk.Checkbutton(pad_f, text="패딩", variable=self.pad_en_var,
                        command=self._toggle_pad).pack(side=tk.LEFT)
        self._pad_entry = ttk.Entry(pad_f, textvariable=self.pad_px_var, width=5)
        self._pad_entry.pack(side=tk.LEFT, padx=(5, 2))
        ttk.Label(pad_f, text="px").pack(side=tk.LEFT)

        ttk.Label(pad_f, text="   스케일조절").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(pad_f, variable=self.ds_en_var,
                        command=self._toggle_ds).pack(side=tk.LEFT)
        self._ds_entry = ttk.Entry(pad_f, textvariable=self.ds_pct_var, width=5)
        self._ds_entry.pack(side=tk.LEFT, padx=(2, 2))
        ttk.Label(pad_f, text="%").pack(side=tk.LEFT)

        self._toggle_pad()
        self._toggle_ds()

    def _build_save_group(self, parent):
        grp = ttk.LabelFrame(parent, text="저장 옵션", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        fmt_f = ttk.Frame(grp)
        fmt_f.pack(anchor=tk.W)
        ttk.Label(fmt_f, text="포맷:").pack(side=tk.LEFT, padx=(0, 5))
        for lbl, val in [("PNG", "png"), ("WEBP", "webp"), ("JPG", "jpg")]:
            ttk.Radiobutton(fmt_f, text=lbl, variable=self.save_fmt_var,
                            value=val, command=self._toggle_save_opts).pack(side=tk.LEFT, padx=(0, 5))

        opt_f = ttk.Frame(grp)
        opt_f.pack(anchor=tk.W, pady=(5, 0))
        self._lossless_cb = ttk.Checkbutton(opt_f, text="무손실", variable=self.save_lossless,
                                            command=self._toggle_save_opts)
        self._lossless_cb.pack(side=tk.LEFT)
        ttk.Label(opt_f, text="  품질:").pack(side=tk.LEFT)
        self._quality_entry = ttk.Entry(opt_f, textvariable=self.save_quality, width=5)
        self._quality_entry.pack(side=tk.LEFT, padx=(3, 2))
        ttk.Label(opt_f, text="(0~100)").pack(side=tk.LEFT)

        path_f = ttk.Frame(grp)
        path_f.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(path_f, text="저장 경로:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Entry(path_f, textvariable=self.save_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(path_f, text="선택", width=5, command=self._browse_save_path).pack(side=tk.LEFT)

        self._toggle_save_opts()

    def _build_action_group(self, parent):
        grp = ttk.Frame(parent)
        grp.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(grp, text="미리보기",   command=self._run_preview).pack(side=tk.LEFT)
        ttk.Button(grp, text="완성본 저장", command=self._run_save).pack(side=tk.LEFT, padx=(5, 0))

    # ── 우측 격자 패널 ───────────────────────────────────────────────

    def _build_right(self, parent):
        grp = ttk.LabelFrame(parent, text="라벨 입력 격자", padding="8")
        grp.pack(fill=tk.BOTH, expand=True)
        grp.rowconfigure(1, weight=1)
        grp.columnconfigure(0, weight=1)

        ctrl_f = ttk.Frame(grp)
        ctrl_f.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Label(ctrl_f, text="행 수:").pack(side=tk.LEFT)
        ttk.Entry(ctrl_f, textvariable=self.grid_rows_var, width=4).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(ctrl_f, text="열 수:").pack(side=tk.LEFT)
        ttk.Entry(ctrl_f, textvariable=self.grid_cols_var, width=4).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(ctrl_f, text="격자 생성", command=self._rebuild_grid).pack(side=tk.LEFT)
        ttk.Button(ctrl_f, text="자동 격자 생성", command=self._auto_grid).pack(side=tk.LEFT, padx=(5, 0))

        grid_outer = ttk.Frame(grp)
        grid_outer.grid(row=1, column=0, sticky="nsew")
        grid_outer.rowconfigure(0, weight=1)
        grid_outer.columnconfigure(0, weight=1)

        self._grid_canvas = tk.Canvas(grid_outer, highlightthickness=0, bg="#f0f0f0")
        sx = ttk.Scrollbar(grid_outer, orient=tk.HORIZONTAL, command=self._grid_canvas.xview)
        sy = ttk.Scrollbar(grid_outer, orient=tk.VERTICAL,   command=self._grid_canvas.yview)
        self._grid_canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        sx.grid(row=1, column=0, sticky="ew")
        sy.grid(row=0, column=1, sticky="ns")
        self._grid_canvas.grid(row=0, column=0, sticky="nsew")

        self._grid_inner = ttk.Frame(self._grid_canvas)
        self._grid_canvas.create_window((0, 0), window=self._grid_inner, anchor=tk.NW)
        self._grid_scrollregion_job  = None
        self._grid_last_bbox         = None
        self._grid_inner.bind("<Configure>", self._on_grid_inner_configure)

        self._rebuild_grid()

    def _on_grid_inner_configure(self, event=None):
        """격자 내부 프레임 크기 변화 — debounce 후 실제 bbox 변화 시에만 scrollregion 갱신"""
        if self._grid_scrollregion_job:
            self._grid_canvas.after_cancel(self._grid_scrollregion_job)
        self._grid_scrollregion_job = self._grid_canvas.after(
            30, self._apply_grid_scrollregion
        )

    def _apply_grid_scrollregion(self):
        self._grid_scrollregion_job = None
        bbox = self._grid_canvas.bbox("all")
        if bbox is None or bbox == self._grid_last_bbox:
            return
        self._grid_last_bbox = bbox
        self._grid_canvas.configure(scrollregion=bbox)

    def _rebuild_grid(self):
        for w in self._grid_inner.winfo_children():
            w.destroy()
        self._label_entry_vars.clear()

        try:
            n_rows = max(1, min(GRID_MAX, self.grid_rows_var.get()))
            n_cols = max(1, min(GRID_MAX, self.grid_cols_var.get()))
        except Exception:
            return

        for r in range(n_rows + 1):
            row_vars: list[Optional[tk.StringVar]] = []
            for c in range(n_cols + 1):
                if r == 0 and c == 0:
                    tk.Label(self._grid_inner, width=8, bg="#cccccc",
                             relief="ridge").grid(row=r, column=c, padx=1, pady=1, ipadx=4, ipady=4)
                    row_vars.append(None)
                elif r == 0:
                    var = tk.StringVar(value=f"열{c}")
                    tk.Entry(self._grid_inner, textvariable=var, width=8,
                             bg="#ddeeff", relief="ridge",
                             justify="center").grid(row=r, column=c, padx=1, pady=1, ipadx=4, ipady=4)
                    row_vars.append(var)
                elif c == 0:
                    var = tk.StringVar(value=f"행{r}")
                    tk.Entry(self._grid_inner, textvariable=var, width=8,
                             bg="#ddeeff", relief="ridge",
                             justify="center").grid(row=r, column=c, padx=1, pady=1, ipadx=4, ipady=4)
                    row_vars.append(var)
                else:
                    tk.Label(self._grid_inner, text="[이미지]", width=8,
                             bg="#f8f8f8", relief="ridge",
                             fg="#aaaaaa", justify="center").grid(row=r, column=c, padx=1, pady=1, ipadx=4, ipady=4)
                    row_vars.append(None)
            self._label_entry_vars.append(row_vars)

    # ---------------------------------------------------------------- #
    #  토글 핸들러
    # ---------------------------------------------------------------- #

    def _auto_grid(self):
        """
        현재 설정된 폴더(셀프/자동)와 각 폴더 안의 이미지 수를 바탕으로
        행×열을 자동 계산하여 격자를 생성합니다.

        - folder_axis == AXIS_ROW: 폴더 수 → 행, max 이미지 수 → 열
        - folder_axis == AXIS_COL: 폴더 수 → 열, max 이미지 수 → 행
        결과는 GRID_MAX(12)로 클램프됩니다.
        """
        sort_order = self.sort_key_var.get() + "_" + self.sort_dir_var.get()

        # 폴더 목록 수집
        if self.mode_var.get() == "manual":
            folder_paths = [pv.get().strip() for pv, _ in self._folder_entries if pv.get().strip()]
        else:
            parent_p = self.parent_folder.get().strip()
            if not parent_p or not os.path.isdir(parent_p):
                messagebox.showerror("오류", "유효한 상위 폴더를 지정해주세요.")
                return
            folder_paths = sorted(
                [str(d) for d in Path(parent_p).iterdir() if d.is_dir()],
                key=lambda d: d.lower(),
            )

        if not folder_paths:
            messagebox.showerror("오류", "폴더가 지정되지 않았습니다.")
            return

        n_folders = len(folder_paths)
        max_images = max(
            (len(collect_images(fp, sort_order)) for fp in folder_paths),
            default=0,
        )
        if max_images == 0:
            messagebox.showwarning("경고", "폴더 안에 이미지가 없습니다.\n행/열을 폴더 수 기준으로만 설정합니다.")
            max_images = 1

        n_folders = max(1, min(GRID_MAX, n_folders))
        max_images = max(1, min(GRID_MAX, max_images))

        if self.axis_var.get() == AXIS_ROW:
            self.grid_rows_var.set(n_folders)
            self.grid_cols_var.set(max_images)
        else:
            self.grid_rows_var.set(max_images)
            self.grid_cols_var.set(n_folders)

        self._rebuild_grid()

    def _swap_axis(self):
        """격자의 첫 행/첫 열 라벨을 전치. 축 방향 라디오버튼은 건드리지 않음."""
        if not self._label_entry_vars:
            return

        col_lbls = [self._label_entry_vars[0][c].get()
                    if self._label_entry_vars[0][c] else ""
                    for c in range(1, len(self._label_entry_vars[0]))]
        row_lbls = [self._label_entry_vars[r][0].get()
                    if self._label_entry_vars[r][0] else ""
                    for r in range(1, len(self._label_entry_vars))]

        old_rows = self.grid_rows_var.get()
        old_cols = self.grid_cols_var.get()
        self.grid_rows_var.set(old_cols)
        self.grid_cols_var.set(old_rows)
        self._rebuild_grid()

        # 이전 행 라벨 → 새 열 라벨, 이전 열 라벨 → 새 행 라벨
        first_row = self._label_entry_vars[0]
        for c in range(1, len(first_row)):
            var = first_row[c]
            if var:
                var.set(row_lbls[c - 1] if (c - 1) < len(row_lbls) else "")

        for r in range(1, len(self._label_entry_vars)):
            var = self._label_entry_vars[r][0]
            if var:
                var.set(col_lbls[r - 1] if (r - 1) < len(col_lbls) else "")

    def _on_mode_change(self):
        if self.mode_var.get() == "manual":
            self._manual_frame.pack(fill=tk.X, pady=(5, 0))
            self._auto_frame.pack_forget()
        else:
            self._auto_frame.pack(fill=tk.X, pady=(5, 0))
            self._manual_frame.pack_forget()

    def _toggle_custom_resize(self):
        state = tk.NORMAL if self.resize_base_var.get() == RESIZE_CUSTOM else tk.DISABLED
        self._resize_w_entry.config(state=state)
        self._resize_h_entry.config(state=state)

    def _toggle_title(self):
        en   = self.title_en_var.get()
        auto = self.title_fs_auto.get()
        self._title_entry.config(state=tk.NORMAL if en else tk.DISABLED)
        self._title_fs_entry.config(state=tk.DISABLED if (not en or auto) else tk.NORMAL)

    def _toggle_lbl_fs(self):
        state = tk.NORMAL if self.lbl_fs_mode_var.get() == FONT_MANUAL else tk.DISABLED
        self._lbl_fs_entry.config(state=state)

    def _toggle_pad(self):
        self._pad_entry.config(state=tk.NORMAL if self.pad_en_var.get() else tk.DISABLED)

    def _toggle_ds(self):
        self._ds_entry.config(state=tk.NORMAL if self.ds_en_var.get() else tk.DISABLED)

    def _toggle_save_opts(self):
        fmt = self.save_fmt_var.get()
        if fmt == "png":
            self._lossless_cb.config(state=tk.DISABLED)
            self._quality_entry.config(state=tk.DISABLED)
        elif fmt == "webp":
            self._lossless_cb.config(state=tk.NORMAL)
            self._quality_entry.config(
                state=tk.DISABLED if self.save_lossless.get() else tk.NORMAL)
        else:
            self._lossless_cb.config(state=tk.DISABLED)
            self._quality_entry.config(state=tk.NORMAL)

    # ---------------------------------------------------------------- #
    #  폴더 관리
    # ---------------------------------------------------------------- #

    def _add_folder_row(self, path: str = "", label: str = ""):
        idx   = len(self._folder_entries)
        frame = ttk.Frame(self._folder_list_frame)
        frame.pack(fill=tk.X, pady=1)

        path_var  = tk.StringVar(value=path)
        label_var = tk.StringVar(value=label)

        ttk.Label(frame, text=f"{idx+1}.").pack(side=tk.LEFT)
        ttk.Entry(frame, textvariable=path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 2))
        ttk.Button(frame, text="선택", width=5,
                   command=lambda v=path_var: self._browse_folder_var(v)).pack(side=tk.LEFT)
        ttk.Label(frame, text="라벨:").pack(side=tk.LEFT, padx=(5, 2))
        ttk.Entry(frame, textvariable=label_var, width=10).pack(side=tk.LEFT)

        self._folder_entries.append((path_var, label_var))

    def _remove_last_folder(self):
        if not self._folder_entries:
            return
        self._folder_entries.pop()
        frames = self._folder_list_frame.winfo_children()
        if frames:
            frames[-1].destroy()

    def _browse_folder_var(self, var: tk.StringVar):
        d = filedialog.askdirectory(title="폴더 선택")
        if d:
            var.set(d)

    def _browse_parent_folder(self):
        d = filedialog.askdirectory(title="상위 폴더 선택")
        if d:
            self.parent_folder.set(d)

    def _browse_save_path(self):
        fmt = self.save_fmt_var.get()
        ext = {"png": ".png", "webp": ".webp", "jpg": ".jpg"}.get(fmt, ".png")
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[(fmt.upper(), f"*{ext}"), ("모든 파일", "*.*")],
            title="저장 경로 지정",
        )
        if path:
            self.save_path_var.set(path)

    # ---------------------------------------------------------------- #
    #  설정 수집
    # ---------------------------------------------------------------- #

    def _collect_config(self) -> Optional[XYPlotConfig]:
        try:
            if self.mode_var.get() == "manual":
                entries = [
                    FolderEntry(folder_path=pv.get().strip(), label=lv.get().strip())
                    for pv, lv in self._folder_entries
                    if pv.get().strip()
                ]
            else:
                parent_p = self.parent_folder.get().strip()
                if not parent_p or not os.path.isdir(parent_p):
                    messagebox.showerror("오류", "유효한 상위 폴더를 지정해주세요.")
                    return None
                subs = sorted(
                    [d for d in Path(parent_p).iterdir() if d.is_dir()],
                    key=lambda d: d.name.lower(),
                )
                entries = [FolderEntry(folder_path=str(d), label=d.name) for d in subs]

            if not entries:
                messagebox.showerror("오류", "폴더가 지정되지 않았습니다.")
                return None

            # 격자 라벨 수집
            col_labels: list[str] = []
            row_labels_extra: list[str] = []
            grid_cols = self.grid_cols_var.get()
            grid_rows = self.grid_rows_var.get()
            if self._label_entry_vars:
                first_row = self._label_entry_vars[0]
                for c, var in enumerate(first_row):
                    if c == 0:
                        continue
                    col_labels.append(var.get() if var else "")
                for r, row in enumerate(self._label_entry_vars[1:], 1):
                    var = row[0] if row else None
                    rl  = var.get().strip() if var else ""
                    row_labels_extra.append(rl)
                    # 폴더 엔트리 라벨도 격자값으로 오버라이드
                    if rl and (r - 1) < len(entries):
                        entries[r - 1].label = rl

            title_fs = None if self.title_fs_auto.get() else self.title_fs_var.get()
            lbl_fs   = self.lbl_fs_var.get() if self.lbl_fs_mode_var.get() == FONT_MANUAL else None
            ds_ratio = self.ds_pct_var.get() / 100.0 if self.ds_en_var.get() else 1.0

            return XYPlotConfig(
                entries=entries,
                col_labels=col_labels,
                row_labels_extra=row_labels_extra,
                grid_cols=grid_cols,
                grid_rows=grid_rows,
                fill_mode=self.fill_mode_var.get(),
                folder_axis=self.axis_var.get(),
                sort_order=self.sort_key_var.get() + "_" + self.sort_dir_var.get(),
                cell_mode=self.cell_mode_var.get(),
                resize_base=self.resize_base_var.get(),
                resize_custom_wh=(self.resize_w_var.get(), self.resize_h_var.get()),
                resize_method=self.resize_method_var.get(),
                title_enabled=self.title_en_var.get(),
                title_text=self.title_text_var.get(),
                title_fontsize=title_fs,
                label_fontsize_mode=self.lbl_fs_mode_var.get(),
                label_fontsize=lbl_fs,
                label_align_h=self.lbl_align_h_var.get(),
                label_align_v=self.lbl_align_v_var.get(),
                padding_enabled=self.pad_en_var.get(),
                padding_px=self.pad_px_var.get(),
                downscale_enabled=self.ds_en_var.get(),
                downscale_ratio=ds_ratio,
                save_path=self.save_path_var.get(),
                save_format=self.save_fmt_var.get(),
                save_lossless=self.save_lossless.get(),
                save_quality=self.save_quality.get(),
            )
        except Exception as e:
            messagebox.showerror("설정 오류", str(e))
            return None

    # ---------------------------------------------------------------- #
    #  실행
    # ---------------------------------------------------------------- #

    def _run_preview(self):
        cfg = self._collect_config()
        if cfg is None:
            return
        self._log("미리보기 렌더링 중...")

        def _work():
            result = build_preview(cfg)
            self.parent.after(0, lambda: _PreviewWindow(self.parent, result, cfg, self._log))

        threading.Thread(target=_work, daemon=True).start()

    def _run_save(self):
        cfg = self._collect_config()
        if cfg is None:
            return
        if not cfg.save_path:
            messagebox.showerror("오류", "저장 경로를 지정해주세요.")
            return

        # 확장자 보정 후 실제 경로 확인
        fmt = cfg.save_format.lower()
        ext = {"jpg": ".jpg", "jpeg": ".jpg", "webp": ".webp"}.get(fmt, ".png")
        final_path = cfg.save_path if cfg.save_path.lower().endswith(ext) else cfg.save_path + ext
        if os.path.exists(final_path):
            if not messagebox.askyesno(
                "덮어쓰기 확인",
                f"이미 파일이 존재합니다.\n{final_path}\n\n덮어쓰시겠습니까?",
            ):
                return

        self._log("완성본 렌더링 중...")

        def _work():
            result = build_plot(cfg)
            if result.success:
                ok, msg = save_image(result.image, cfg)
                self.parent.after(0, lambda: self._log(msg))
                if ok:
                    self.parent.after(0, lambda: messagebox.showinfo("완료", msg))
                else:
                    self.parent.after(0, lambda: messagebox.showerror("저장 실패", msg))
            else:
                self.parent.after(0, lambda: messagebox.showerror("렌더링 실패", result.error_msg))

        threading.Thread(target=_work, daemon=True).start()

    # ---------------------------------------------------------------- #
    #  로거
    # ---------------------------------------------------------------- #

    def _log(self, msg: str):
        if self.logger:
            self.logger.info(msg)
        else:
            print(f"[XYPlot] {msg}")

    # ---------------------------------------------------------------- #
    #  설정 저장/불러오기
    # ---------------------------------------------------------------- #

    def get_settings(self) -> dict:
        folders = [{"path": pv.get(), "label": lv.get()} for pv, lv in self._folder_entries]
        grid_labels = [
            [v.get() if v else "" for v in row]
            for row in self._label_entry_vars
        ]
        return {
            "xy_mode":           self.mode_var.get(),
            "xy_parent_folder":  self.parent_folder.get(),
            "xy_folders":        folders,
            "xy_grid_rows":      self.grid_rows_var.get(),
            "xy_grid_cols":      self.grid_cols_var.get(),
            "xy_grid_labels":    grid_labels,
            "xy_fill_mode":      self.fill_mode_var.get(),
            "xy_axis":           self.axis_var.get(),
            "xy_sort_key":       self.sort_key_var.get(),
            "xy_sort_dir":       self.sort_dir_var.get(),
            "xy_cell_mode":      self.cell_mode_var.get(),
            "xy_resize_base":    self.resize_base_var.get(),
            "xy_resize_method":  self.resize_method_var.get(),
            "xy_resize_w":       self.resize_w_var.get(),
            "xy_resize_h":       self.resize_h_var.get(),
            "xy_title_en":       self.title_en_var.get(),
            "xy_title_text":     self.title_text_var.get(),
            "xy_title_fs_auto":  self.title_fs_auto.get(),
            "xy_title_fs":       self.title_fs_var.get(),
            "xy_lbl_fs_mode":    self.lbl_fs_mode_var.get(),
            "xy_lbl_fs":         self.lbl_fs_var.get(),
            "xy_lbl_align_h":    self.lbl_align_h_var.get(),
            "xy_lbl_align_v":    self.lbl_align_v_var.get(),
            "xy_pad_en":         self.pad_en_var.get(),
            "xy_pad_px":         self.pad_px_var.get(),
            "xy_ds_en":          self.ds_en_var.get(),
            "xy_ds_pct":         self.ds_pct_var.get(),
            "xy_save_fmt":       self.save_fmt_var.get(),
            "xy_save_lossless":  self.save_lossless.get(),
            "xy_save_quality":   self.save_quality.get(),
            "xy_save_path":      self.save_path_var.get(),
        }

    def load_settings(self, s: dict):
        def _s(var, key, default=None):
            if key in s:
                try:
                    var.set(s[key])
                except Exception:
                    if default is not None:
                        var.set(default)

        _s(self.mode_var,          "xy_mode",          "folder")
        _s(self.parent_folder,     "xy_parent_folder", "")
        _s(self.fill_mode_var,     "xy_fill_mode",     "grid")
        _s(self.axis_var,          "xy_axis",          AXIS_ROW)
        _s(self.sort_key_var,      "xy_sort_key",      "name")
        _s(self.sort_dir_var,      "xy_sort_dir",      "asc")
        _s(self.cell_mode_var,     "xy_cell_mode",     CELL_TIGHT)
        _s(self.resize_base_var,   "xy_resize_base",   RESIZE_LARGEST)
        _s(self.resize_method_var, "xy_resize_method", METHOD_SCALE)
        _s(self.resize_w_var,      "xy_resize_w",      512)
        _s(self.resize_h_var,      "xy_resize_h",      512)
        _s(self.title_en_var,      "xy_title_en",      False)
        _s(self.title_text_var,    "xy_title_text",    "")
        _s(self.title_fs_auto,     "xy_title_fs_auto", True)
        _s(self.title_fs_var,      "xy_title_fs",      36)
        _s(self.lbl_fs_mode_var,   "xy_lbl_fs_mode",   FONT_AUTO)
        _s(self.lbl_fs_var,        "xy_lbl_fs",        18)
        _s(self.lbl_align_h_var,   "xy_lbl_align_h",   "center")
        _s(self.lbl_align_v_var,   "xy_lbl_align_v",   "center")
        _s(self.pad_en_var,        "xy_pad_en",        False)
        _s(self.pad_px_var,        "xy_pad_px",        4)
        _s(self.ds_en_var,         "xy_ds_en",         False)
        _s(self.ds_pct_var,        "xy_ds_pct",        100)
        _s(self.save_fmt_var,      "xy_save_fmt",      "png")
        _s(self.save_lossless,     "xy_save_lossless", True)
        _s(self.save_quality,      "xy_save_quality",  95)
        _s(self.save_path_var,     "xy_save_path",     "")

        for _ in range(len(self._folder_entries)):
            self._remove_last_folder()
        for entry in s.get("xy_folders", []):
            self._add_folder_row(entry.get("path", ""), entry.get("label", ""))

        _s(self.grid_rows_var, "xy_grid_rows", 3)
        _s(self.grid_cols_var, "xy_grid_cols", 3)
        self._rebuild_grid()
        for r, row in enumerate(s.get("xy_grid_labels", [])):
            if r >= len(self._label_entry_vars):
                break
            for c, val in enumerate(row):
                if c >= len(self._label_entry_vars[r]):
                    break
                var = self._label_entry_vars[r][c]
                if var and val:
                    var.set(val)

        self._on_mode_change()
        self._toggle_custom_resize()
        self._toggle_title()
        self._toggle_lbl_fs()
        self._toggle_pad()
        self._toggle_ds()
        self._toggle_save_opts()


# ------------------------------------------------------------------ #
#  미리보기 창
# ------------------------------------------------------------------ #

class _PreviewWindow:
    """미리보기 전용 Toplevel 창."""

    MIN_ZOOM  = 0.05
    MAX_ZOOM  = 20.0
    ZOOM_STEP = 1.15

    def __init__(self, parent, result: BuildResult, cfg: XYPlotConfig, log_fn):
        if not result.success:
            messagebox.showerror("미리보기 실패", result.error_msg)
            return

        self._result    = result
        self._cfg       = cfg
        self._log       = log_fn
        self._zoom      = 1.0
        self._pan_x     = 0.0
        self._pan_y     = 0.0
        self._drag_start = None
        self._photo_ref  = None
        self._resize_job  = None
        self._last_wh     = (0, 0)  # 창 크기 변화 감지용

        win = tk.Toplevel(parent)
        win.title("미리보기")
        win.geometry("900x700")
        win.minsize(400, 300)
        self._win = win

        self._build_toolbar()
        self._build_canvas()
        win.after(50, self._fit_to_window)
        win.bind("<Configure>", self._on_win_resize)
        win.focus_set()
        log_fn("미리보기 완료.")

    def _build_toolbar(self):
        bar = ttk.Frame(self._win)
        bar.pack(fill=tk.X, padx=5, pady=3)

        ttk.Button(bar, text="확대 (+)", width=9,
                   command=lambda: self._zoom_by(self.ZOOM_STEP)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="축소 (−)", width=9,
                   command=lambda: self._zoom_by(1 / self.ZOOM_STEP)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="창 크기에 맞춤",
                   command=self._fit_to_window).pack(side=tk.LEFT, padx=2)

        self._zoom_var = tk.StringVar(value="100%")
        ttk.Label(bar, textvariable=self._zoom_var, width=7, anchor=tk.CENTER).pack(side=tk.LEFT, padx=8)

        ttk.Label(bar, text="[휠] 확대/축소   [드래그] 이동   [더블클릭/R] 맞춤 리셋",
                  foreground="#888888").pack(side=tk.LEFT, padx=5)

        ttk.Button(bar, text="완성본 저장",   command=self._save_final  ).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bar, text="미리보기 저장", command=self._save_preview).pack(side=tk.RIGHT, padx=2)

    def _build_canvas(self):
        frame = ttk.Frame(self._win)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(frame, bg="#1e1e1e", cursor="fleur", highlightthickness=0)
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL,   command=self._canvas.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._canvas.bind("<MouseWheel>",      self._on_mousewheel)
        self._canvas.bind("<Button-4>",        self._on_mousewheel)
        self._canvas.bind("<Button-5>",        self._on_mousewheel)
        self._canvas.bind("<ButtonPress-1>",   self._on_drag_start)
        self._canvas.bind("<B1-Motion>",       self._on_drag_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._canvas.bind("<Double-Button-1>", lambda e: self._fit_to_window())
        self._win.bind("<r>",     lambda e: self._fit_to_window())
        self._win.bind("<R>",     lambda e: self._fit_to_window())
        self._win.bind("<plus>",  lambda e: self._zoom_by(self.ZOOM_STEP))
        self._win.bind("<equal>", lambda e: self._zoom_by(self.ZOOM_STEP))
        self._win.bind("<minus>", lambda e: self._zoom_by(1 / self.ZOOM_STEP))

    def _render(self):
        img   = self._result.image
        new_w = max(1, int(img.width  * self._zoom))
        new_h = max(1, int(img.height * self._zoom))
        photo = ImageTk.PhotoImage(img.resize((new_w, new_h), Image.LANCZOS))
        self._canvas.delete("all")
        self._canvas.create_image(int(self._pan_x), int(self._pan_y), anchor=tk.NW, image=photo)
        self._photo_ref = photo
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        self._canvas.configure(scrollregion=(
            min(0, int(self._pan_x)), min(0, int(self._pan_y)),
            max(cw, int(self._pan_x) + new_w), max(ch, int(self._pan_y) + new_h),
        ))
        self._zoom_var.set(f"{int(self._zoom * 100)}%")

    def _fit_to_window(self):
        self._canvas.update_idletasks()
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            self._win.after(80, self._fit_to_window)
            return
        img = self._result.image
        self._zoom  = max(self.MIN_ZOOM, min(self.MAX_ZOOM, min(cw / img.width, ch / img.height)))
        new_w = int(img.width  * self._zoom)
        new_h = int(img.height * self._zoom)
        self._pan_x = max(0, (cw - new_w) // 2)
        self._pan_y = max(0, (ch - new_h) // 2)
        self._render()

    def _zoom_by(self, factor: float, cx=None, cy=None):
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        if cx is None:
            cx = self._canvas.winfo_width()  // 2
        if cy is None:
            cy = self._canvas.winfo_height() // 2
        ratio       = new_zoom / self._zoom
        self._pan_x = cx - ratio * (cx - self._pan_x)
        self._pan_y = cy - ratio * (cy - self._pan_y)
        self._zoom  = new_zoom
        self._render()

    def _on_mousewheel(self, event):
        delta  = 1 if event.num == 4 else (-1 if event.num == 5 else event.delta)
        factor = self.ZOOM_STEP if delta > 0 else (1 / self.ZOOM_STEP)
        self._zoom_by(factor, cx=event.x, cy=event.y)

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag_move(self, event):
        if self._drag_start is None:
            return
        self._pan_x += event.x - self._drag_start[0]
        self._pan_y += event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        self._render()

    def _on_drag_end(self, event):
        self._drag_start = None

    def _on_win_resize(self, event):
        # 창 이동(위치 변화)은 무시하고 크기 변화만 감지
        if event.widget is not self._win:
            return
        wh = (event.width, event.height)
        if wh == self._last_wh:
            return
        self._last_wh = wh
        if self._resize_job:
            self._win.after_cancel(self._resize_job)
        self._resize_job = self._win.after(150, self._fit_to_window)

    def _save_preview(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg"), ("모든 파일", "*.*")],
            title="미리보기 저장",
        )
        if path:
            ok, msg = save_preview_image(self._result.image, path)
            messagebox.showinfo("결과", msg)

    def _save_final(self):
        if not self._cfg.save_path:
            path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG", "*.png"), ("WEBP", "*.webp"), ("JPEG", "*.jpg"), ("모든 파일", "*.*")],
                title="완성본 저장",
            )
            if not path:
                return
            self._cfg.save_path = path

        # full_image가 보존되어 있으면 재렌더링 없이 즉시 저장
        # (미리보기와 동일한 이미지 보장)
        full_img = self._result.full_image or self._result.image

        def _work():
            ok, msg = save_image(full_img, self._cfg)
            if ok:
                self._win.after(0, lambda: messagebox.showinfo("결과", msg))
            else:
                self._win.after(0, lambda: messagebox.showerror("실패", msg))

        threading.Thread(target=_work, daemon=True).start()
