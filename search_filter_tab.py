"""
검색 및 분류 탭 UI  (v1.1.6)
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk
import threading
from pathlib import Path
from typing import List, Optional

from search_filter import (
    FileEntry,
    search_files,
    process_entries,
    get_orphan_warning,
)
from utils import ScrollableFrame


# ---------------------------------------------------------------------------
# 열 정의 (treeview column id, 표시명, 초기 폭)
# ---------------------------------------------------------------------------
_COLUMNS = [
    ("check",      "✓",              30),
    ("name",       "파일명",         220),
    ("ext",        "확장자",          55),
    ("folder",     "폴더",           200),
    ("size_kb",    "용량(KB)",        75),
    ("resolution", "해상도",         100),
    ("tags",       "태그 미리보기",  260),
]


# ===========================================================================
# 메인 탭 GUI 클래스
# ===========================================================================

class SearchFilterGUI:
    def __init__(self, parent, folder_path_var=None, core_var=None):
        self.parent = parent
        self.folder_path_var = folder_path_var if folder_path_var else tk.StringVar()
        self.core_var = core_var

        # ── 독립 경로 ────────────────────────────────────────────────
        self.use_independent_path = tk.BooleanVar(value=False)
        self.independent_folder_path = tk.StringVar()

        # ── 검색 옵션 ────────────────────────────────────────────────
        self.recursive = tk.BooleanVar(value=True)

        # 조건별 모드 변수 (unused / and / or / not)
        self.filename_mode = tk.StringVar(value="unused")
        self.filename_pattern = tk.StringVar()

        self.size_mode = tk.StringVar(value="unused")
        self.size_min = tk.StringVar(value="")
        self.size_max = tk.StringVar(value="")

        self.res_mode = tk.StringVar(value="unused")
        self.res_min_w = tk.StringVar(value="")
        self.res_max_w = tk.StringVar(value="")
        self.res_min_h = tk.StringVar(value="")
        self.res_max_h = tk.StringVar(value="")

        self.tag_mode = tk.StringVar(value="unused")
        self.tag_query = tk.StringVar()

        # ── 처리 대상 ────────────────────────────────────────────────
        self.target_type = tk.StringVar(value="both")

        # ── 내부 상태 ────────────────────────────────────────────────
        self._all_results: List[FileEntry] = []
        self._check_vars: List[tk.BooleanVar] = []
        self._search_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 미리보기 관련
        self._preview_img_ref = None          # PhotoImage GC 방지
        self._preview_orig_img = None         # 원본 PIL Image
        self._current_entry: Optional[FileEntry] = None
        self._resize_job = None               # after() 디바운스 ID

        # 정렬 상태
        self._sort_col = "name"
        self._sort_reverse = False

        self._create_widgets()

    # =========================================================================
    # 공통 유틸
    # =========================================================================

    def _get_effective_folder(self) -> str:
        if self.use_independent_path.get():
            return self.independent_folder_path.get()
        return self.folder_path_var.get()

    def _safe_int(self, var: tk.StringVar) -> Optional[int]:
        v = var.get().strip()
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    def _safe_float(self, var: tk.StringVar) -> Optional[float]:
        v = var.get().strip()
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    def _build_conditions(self) -> list:
        return [
            {'mode': self.filename_mode.get(), 'type': 'filename',
             'pattern': self.filename_pattern.get().strip()},
            {'mode': self.size_mode.get(), 'type': 'size',
             'min_kb': self._safe_float(self.size_min),
             'max_kb': self._safe_float(self.size_max)},
            {'mode': self.res_mode.get(), 'type': 'resolution',
             'min_w': self._safe_int(self.res_min_w),
             'max_w': self._safe_int(self.res_max_w),
             'min_h': self._safe_int(self.res_min_h),
             'max_h': self._safe_int(self.res_max_h)},
            {'mode': self.tag_mode.get(), 'type': 'tag',
             'query': self.tag_query.get().strip()},
        ]

    # =========================================================================
    # 위젯 생성
    # =========================================================================

    def _create_widgets(self):
        paned = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ── 왼쪽: 설정 패널 ─────────────────────────────────────────
        left_outer = ttk.Frame(paned)
        paned.add(left_outer, weight=1)

        left_scroll = ScrollableFrame(left_outer)
        left_scroll.pack(fill=tk.BOTH, expand=True)
        left = left_scroll.scrollable_frame

        self._build_path_group(left)
        self._build_condition_group(left)
        self._build_action_group(left)

        # ── 오른쪽: 결과 패널 ───────────────────────────────────────
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        self._build_result_area(right_frame)

    # ── 경로 설정 ────────────────────────────────────────────────────

    def _build_path_group(self, parent):
        grp = ttk.LabelFrame(parent, text="경로 설정", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        ttk.Checkbutton(
            grp, text="독립적인 경로 사용",
            variable=self.use_independent_path,
            command=self._toggle_path_ui,
        ).pack(anchor=tk.W)

        self._ind_path_frame = ttk.Frame(grp)
        self._ind_path_frame.pack(fill=tk.X, pady=3)

        self._ind_entry = ttk.Entry(
            self._ind_path_frame, textvariable=self.independent_folder_path)
        self._ind_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self._ind_btn = ttk.Button(
            self._ind_path_frame, text="선택", width=5,
            command=self._select_independent_folder)
        self._ind_btn.pack(side=tk.LEFT)

        ttk.Checkbutton(
            grp, text="하위 폴더 포함",
            variable=self.recursive,
        ).pack(anchor=tk.W, pady=(3, 0))

        self._toggle_path_ui()

    def _toggle_path_ui(self):
        state = tk.NORMAL if self.use_independent_path.get() else tk.DISABLED
        self._ind_entry.config(state=state)
        self._ind_btn.config(state=state)

    def _select_independent_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.independent_folder_path.set(folder)

    # ── 검색 조건 ────────────────────────────────────────────────────

    def _build_condition_group(self, parent):
        grp = ttk.LabelFrame(parent, text="검색 조건", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        MODE_VALUES = [
            ("미사용", "unused"),
            ("AND",    "and"),
            ("OR",     "or"),
            ("NOT",    "not"),
        ]

        def mode_radios(frame, var):
            for label, value in MODE_VALUES:
                ttk.Radiobutton(
                    frame, text=label, variable=var, value=value,
                ).pack(side=tk.LEFT, padx=2)

        # 파일명
        fn_grp = ttk.LabelFrame(grp, text="파일명", padding="5")
        fn_grp.pack(fill=tk.X, pady=3)
        fn_top = ttk.Frame(fn_grp)
        fn_top.pack(fill=tk.X)
        ttk.Label(fn_top, text="모드:").pack(side=tk.LEFT)
        mode_radios(fn_top, self.filename_mode)
        fn_bot = ttk.Frame(fn_grp)
        fn_bot.pack(fill=tk.X, pady=(3, 0))
        ttk.Label(fn_bot, text="포함 문자열:").pack(side=tk.LEFT)
        ttk.Entry(fn_bot, textvariable=self.filename_pattern).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 용량
        sz_grp = ttk.LabelFrame(grp, text="용량 (KB)", padding="5")
        sz_grp.pack(fill=tk.X, pady=3)
        sz_top = ttk.Frame(sz_grp)
        sz_top.pack(fill=tk.X)
        ttk.Label(sz_top, text="모드:").pack(side=tk.LEFT)
        mode_radios(sz_top, self.size_mode)
        sz_bot = ttk.Frame(sz_grp)
        sz_bot.pack(fill=tk.X, pady=(3, 0))
        ttk.Label(sz_bot, text="최소:").pack(side=tk.LEFT)
        ttk.Entry(sz_bot, textvariable=self.size_min, width=7).pack(side=tk.LEFT, padx=3)
        ttk.Label(sz_bot, text="최대:").pack(side=tk.LEFT)
        ttk.Entry(sz_bot, textvariable=self.size_max, width=7).pack(side=tk.LEFT, padx=3)
        ttk.Label(sz_bot, text="(빈 칸 = 무제한)").pack(side=tk.LEFT, padx=(5, 0))

        # 해상도
        res_grp = ttk.LabelFrame(grp, text="해상도 (px)", padding="5")
        res_grp.pack(fill=tk.X, pady=3)
        res_top = ttk.Frame(res_grp)
        res_top.pack(fill=tk.X)
        ttk.Label(res_top, text="모드:").pack(side=tk.LEFT)
        mode_radios(res_top, self.res_mode)
        res_w = ttk.Frame(res_grp)
        res_w.pack(fill=tk.X, pady=(3, 0))
        ttk.Label(res_w, text="너비 최소:").pack(side=tk.LEFT)
        ttk.Entry(res_w, textvariable=self.res_min_w, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Label(res_w, text="최대:").pack(side=tk.LEFT)
        ttk.Entry(res_w, textvariable=self.res_max_w, width=6).pack(side=tk.LEFT, padx=3)
        res_h = ttk.Frame(res_grp)
        res_h.pack(fill=tk.X, pady=2)
        ttk.Label(res_h, text="높이 최소:").pack(side=tk.LEFT)
        ttk.Entry(res_h, textvariable=self.res_min_h, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Label(res_h, text="최대:").pack(side=tk.LEFT)
        ttk.Entry(res_h, textvariable=self.res_max_h, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Label(res_h, text="(빈 칸 = 무제한)").pack(side=tk.LEFT, padx=(5, 0))

        # 태그
        tag_grp = ttk.LabelFrame(grp, text="태그 (.txt)", padding="5")
        tag_grp.pack(fill=tk.X, pady=3)
        tag_top = ttk.Frame(tag_grp)
        tag_top.pack(fill=tk.X)
        ttk.Label(tag_top, text="모드:").pack(side=tk.LEFT)
        mode_radios(tag_top, self.tag_mode)
        tag_bot = ttk.Frame(tag_grp)
        tag_bot.pack(fill=tk.X, pady=(3, 0))
        ttk.Label(tag_bot, text="태그 (  |  로 구분):").pack(side=tk.LEFT)
        ttk.Entry(tag_bot, textvariable=self.tag_query).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 검색 버튼
        btn_f = ttk.Frame(grp)
        btn_f.pack(fill=tk.X, pady=(8, 0))
        self._search_btn = ttk.Button(btn_f, text="🔍  검색", command=self._start_search)
        self._search_btn.pack(side=tk.LEFT, padx=3)
        self._stop_btn = ttk.Button(
            btn_f, text="■  중지", command=self._stop_search, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=3)
        self._progress_var = tk.StringVar(value="")
        ttk.Label(btn_f, textvariable=self._progress_var).pack(side=tk.LEFT, padx=5)

    # ── 처리 설정 ────────────────────────────────────────────────────

    def _build_action_group(self, parent):
        grp = ttk.LabelFrame(parent, text="처리 설정", padding="8")
        grp.pack(fill=tk.X, pady=(0, 5))

        tgt_grp = ttk.LabelFrame(grp, text="처리 대상", padding="5")
        tgt_grp.pack(fill=tk.X, pady=3)
        for label, value in [
            ("이미지 + 태깅(.txt)", "both"),
            ("이미지만",            "image"),
            ("태깅(.txt)만",        "txt"),
        ]:
            ttk.Radiobutton(
                tgt_grp, text=label, variable=self.target_type, value=value,
            ).pack(anchor=tk.W)

        act_f = ttk.Frame(grp)
        act_f.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(act_f, text="🗑  삭제", command=self._action_delete).pack(side=tk.LEFT, padx=3)
        ttk.Button(act_f, text="📂  이동", command=self._action_move).pack(side=tk.LEFT, padx=3)
        ttk.Button(act_f, text="📋  복사", command=self._action_copy).pack(side=tk.LEFT, padx=3)

    # ── 결과 영역 ────────────────────────────────────────────────────

    def _build_result_area(self, parent):
        paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 상단: Treeview
        top_frame = ttk.Frame(paned)
        paned.add(top_frame, weight=3)

        ctrl_bar = ttk.Frame(top_frame)
        ctrl_bar.pack(fill=tk.X, padx=3, pady=(3, 2))

        self._result_count_var = tk.StringVar(value="검색 결과: 0건")
        ttk.Label(ctrl_bar, textvariable=self._result_count_var).pack(side=tk.LEFT, padx=5)

        ttk.Button(ctrl_bar, text="전체 선택",    command=self._select_all).pack(side=tk.RIGHT, padx=3)
        ttk.Button(ctrl_bar, text="전체 선택해제", command=self._deselect_all).pack(side=tk.RIGHT, padx=3)
        self._sel_count_var = tk.StringVar(value="선택: 0건")
        ttk.Label(ctrl_bar, textvariable=self._sel_count_var).pack(side=tk.RIGHT, padx=5)

        tree_frame = ttk.Frame(top_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=3)

        col_ids = [c[0] for c in _COLUMNS]
        self._tree = ttk.Treeview(
            tree_frame, columns=col_ids, show="headings", selectmode="browse")

        for col_id, col_label, col_width in _COLUMNS:
            self._tree.heading(
                col_id, text=col_label,
                command=lambda c=col_id: self._sort_by(c))
            anchor = tk.CENTER if col_id in (
                "check", "ext", "size_kb", "resolution") else tk.W
            self._tree.column(col_id, width=col_width, anchor=anchor, minwidth=20)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,   command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 하단: 미리보기
        bot_frame = ttk.Frame(paned)
        paned.add(bot_frame, weight=2)

        prev_paned = ttk.PanedWindow(bot_frame, orient=tk.HORIZONTAL)
        prev_paned.pack(fill=tk.BOTH, expand=True)

        # 이미지 미리보기 (Canvas 기반 - 패널 크기에 자동 fit)
        img_frame = ttk.LabelFrame(
            prev_paned, text="이미지 미리보기  (클릭하면 확대/축소 뷰어 창 열림)", padding="5")
        prev_paned.add(img_frame, weight=1)

        self._img_canvas = tk.Canvas(
            img_frame, bg="#2b2b2b", cursor="hand2", highlightthickness=0)
        self._img_canvas.pack(fill=tk.BOTH, expand=True)
        self._img_canvas.bind("<Configure>", self._on_preview_canvas_resize)
        self._img_canvas.bind("<Button-1>",  self._open_image_viewer)

        self._img_info_var = tk.StringVar(value="")
        ttk.Label(img_frame, textvariable=self._img_info_var, anchor=tk.CENTER).pack()

        # 태그 미리보기
        tag_frame = ttk.LabelFrame(prev_paned, text="태그(.txt) 내용 미리보기", padding="5")
        prev_paned.add(tag_frame, weight=1)

        self._tag_preview = scrolledtext.ScrolledText(
            tag_frame, wrap=tk.WORD, state=tk.DISABLED, height=8)
        self._tag_preview.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # 이벤트 핸들러
    # =========================================================================

    def _on_tree_click(self, event):
        """check 열 클릭 → 체크 토글"""
        region = self._tree.identify_region(event.x, event.y)
        col    = self._tree.identify_column(event.x)
        if region == "cell" and col == "#1":
            item = self._tree.identify_row(event.y)
            if item:
                self._toggle_check(item)

    def _toggle_check(self, item_id: str):
        idx = self._item_to_idx(item_id)
        if idx is None:
            return
        new_val = not self._check_vars[idx].get()
        self._check_vars[idx].set(new_val)
        self._tree.set(item_id, "check", "☑" if new_val else "☐")
        self._update_sel_count()

    def _on_tree_select(self, event):
        selected = self._tree.selection()
        if not selected:
            return
        idx = self._item_to_idx(selected[0])
        if idx is None:
            return
        self._show_preview(self._all_results[idx])

    def _item_to_idx(self, item_id: str) -> Optional[int]:
        try:
            return int(self._tree.item(item_id, "tags")[0])
        except (IndexError, ValueError, TypeError):
            return None

    # =========================================================================
    # 검색
    # =========================================================================

    def _start_search(self):
        folder = self._get_effective_folder()
        if not folder:
            messagebox.showwarning("경고", "작업 폴더를 먼저 선택하세요.")
            return

        conditions   = self._build_conditions()
        active_count = sum(1 for c in conditions if c.get('mode', 'unused') != 'unused')
        if active_count == 0:
            if not messagebox.askyesno(
                    "확인",
                    "활성 검색 조건이 없습니다.\n폴더 내 모든 파일을 불러오시겠습니까?"):
                return

        self._stop_event.clear()
        self._search_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._progress_var.set("검색 중...")
        self._clear_tree()

        cores = self.core_var.get() if self.core_var else 1

        def _run():
            results = search_files(
                folder_path=folder,
                recursive=self.recursive.get(),
                conditions=conditions,
                num_cores=cores,
                progress_callback=self._progress_cb,
                stop_event=self._stop_event,
            )
            self.parent.after(0, lambda: self._on_search_done(results))

        self._search_thread = threading.Thread(target=_run, daemon=True)
        self._search_thread.start()

    def _stop_search(self):
        self._stop_event.set()

    def _progress_cb(self, done: int, total: int):
        self.parent.after(0, lambda: self._progress_var.set(f"처리 중... {done}/{total}"))

    def _on_search_done(self, results: List[FileEntry]):
        self._all_results = results
        self._search_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._progress_var.set("")
        self._result_count_var.set(f"검색 결과: {len(results)}건")
        self._populate_tree(results)

    # =========================================================================
    # Treeview 조작
    # =========================================================================

    def _clear_tree(self):
        self._tree.delete(*self._tree.get_children())
        self._check_vars.clear()
        self._all_results.clear()
        self._sel_count_var.set("선택: 0건")
        self._result_count_var.set("검색 결과: 0건")

    def _populate_tree(self, entries: List[FileEntry]):
        self._tree.delete(*self._tree.get_children())
        self._check_vars = [tk.BooleanVar(value=False) for _ in entries]

        for idx, entry in enumerate(entries):
            res     = entry.resolution
            res_str = f"{res[0]}×{res[1]}" if res else "-"
            tag_list = entry.tags
            tags_preview = ", ".join(tag_list[:6])
            if len(tag_list) > 6:
                tags_preview += " ..."

            self._tree.insert("", tk.END, tags=(str(idx),), values=(
                "☐",
                entry.stem,
                entry.image_ext if entry.image_ext else ".txt",
                entry.folder,
                str(entry.file_size_kb),
                res_str,
                tags_preview,
            ))

        self._update_sel_count()

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col   = col
            self._sort_reverse = False

        def _key(entry: FileEntry):
            if col == "name":       return entry.stem.lower()
            if col == "ext":        return entry.image_ext
            if col == "folder":     return entry.folder.lower()
            if col == "size_kb":    return entry.file_size_kb
            if col == "resolution":
                res = entry.resolution
                return (res[0] * res[1]) if res else 0
            if col == "tags":       return entry.tag_content.lower()
            return ""

        self._all_results.sort(key=_key, reverse=self._sort_reverse)
        self._populate_tree(self._all_results)

    # =========================================================================
    # 선택 제어
    # =========================================================================

    def _select_all(self):
        for i, item in enumerate(self._tree.get_children()):
            self._check_vars[i].set(True)
            self._tree.set(item, "check", "☑")
        self._update_sel_count()

    def _deselect_all(self):
        for i, item in enumerate(self._tree.get_children()):
            self._check_vars[i].set(False)
            self._tree.set(item, "check", "☐")
        self._update_sel_count()

    def _update_sel_count(self):
        cnt = sum(1 for v in self._check_vars if v.get())
        self._sel_count_var.set(f"선택: {cnt}건")

    def _get_selected_entries(self) -> List[FileEntry]:
        return [e for e, v in zip(self._all_results, self._check_vars) if v.get()]

    # =========================================================================
    # 미리보기 (인라인 Canvas)
    # =========================================================================

    def _show_preview(self, entry: FileEntry):
        self._current_entry = entry

        if entry.has_image():
            try:
                img = Image.open(entry.image_path)
                img.load()                          # 파일 핸들 즉시 해제
                self._preview_orig_img = img
                self._render_preview_to_canvas()
                w, h = entry.resolution or (0, 0)
                self._img_info_var.set(
                    f"{entry.image_path.name}  ({w}×{h}, {entry.file_size_kb} KB)"
                    "  ─  클릭하면 뷰어 창이 열립니다"
                )
            except Exception as e:
                self._preview_orig_img = None
                self._img_canvas.delete("all")
                cx = self._img_canvas.winfo_width()  // 2 or 150
                cy = self._img_canvas.winfo_height() // 2 or 80
                self._img_canvas.create_text(
                    cx, cy, text=f"미리보기 실패\n{e}",
                    fill="#aaaaaa", justify=tk.CENTER)
                self._preview_img_ref = None
                self._img_info_var.set("")
        else:
            self._preview_orig_img = None
            self._img_canvas.delete("all")
            cx = self._img_canvas.winfo_width()  // 2 or 150
            cy = self._img_canvas.winfo_height() // 2 or 80
            self._img_canvas.create_text(cx, cy, text="이미지 없음", fill="#aaaaaa")
            self._preview_img_ref = None
            self._img_info_var.set("")

        # 태그 미리보기
        self._tag_preview.config(state=tk.NORMAL)
        self._tag_preview.delete("1.0", tk.END)
        self._tag_preview.insert(
            tk.END, entry.tag_content if entry.has_txt() else "(태그 파일 없음)")
        self._tag_preview.config(state=tk.DISABLED)

    def _render_preview_to_canvas(self):
        """원본 PIL 이미지를 현재 Canvas 크기에 비율 유지하여 fit 렌더링."""
        if self._preview_orig_img is None:
            return
        self._img_canvas.update_idletasks()
        cw = self._img_canvas.winfo_width()
        ch = self._img_canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        img = self._preview_orig_img.copy()
        img = _apply_exif_orientation(img)

        iw, ih = img.size
        scale   = min(cw / iw, ch / ih)
        new_w   = max(1, int(iw * scale))
        new_h   = max(1, int(ih * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)

        photo = ImageTk.PhotoImage(resized)
        self._img_canvas.delete("all")
        self._img_canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=photo)
        self._preview_img_ref = photo   # GC 방지

    def _on_preview_canvas_resize(self, event):
        """Canvas 크기 변경 시 100ms 디바운스 후 재렌더."""
        if self._resize_job:
            self._img_canvas.after_cancel(self._resize_job)
        self._resize_job = self._img_canvas.after(100, self._render_preview_to_canvas)

    def _open_image_viewer(self, event=None):
        """인라인 미리보기 클릭 시 독립 뷰어 창 열기."""
        if self._preview_orig_img is None or self._current_entry is None:
            return
        if not self._current_entry.has_image():
            return
        try:
            ImageViewerWindow(
                parent=self._img_canvas,
                image_path=self._current_entry.image_path,
            )
        except Exception as e:
            messagebox.showerror("오류", f"이미지 뷰어를 열 수 없습니다.\n{e}")

    # =========================================================================
    # 파일 처리 액션
    # =========================================================================

    def _check_selection(self) -> Optional[List[FileEntry]]:
        selected = self._get_selected_entries()
        if not selected:
            messagebox.showwarning("경고", "처리할 항목을 선택하세요.")
            return None
        return selected

    def _warn_orphan(self, selected: List[FileEntry]) -> bool:
        """일부만 처리 시 남게 될 고아 파일 경고. True=계속, False=취소."""
        orphans = get_orphan_warning(selected, self.target_type.get())
        if not orphans:
            return True
        preview = "\n".join(orphans[:10])
        if len(orphans) > 10:
            preview += f"\n... 외 {len(orphans) - 10}건"
        return messagebox.askyesno(
            "짝 없는 파일 발생 경고",
            f"처리 후 아래 파일들이 짝 없이 남게 됩니다.\n"
            f"(단일 파일 찾기 기능으로 나중에 정리할 수 있습니다.)\n\n"
            f"{preview}\n\n계속 진행하시겠습니까?",
        )

    def _ttype_label(self) -> str:
        return {"both": "이미지+태깅", "image": "이미지만", "txt": "태깅만"}.get(
            self.target_type.get(), "")

    def _action_delete(self):
        selected = self._check_selection()
        if selected is None:
            return
        if not self._warn_orphan(selected):
            return
        if not messagebox.askyesno(
                "삭제 확인",
                f"선택한 {len(selected)}개 항목을 삭제합니다.\n"
                f"처리 대상: {self._ttype_label()}\n\n"
                "이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?"):
            return
        success, fail, logs = process_entries(
            selected, 'delete', self.target_type.get())
        self._show_result_log("삭제", success, fail, logs)
        self._start_search()

    def _action_move(self):
        selected = self._check_selection()
        if selected is None:
            return
        dest = filedialog.askdirectory(title="이동할 폴더 선택")
        if not dest:
            return
        if not self._warn_orphan(selected):
            return
        if not messagebox.askyesno(
                "이동 확인",
                f"선택한 {len(selected)}개 항목을\n{dest}\n으로 이동합니다.\n"
                f"처리 대상: {self._ttype_label()}\n\n계속하시겠습니까?"):
            return
        success, fail, logs = process_entries(
            selected, 'move', self.target_type.get(), dest)
        self._show_result_log("이동", success, fail, logs)
        self._start_search()

    def _action_copy(self):
        selected = self._check_selection()
        if selected is None:
            return
        dest = filedialog.askdirectory(title="복사할 폴더 선택")
        if not dest:
            return
        if not messagebox.askyesno(
                "복사 확인",
                f"선택한 {len(selected)}개 항목을\n{dest}\n으로 복사합니다.\n"
                f"처리 대상: {self._ttype_label()}\n\n계속하시겠습니까?"):
            return
        success, fail, logs = process_entries(
            selected, 'copy', self.target_type.get(), dest)
        self._show_result_log("복사", success, fail, logs)

    def _show_result_log(self, action_name: str, success: int, fail: int, logs: List[str]):
        log_win = tk.Toplevel(self.parent)
        log_win.title(f"{action_name} 결과")
        log_win.geometry("600x400")

        ttk.Label(
            log_win,
            text=f"성공: {success}건  /  실패: {fail}건",
            font=("", 11, "bold"),
        ).pack(anchor=tk.W, padx=10, pady=6)

        txt = scrolledtext.ScrolledText(log_win, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        txt.insert(tk.END, "\n".join(logs))
        txt.config(state=tk.DISABLED)

        ttk.Button(log_win, text="닫기", command=log_win.destroy).pack(pady=(0, 8))

        messagebox.showinfo(f"{action_name} 완료",
                            f"성공: {success}건,  실패: {fail}건")


# ===========================================================================
# 공통 EXIF 방향 보정 헬퍼
# ===========================================================================

def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    """EXIF Orientation 태그에 따라 이미지를 바르게 회전/반전합니다."""
    try:
        import piexif
        exif_bytes = img.info.get("exif")
        if not exif_bytes:
            return img
        exif = piexif.load(exif_bytes)
        orientation = exif.get("0th", {}).get(piexif.ImageIFD.Orientation, 1)
        ops = {
            2: lambda i: i.transpose(Image.FLIP_LEFT_RIGHT),
            3: lambda i: i.rotate(180),
            4: lambda i: i.transpose(Image.FLIP_TOP_BOTTOM),
            5: lambda i: i.transpose(Image.FLIP_LEFT_RIGHT).rotate(90,  expand=True),
            6: lambda i: i.rotate(-90, expand=True),
            7: lambda i: i.transpose(Image.FLIP_LEFT_RIGHT).rotate(-90, expand=True),
            8: lambda i: i.rotate(90,  expand=True),
        }
        if orientation in ops:
            img = ops[orientation](img)
    except Exception:
        pass
    return img


# ===========================================================================
# 독립 이미지 뷰어 창 (확대/축소/패닝)
# ===========================================================================

class ImageViewerWindow:
    """
    별도 Toplevel 창에서 이미지를 확대·축소·드래그 패닝할 수 있는 뷰어.

    조작법
    ──────
    마우스 휠         : 커서 위치 중심으로 확대/축소
    좌클릭 드래그     : 이미지 이동(패닝)
    더블클릭 / R 키   : 창 크기에 맞춤(fit) 리셋
    +/= 키            : 확대
    - 키              : 축소
    툴바 버튼         : 확대·축소·창 맞춤·원본(1:1)
    """

    MIN_ZOOM  = 0.05
    MAX_ZOOM  = 20.0
    ZOOM_STEP = 1.15

    def __init__(self, parent, image_path: Path):
        self._image_path = image_path
        self._zoom       = 1.0
        self._pan_x      = 0.0
        self._pan_y      = 0.0
        self._drag_start = None
        self._photo_ref  = None
        self._resize_job_viewer = None

        self._win = tk.Toplevel(parent)
        self._win.title(f"이미지 뷰어  —  {image_path.name}")
        self._win.geometry("900x700")
        self._win.minsize(400, 300)

        self._build_toolbar()
        self._build_canvas()
        self._load_image()
        self._win.after(50, self._fit_to_window)   # 창이 완전히 그려진 뒤 fit
        self._win.bind("<Configure>", self._on_win_resize)
        self._win.focus_set()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = ttk.Frame(self._win)
        bar.pack(fill=tk.X, padx=5, pady=3)

        ttk.Button(bar, text="확대 (+)", width=9,
                   command=lambda: self._zoom_by(self.ZOOM_STEP)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="축소 (−)", width=9,
                   command=lambda: self._zoom_by(1 / self.ZOOM_STEP)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="창 크기에 맞춤",
                   command=self._fit_to_window).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="원본 크기 (1:1)",
                   command=self._reset_to_actual).pack(side=tk.LEFT, padx=2)

        self._zoom_var = tk.StringVar(value="100%")
        ttk.Label(bar, textvariable=self._zoom_var,
                  width=7, anchor=tk.CENTER).pack(side=tk.LEFT, padx=8)

        self._info_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self._info_var, anchor=tk.W).pack(side=tk.LEFT, padx=5)

        ttk.Label(
            bar,
            text="[휠] 확대/축소   [드래그] 이동   [더블클릭/R] 맞춤 리셋",
            foreground="#888888",
        ).pack(side=tk.RIGHT, padx=8)

    def _build_canvas(self):
        frame = ttk.Frame(self._win)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self._canvas = tk.Canvas(
            frame, bg="#1e1e1e", cursor="fleur", highlightthickness=0)
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL,   command=self._canvas.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # 이벤트
        self._canvas.bind("<MouseWheel>",      self._on_mousewheel)   # Windows
        self._canvas.bind("<Button-4>",        self._on_mousewheel)   # Linux ↑
        self._canvas.bind("<Button-5>",        self._on_mousewheel)   # Linux ↓
        self._canvas.bind("<ButtonPress-1>",   self._on_drag_start)
        self._canvas.bind("<B1-Motion>",       self._on_drag_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._canvas.bind("<Double-Button-1>", lambda e: self._fit_to_window())
        self._win.bind("<r>",     lambda e: self._fit_to_window())
        self._win.bind("<R>",     lambda e: self._fit_to_window())
        self._win.bind("<plus>",  lambda e: self._zoom_by(self.ZOOM_STEP))
        self._win.bind("<equal>", lambda e: self._zoom_by(self.ZOOM_STEP))
        self._win.bind("<minus>", lambda e: self._zoom_by(1 / self.ZOOM_STEP))

    # ── 이미지 로드 ───────────────────────────────────────────────────

    def _load_image(self):
        img = Image.open(self._image_path)
        img.load()
        img = _apply_exif_orientation(img)
        self._orig_img  = img
        self._orig_w, self._orig_h = img.size

        size_kb = round(self._image_path.stat().st_size / 1024, 1)
        self._info_var.set(f"{self._orig_w}×{self._orig_h}px  /  {size_kb} KB")

    # ── 렌더링 ────────────────────────────────────────────────────────

    def _render(self):
        new_w = max(1, int(self._orig_w * self._zoom))
        new_h = max(1, int(self._orig_h * self._zoom))

        resized = self._orig_img.resize((new_w, new_h), Image.LANCZOS)
        photo   = ImageTk.PhotoImage(resized)

        self._canvas.delete("all")
        self._canvas.create_image(
            int(self._pan_x), int(self._pan_y), anchor=tk.NW, image=photo)
        self._photo_ref = photo     # GC 방지

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        self._canvas.configure(scrollregion=(
            min(0, int(self._pan_x)),
            min(0, int(self._pan_y)),
            max(cw, int(self._pan_x) + new_w),
            max(ch, int(self._pan_y) + new_h),
        ))
        self._zoom_var.set(f"{int(self._zoom * 100)}%")

    # ── 줌 제어 ──────────────────────────────────────────────────────

    def _fit_to_window(self):
        self._canvas.update_idletasks()
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            self._win.after(80, self._fit_to_window)
            return
        self._zoom = max(self.MIN_ZOOM, min(
            self.MAX_ZOOM, min(cw / self._orig_w, ch / self._orig_h)))
        new_w = int(self._orig_w * self._zoom)
        new_h = int(self._orig_h * self._zoom)
        self._pan_x = max(0, (cw - new_w) // 2)
        self._pan_y = max(0, (ch - new_h) // 2)
        self._render()

    def _reset_to_actual(self):
        self._zoom  = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._render()

    def _zoom_by(self, factor: float, cx: int = None, cy: int = None):
        new_zoom = max(self.MIN_ZOOM, min(
            self.MAX_ZOOM, self._zoom * factor))
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

    # ── 이벤트 핸들러 ────────────────────────────────────────────────

    def _on_mousewheel(self, event):
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        else:
            delta = event.delta
        factor = self.ZOOM_STEP if delta > 0 else (1 / self.ZOOM_STEP)
        self._zoom_by(factor, cx=event.x, cy=event.y)

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag_move(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._pan_x += dx
        self._pan_y += dy
        self._drag_start = (event.x, event.y)
        self._render()

    def _on_drag_end(self, event):
        self._drag_start = None

    def _on_win_resize(self, event):
        if self._resize_job_viewer:
            self._win.after_cancel(self._resize_job_viewer)
        self._resize_job_viewer = self._win.after(120, self._fit_to_window)