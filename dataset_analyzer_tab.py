import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import csv
from pathlib import Path
from dataset_analyzer import DatasetAnalyzer, DatasetSnapshot
from utils import ScrollableFrame


# ═══════════════════════════════════════════════════════════════
# 데이터셋 분석 메인 탭 GUI
# ═══════════════════════════════════════════════════════════════

class DatasetAnalyzerGUI:
    def __init__(self, parent, folder_path_var=None, core_var=None):
        self.parent = parent
        self.folder_path_var = folder_path_var if folder_path_var else tk.StringVar()
        self.core_var = core_var
        
        # UI 변수
        self.use_independent_path = tk.BooleanVar(value=False)
        self.independent_folder_path = tk.StringVar()
        
        self.recursive = tk.BooleanVar(value=True)
        self.include_empty = tk.BooleanVar(value=False)
        self.include_untagged = tk.BooleanVar(value=False)
        
        # 버킷 설정 변수
        self.use_custom_buckets = tk.BooleanVar(value=False)
        self.target_reso = tk.IntVar(value=1024)
        self.bucket_reso_steps = tk.IntVar(value=64)
        self.min_bucket_reso = tk.IntVar(value=256)
        self.max_bucket_reso = tk.IntVar(value=2048)
        
        self.batch_size = tk.IntVar(value=1)
        self.grad_acc = tk.IntVar(value=1)
        self.epochs = tk.IntVar(value=10)
        
        self.results = [] 
        self.avg_data = 0
        
        # 정렬 상태 저장 (컬럼, 역순여부)
        self.current_sort = (None, False)
        
        self.setup_ui()

    def setup_ui(self):
        scroll = ScrollableFrame(self.parent)
        scroll.pack(fill=tk.BOTH, expand=True)
        container = scroll.scrollable_frame
        
        # 1. 상단 설정 영역
        settings_frame = ttk.LabelFrame(container, text="분석 설정", padding="10")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 1-1. 경로 설정
        path_frame = ttk.Frame(settings_frame)
        path_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(path_frame, text="독립 경로 사용", variable=self.use_independent_path, command=self.toggle_path_ui).pack(side=tk.LEFT)
        self.indep_entry = ttk.Entry(path_frame, textvariable=self.independent_folder_path, width=40)
        self.indep_entry.pack(side=tk.LEFT, padx=5)
        self.indep_btn = ttk.Button(path_frame, text="폴더 선택", command=self.select_folder)
        self.indep_btn.pack(side=tk.LEFT)
        
        # 1-2. 옵션 체크박스
        opts_frame = ttk.Frame(settings_frame)
        opts_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(opts_frame, text="하위 폴더 포함", variable=self.recursive).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Checkbutton(opts_frame, text="빈 폴더 포함 (최하위 한정)", variable=self.include_empty).pack(side=tk.LEFT, padx=15)
        ttk.Checkbutton(opts_frame, text="미 태깅 파일 포함", variable=self.include_untagged).pack(side=tk.LEFT, padx=15)
        
        # 1-2-1. 버킷 상세 설정
        buckets_frame = ttk.LabelFrame(settings_frame, text="학습 환경 설정", padding="5")
        buckets_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(buckets_frame, text="사용자 정의 버킷", variable=self.use_custom_buckets, command=self.toggle_bucket_ui).pack(side=tk.LEFT, padx=(0, 10))
        
        self.target_reso_label = ttk.Label(buckets_frame, text="기준 해상도(--resolution):")
        self.target_reso_label.pack(side=tk.LEFT, padx=2)
        self.target_reso_entry = ttk.Spinbox(buckets_frame, from_=256, to=4096, increment=64, textvariable=self.target_reso, width=6)
        self.target_reso_entry.pack(side=tk.LEFT, padx=5)

        self.bucket_steps_label = ttk.Label(buckets_frame, text="단위(steps):")
        self.bucket_steps_label.pack(side=tk.LEFT, padx=2)
        self.bucket_steps_entry = ttk.Spinbox(buckets_frame, from_=8, to=1024, increment=8, textvariable=self.bucket_reso_steps, width=5)
        self.bucket_steps_entry.pack(side=tk.LEFT, padx=5)
        
        self.min_bucket_label = ttk.Label(buckets_frame, text="최소:")
        self.min_bucket_label.pack(side=tk.LEFT, padx=2)
        self.min_bucket_entry = ttk.Spinbox(buckets_frame, from_=64, to=4096, increment=64, textvariable=self.min_bucket_reso, width=6)
        self.min_bucket_entry.pack(side=tk.LEFT, padx=5)
        
        self.max_bucket_label = ttk.Label(buckets_frame, text="최대:")
        self.max_bucket_label.pack(side=tk.LEFT, padx=2)
        self.max_bucket_entry = ttk.Spinbox(buckets_frame, from_=64, to=8192, increment=64, textvariable=self.max_bucket_reso, width=6)
        self.max_bucket_entry.pack(side=tk.LEFT, padx=5)
        
        # 1-3. 학습 파라미터
        params_frame = ttk.LabelFrame(settings_frame, text="학습 파라미터", padding="5")
        params_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(params_frame, text="배치:").pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(params_frame, from_=1, to=1024, textvariable=self.batch_size, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(params_frame, text="그라디언트(Gradient Acc):").pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(params_frame, from_=1, to=1024, textvariable=self.grad_acc, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(params_frame, text="에포크:").pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(params_frame, from_=1, to=10000, textvariable=self.epochs, width=6).pack(side=tk.LEFT, padx=5)
        
        # 2. 버튼 영역
        btn_frame = ttk.Frame(container, padding="5")
        btn_frame.pack(fill=tk.X, padx=10)
        
        self.search_btn = ttk.Button(btn_frame, text="검색 (폴더 스캔)", command=self.start_search)
        self.search_btn.pack(side=tk.LEFT, padx=5)
        
        self.analyze_btn = ttk.Button(btn_frame, text="분석 (계산 갱신)", command=self.update_analysis, state=tk.DISABLED)
        self.analyze_btn.pack(side=tk.LEFT, padx=5)

        self.export_btn = ttk.Button(btn_frame, text="CSV로 출력", command=self.export_to_csv, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=2)
        
        self.mismatch_btn = ttk.Button(btn_frame, text="버킷 미스 매치", command=self.show_mismatch_window, state=tk.DISABLED)
        self.mismatch_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Button(btn_frame, text="리핏 일괄 설정", command=self.ask_all_repeats).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="추천 리핏 설정", command=self.set_recommended_repeats).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="최적 리핏 설정", command=self.set_optimal_repeats).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="균등 리핏 설정", command=self.set_averaged_repeats).pack(side=tk.LEFT, padx=2)

        # 3. 요약 정보 영역 ─────────────────────────────────────────────
        # 스냅샷 버튼을 오른쪽 끝에 배치하기 위해 grid 레이아웃 사용
        self.summary_frame = ttk.LabelFrame(container, text="요약 결과", padding="10")
        self.summary_frame.pack(fill=tk.X, padx=10, pady=5)
        self.summary_frame.columnconfigure(0, weight=1)

        self.summary_label = ttk.Label(self.summary_frame, text="검색을 진행해주세요.", justify=tk.LEFT)
        self.summary_label.grid(row=0, column=0, sticky=tk.W)

        ttk.Button(
            self.summary_frame,
            text="데이터셋 스냅샷",
            command=self.show_snapshot_window
        ).grid(row=0, column=1, sticky=tk.E, padx=(15, 0))
        # ──────────────────────────────────────────────────────────────
        
        # 4. 결과 테이블 영역 (Treeview)
        table_frame = ttk.Frame(container, padding="5")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        cols = ("folder", "count", "buckets", "recommend", "repeat", "total_ops", "steps", "waste")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=15)
        
        self.tree.heading("folder",     text="폴더 이름",          command=lambda: self.treeview_sort_column("folder", False))
        self.tree.heading("count",      text="원본 수",             command=lambda: self.treeview_sort_column("count", True))
        self.tree.heading("buckets",    text="버킷(종류)")
        self.tree.heading("recommend",  text="추천 리핏")
        self.tree.heading("repeat",     text="설정 리핏")
        self.tree.heading("total_ops",  text="처리량(이론/실제)")
        self.tree.heading("steps",      text="스텝(이론/실제)")
        self.tree.heading("waste",      text="낭비율",              command=lambda: self.treeview_sort_column("waste", True))
        
        self.tree.column("folder",    width=180)
        self.tree.column("count",     width=80,  anchor=tk.CENTER)
        self.tree.column("buckets",   width=220)
        self.tree.column("recommend", width=80,  anchor=tk.CENTER)
        self.tree.column("repeat",    width=80,  anchor=tk.CENTER)
        self.tree.column("total_ops", width=150, anchor=tk.CENTER)
        self.tree.column("steps",     width=150, anchor=tk.CENTER)
        self.tree.column("waste",     width=80,  anchor=tk.CENTER)
        
        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        
        self.toggle_path_ui()
        self.toggle_bucket_ui()

    # ── 정렬 ──────────────────────────────────────────────────
    def treeview_sort_column(self, col, reverse):
        self.current_sort = (col, reverse)
        self._apply_sort()
        self.tree.heading(col, command=lambda: self.treeview_sort_column(col, not reverse))

    def _apply_sort(self):
        col, reverse = self.current_sort
        if col is None: return
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def try_float(v):
            try:
                clean_v = "".join(c for c in str(v) if c.isdigit() or c == '.')
                return float(clean_v) if clean_v else v
            except: return v
        l.sort(key=lambda t: try_float(t[0]), reverse=reverse)
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

    # ── UI 토글 ───────────────────────────────────────────────
    def toggle_path_ui(self):
        state = tk.NORMAL if self.use_independent_path.get() else tk.DISABLED
        self.indep_entry.config(state=state)
        self.indep_btn.config(state=state)

    def toggle_bucket_ui(self):
        state = tk.NORMAL if self.use_custom_buckets.get() else tk.DISABLED
        self.target_reso_entry.config(state=state)
        self.bucket_steps_entry.config(state=state)
        self.min_bucket_entry.config(state=state)
        self.max_bucket_entry.config(state=state)
        
        label_color = "black" if self.use_custom_buckets.get() else "gray"
        self.target_reso_label.config(foreground=label_color)
        self.bucket_steps_label.config(foreground=label_color)
        self.min_bucket_label.config(foreground=label_color)
        self.max_bucket_label.config(foreground=label_color)

    def select_folder(self):
        f = filedialog.askdirectory()
        if f: self.independent_folder_path.set(f)

    # ── 검색 / 분석 ───────────────────────────────────────────
    def start_search(self):
        path = self.independent_folder_path.get() if self.use_independent_path.get() else self.folder_path_var.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("경고", "올바른 경로를 선택해주세요.")
            return
        self.search_btn.config(state=tk.DISABLED)
        self.analyze_btn.config(state=tk.DISABLED)
        self.export_btn.config(state=tk.DISABLED)
        def run():
            num_cores = self.core_var.get() if self.core_var else 1
            
            bucket_settings = None
            if self.use_custom_buckets.get():
                bucket_settings = {
                    'target_res':    self.target_reso.get(),
                    'bucket_steps':  self.bucket_reso_steps.get(),
                    'bucket_min':    self.min_bucket_reso.get(),
                    'bucket_max':    self.max_bucket_reso.get()
                }
                
            raw_results = DatasetAnalyzer.scan_directories(
                path, self.recursive.get(), self.include_empty.get(),
                self.include_untagged.get(), num_cores, bucket_settings
            )
            self.parent.after(0, lambda: self.finish_search(raw_results))
        threading.Thread(target=run, daemon=True).start()

    def finish_search(self, raw_results):
        self.results = raw_results
        total_data = sum(r['count'] for r in self.results)
        self.avg_data = total_data / len(self.results) if self.results else 0
        
        for r in self.results:
            r['repeat'] = 1
            
        self._update_recommend_column()
        self.update_table()
        self.update_summary()
        self.search_btn.config(state=tk.NORMAL)
        self.analyze_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        
        total_mismatches = sum(len(r.get('mismatches', [])) for r in self.results)
        if total_mismatches > 0:
            self.mismatch_btn.config(state=tk.NORMAL)
        else:
            self.mismatch_btn.config(state=tk.DISABLED)

    def _update_recommend_column(self):
        if not self.results: return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        rec_repeats = DatasetAnalyzer.calculate_recommend_repeats(self.results, batch_total)
        for r, rec in zip(self.results, rec_repeats):
            r['recommend'] = rec
            self._recalculate_folder(r)

    def update_table(self):
        self.tree.delete(*self.tree.get_children())
        batch_total = self.batch_size.get() * self.grad_acc.get()
        for r in self.results:
            marker = "▲" if r['count'] >= self.avg_data else "▼"
            count_str = f"{marker} {r['count']}개"
            bucket_types = len(r['buckets'])
            buckets_str = f"[{bucket_types}종] " + ", ".join([f"{k}:{v}" for k, v in sorted(r['buckets'].items())])
            
            theo_ops  = r['count'] * r['repeat']
            actual_ops = r['steps'] * batch_total
            ops_display   = f"{theo_ops} / {actual_ops}"
            steps_display = f"{r['theoretical_steps']:.1f} / {r['steps']}"
            
            self.tree.insert("", tk.END, values=(
                r['folder_name'], count_str, buckets_str, r['recommend'], r['repeat'],
                ops_display, steps_display, f"{r['waste_rate']:.2f}%"
            ), tags=(r['folder_path'],))
        if self.current_sort[0]: self._apply_sort()

    def update_summary(self):
        if not self.results:
            self.summary_label.config(text="검색 결과가 없습니다.")
            return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        epochs = self.epochs.get()
        total_folders  = len(self.results)
        total_data     = sum(r['count'] for r in self.results)
        total_steps_per_epoch      = sum(r['steps'] for r in self.results)
        total_steps                = total_steps_per_epoch * epochs
        total_theo_steps_per_epoch = sum(r['theoretical_steps'] for r in self.results)
        total_theo_steps           = total_theo_steps_per_epoch * epochs
        total_waste_slots = 0
        total_slots = 0
        for r in self.results:
            w_slots, _, steps = DatasetAnalyzer.calculate_waste(r['buckets'], r['repeat'], batch_total)
            total_waste_slots += w_slots
            total_slots       += steps * batch_total
        avg_waste_rate = (total_waste_slots / total_slots * 100) if total_slots > 0 else 0
        
        total_mismatches = sum(len(r.get('mismatches', [])) for r in self.results)
        mismatch_text = f"⚠️ 비율 미스매치 감지: {total_mismatches}건\n" if total_mismatches > 0 else ""

        summary_text = (
            f"{mismatch_text}"
            f"최종 배치(배치*그라디언트): {batch_total} | 총 폴더: {total_folders}개 | "
            f"총 데이터셋: {total_data}개 | 폴더당 평균: {self.avg_data:.1f}개\n"
            f"이론적 스텝 (1에포크): {total_theo_steps_per_epoch:.1f} | "
            f"이론적 총 스텝 ({epochs}에포크): {total_theo_steps:.1f}\n"
            f"실제 예상 스텝 (1에포크): {total_steps_per_epoch} | "
            f"실제 예상 총 스텝 ({epochs}에포크): {total_steps} | "
            f"평균 배치 슬롯 낭비율: {avg_waste_rate:.2f}%"
        )
        self.summary_label.config(text=summary_text)

    # ── 리핏 설정 ─────────────────────────────────────────────
    def on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        column  = self.tree.identify_column(event.x)
        if not item_id or column != "#5": return
        item_values = self.tree.item(item_id, 'values')
        tags = self.tree.item(item_id, 'tags')
        if not tags: return
        folder_path = tags[0]
        import tkinter.simpledialog as sd
        new_val = sd.askinteger("리핏 수정", f"'{item_values[0]}' 폴더의 리핏 값을 입력하세요:", initialvalue=int(item_values[4]), minvalue=0)
        if new_val is not None:
            for r in self.results:
                if r['folder_path'] == folder_path:
                    r['repeat'] = new_val
                    self._recalculate_folder(r)
                    break
            self.update_table()
            self.update_summary()

    def _recalculate_folder(self, r):
        batch_total = self.batch_size.get() * self.grad_acc.get()
        _, waste_rate, steps = DatasetAnalyzer.calculate_waste(r['buckets'], r['repeat'], batch_total)
        r['waste_rate']         = waste_rate
        r['steps']              = steps
        r['theoretical_steps']  = DatasetAnalyzer.calculate_theoretical_steps(r['count'], r['repeat'], batch_total)

    def ask_all_repeats(self):
        if not self.results: return
        import tkinter.simpledialog as sd
        val = sd.askinteger("리핏 일괄 설정", "모든 폴더에 적용할 리핏 값을 입력하세요:", initialvalue=1, minvalue=0)
        if val is not None:
            self.set_all_repeats(val)

    def set_all_repeats(self, val):
        if not self.results: return
        for r in self.results:
            r['repeat'] = val
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()

    def set_recommended_repeats(self):
        if not self.results: return
        for r in self.results:
            r['repeat'] = r.get('recommend', 1)
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()

    def set_optimal_repeats(self):
        if not self.results: return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        for r in self.results:
            if r['count'] < self.avg_data:
                r['repeat'] = batch_total
            else:
                r['repeat'] = r.get('recommend', 1)
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()

    def set_averaged_repeats(self):
        if not self.results: return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        
        base_total_steps = 0
        for r in self.results:
            _, _, steps = DatasetAnalyzer.calculate_waste(r['buckets'], 1, batch_total)
            base_total_steps += steps
        
        avg_base_step = base_total_steps / len(self.results) if self.results else 1
        
        for r in self.results:
            if r['count'] > 0:
                ideal_r      = (avg_base_step * batch_total) / r['count']
                base_r       = max(1, round(ideal_r))
                search_range = [max(1, base_r - 1), base_r, base_r + 1, base_r + 2]
                
                best_r    = base_r
                min_score = float('inf')
                
                for cand in sorted(list(set(search_range))):
                    _, waste_rate, steps = DatasetAnalyzer.calculate_waste(r['buckets'], cand, batch_total)
                    step_error    = abs(steps - avg_base_step)
                    waste_penalty = (waste_rate / 100) * 0.5
                    score         = step_error + waste_penalty
                    
                    if score < min_score:
                        min_score = score
                        best_r    = cand
                    elif abs(score - min_score) < 1e-7:
                        if best_r % 2 != 0 and cand % 2 == 0:
                            best_r = cand

                r['repeat'] = best_r
            else:
                r['repeat'] = 1
            self._recalculate_folder(r)
        
        self.update_table()
        self.update_summary()

    def update_analysis(self):
        batch_total = self.batch_size.get() * self.grad_acc.get()
        
        if self.use_custom_buckets.get():
            b_target = self.target_reso.get()
            b_steps  = self.bucket_reso_steps.get()
            b_min    = self.min_bucket_reso.get()
            b_max    = self.max_bucket_reso.get()
        else:
            b_target, b_steps, b_min, b_max = 1024, 64, 256, 2048

        total_data     = sum(r['count'] for r in self.results)
        self.avg_data  = total_data / len(self.results) if self.results else 0
        
        bucket_list = DatasetAnalyzer.make_buckets(b_target, b_min, b_max, b_steps)
        bucket_ars  = [bw / bh for bw, bh in bucket_list]
        
        for r in self.results:
            if 'image_dims' in r and r['image_dims']:
                r['buckets']    = DatasetAnalyzer.rebucketize(r['image_dims'], b_steps, b_min, b_max, b_target)
                r['mismatches'] = []
                
                for w, h in r['image_dims']:
                    orig_ar = w / h
                    diffs   = [abs(orig_ar - b_ar) for b_ar in bucket_ars]
                    best_idx = diffs.index(min(diffs))
                    b_ar    = bucket_ars[best_idx]
                    bw, bh  = bucket_list[best_idx]
                    
                    if abs(orig_ar - b_ar) / b_ar > 0.3:
                        r['mismatches'].append({
                            'file_name':   "(계산 갱신됨)",
                            'resolution':  f"{w}x{h}",
                            'orig_ar':     round(orig_ar, 3),
                            'bucket_ar':   round(b_ar, 3),
                            'bucket_res':  f"{bw}x{bh}",
                            'folder_path': r['folder_path']
                        })
            
            self._recalculate_folder(r)
            
        self._update_recommend_column()
        self.update_table()
        self.update_summary()
        
        total_mismatches = sum(len(r.get('mismatches', [])) for r in self.results)
        if total_mismatches > 0:
            self.mismatch_btn.config(state=tk.NORMAL)
        else:
            self.mismatch_btn.config(state=tk.DISABLED)

    # ── 미스매치 창 ───────────────────────────────────────────
    def show_mismatch_window(self):
        mismatches = []
        for r in self.results:
            mismatches.extend(r.get('mismatches', []))
            
        if not mismatches:
            messagebox.showinfo("알림", "비율 미스매치 이미지가 없습니다.")
            return
            
        win = tk.Toplevel(self.parent)
        win.title("버킷 비율 미스매치 검수 (차이 30% 초과)")
        win.geometry("900x500")
        
        frame = ttk.Frame(win, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text=f"총 {len(mismatches)}개의 이미지가 배정된 버킷과 비율 차이가 큽니다. (학습 시 이미지 왜곡 주의)", foreground="red").pack(pady=5)
        
        cols = ("file", "res", "orig_ar", "bucket_ar", "bucket_res", "path")
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.heading("file",       text="파일명")
        tree.heading("res",        text="원본 해상도")
        tree.heading("orig_ar",    text="원본 AR")
        tree.heading("bucket_ar",  text="버킷 AR")
        tree.heading("bucket_res", text="배정 버킷")
        tree.heading("path",       text="폴더 경로")
        
        tree.column("file",       width=150)
        tree.column("res",        width=100, anchor=tk.CENTER)
        tree.column("orig_ar",    width=80,  anchor=tk.CENTER)
        tree.column("bucket_ar",  width=80,  anchor=tk.CENTER)
        tree.column("bucket_res", width=100, anchor=tk.CENTER)
        tree.column("path",       width=300)
        
        for m in mismatches:
            tree.insert("", tk.END, values=(m['file_name'], m['resolution'], m['orig_ar'], m['bucket_ar'], m['bucket_res'], m['folder_path']))
            
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        def save_mismatch_csv():
            file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if not file_path: return
            try:
                with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["파일명", "원본 해상도", "원본 종횡비", "버킷 종횡비", "배정 버킷 해상도", "폴더 경로"])
                    for m in mismatches:
                        writer.writerow([m['file_name'], m['resolution'], m['orig_ar'], m['bucket_ar'], m['bucket_res'], m['folder_path']])
                messagebox.showinfo("완료", f"미스매치 목록이 저장되었습니다:\n{file_path}")
            except Exception as e:
                messagebox.showerror("오류", f"저장 중 오류: {e}")

        btn_frame = ttk.Frame(win, padding="10")
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="목록 CSV로 저장", command=save_mismatch_csv).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="닫기", command=win.destroy).pack(side=tk.RIGHT, padx=5)

    # ── CSV 내보내기 ──────────────────────────────────────────
    def export_to_csv(self):
        if not self.results: return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not file_path: return
        try:
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["[데이터셋 분석 요약 결과]"])
                batch_total = self.batch_size.get() * self.grad_acc.get()
                writer.writerow(["최종 배치",       batch_total])
                writer.writerow(["총 폴더 수",       len(self.results)])
                writer.writerow(["총 데이터셋 수",   sum(r['count'] for r in self.results)])
                writer.writerow(["폴더당 평균 데이터셋", f"{self.avg_data:.2f}"])
                
                if self.use_custom_buckets.get():
                    writer.writerow(["버킷 설정",      "사용자 정의 (kohya-ss 스타일)"])
                    writer.writerow(["기준 해상도(Area)", self.target_reso.get()])
                    writer.writerow(["버킷 크기 단위",  self.bucket_reso_steps.get()])
                    writer.writerow(["최소 버킷 크기",  self.min_bucket_reso.get()])
                    writer.writerow(["최대 버킷 크기",  self.max_bucket_reso.get()])
                else:
                    writer.writerow(["버킷 설정", "기본값 (1024 Area / 64 steps)"])
                
                writer.writerow([])
                writer.writerow(["폴더 이름", "원본 수", "추천 리핏", "설정 리핏",
                                  "처리량(이론)", "처리량(실제)", "이론적 스텝", "스텝(실제)",
                                  "낭비율(%)", "버킷 종류(수)", "버킷 분포 상세", "폴더 경로"])
                for r in self.results:
                    buckets_detail = ", ".join([f"{k}:{v}" for k, v in sorted(r['buckets'].items())])
                    theo_ops   = r['count'] * r['repeat']
                    actual_ops = r['steps'] * batch_total
                    writer.writerow([
                        r['folder_name'], r['count'], r['recommend'], r['repeat'],
                        theo_ops, actual_ops,
                        r['theoretical_steps'], r['steps'],
                        f"{r['waste_rate']:.2f}",
                        len(r['buckets']), buckets_detail, r['folder_path']
                    ])
            messagebox.showinfo("완료", f"분석 결과가 다음 경로에 저장되었습니다:\n{file_path}")
        except Exception as e:
            messagebox.showerror("오류", f"파일 저장 중 오류가 발생했습니다: {e}")

    # ── 스냅샷 창 열기 ────────────────────────────────────────
    def show_snapshot_window(self):
        """데이터셋 스냅샷 관리 창을 엽니다."""
        SnapshotWindow(self.parent, self)

    def get_active_root_path(self) -> str:
        """현재 활성화된 분석 루트 경로를 반환합니다."""
        if self.use_independent_path.get():
            return self.independent_folder_path.get()
        return self.folder_path_var.get()


# ═══════════════════════════════════════════════════════════════
# 스냅샷 저장 다이얼로그
# ═══════════════════════════════════════════════════════════════

class SaveSnapshotDialog:
    """스냅샷 이름과 메모를 입력받는 간단한 다이얼로그."""

    def __init__(self, parent):
        self.confirmed = False
        self.name = ''
        self.memo = ''

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("스냅샷 저장")
        self.dialog.resizable(False, False)
        self.dialog.grab_set()

        frame = ttk.Frame(self.dialog, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # 이름 입력
        ttk.Label(frame, text="스냅샷 이름:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.name_entry = ttk.Entry(frame, width=38)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=(0, 5))

        import datetime
        self.name_entry.insert(0, datetime.datetime.now().strftime("%Y-%m-%d"))
        self.name_entry.selection_range(0, tk.END)
        self.name_entry.focus_set()

        # 메모 입력
        ttk.Label(frame, text="메모 (선택):").grid(row=1, column=0, sticky=tk.NW, pady=(0, 5))
        self.memo_text = tk.Text(frame, width=38, height=4, relief=tk.SOLID, borderwidth=1)
        self.memo_text.grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=(0, 5))

        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frame, text="저장",  command=self._ok,     width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="취소",  command=self._cancel, width=10).pack(side=tk.LEFT, padx=5)

        self.dialog.bind('<Return>', lambda e: self._ok())
        self.dialog.bind('<Escape>', lambda e: self._cancel())

        # 창 크기 및 중앙 배치
        self.dialog.update_idletasks()
        w, h = self.dialog.winfo_width(), self.dialog.winfo_height()
        px = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.dialog.geometry(f"+{max(0, px)}+{max(0, py)}")

    def _ok(self):
        self.name = self.name_entry.get().strip()
        self.memo = self.memo_text.get('1.0', tk.END).strip()
        self.confirmed = True
        self.dialog.destroy()

    def _cancel(self):
        self.dialog.destroy()


# ═══════════════════════════════════════════════════════════════
# 스냅샷 불러오기 다이얼로그
# ═══════════════════════════════════════════════════════════════

class LoadSnapshotDialog:
    """저장된 스냅샷을 드롭다운 또는 파일 탐색기로 선택하는 다이얼로그."""

    def __init__(self, parent):
        self.confirmed = False
        self.selected_path = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("스냅샷 불러오기")
        self.dialog.resizable(False, False)
        self.dialog.grab_set()

        frame = ttk.Frame(self.dialog, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # 저장된 스냅샷 목록 드롭다운
        snapshots = DatasetSnapshot.list_snapshots()
        self._path_map = {name: path for name, path in snapshots}
        snap_names = list(self._path_map.keys())

        ttk.Label(frame, text="저장된 스냅샷:").grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        self.combo_var = tk.StringVar()
        self.combo = ttk.Combobox(frame, textvariable=self.combo_var,
                                  values=snap_names, width=52, state='readonly')
        self.combo.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=(0, 8))
        if snap_names:
            self.combo.current(0)

        # 직접 파일 선택
        ttk.Label(frame, text="직접 선택:").grid(row=1, column=0, sticky=tk.W, pady=(0, 8))
        browse_inner = ttk.Frame(frame)
        browse_inner.grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=(0, 8))
        browse_inner.columnconfigure(0, weight=1)

        self.file_var = tk.StringVar()
        ttk.Entry(browse_inner, textvariable=self.file_var, width=42).grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(browse_inner, text="찾아보기", command=self._browse, width=8).grid(row=0, column=1, padx=(5, 0))

        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frame, text="불러오기", command=self._ok,     width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="취소",     command=self._cancel, width=10).pack(side=tk.LEFT, padx=5)

        self.dialog.bind('<Return>', lambda e: self._ok())
        self.dialog.bind('<Escape>', lambda e: self._cancel())

        # 중앙 배치
        self.dialog.update_idletasks()
        w, h = self.dialog.winfo_width(), self.dialog.winfo_height()
        px = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.dialog.geometry(f"+{max(0, px)}+{max(0, py)}")

    def _browse(self):
        init_dir = str(DatasetSnapshot.get_snapshot_dir())
        path = filedialog.askopenfilename(
            title="스냅샷 파일 선택",
            filetypes=[("JSON 스냅샷", "*.json"), ("모든 파일", "*.*")],
            initialdir=init_dir if os.path.exists(init_dir) else None,
            parent=self.dialog
        )
        if path:
            self.file_var.set(path)

    def _ok(self):
        # 직접 선택한 파일이 있으면 우선
        file_path = self.file_var.get().strip()
        if file_path and os.path.isfile(file_path):
            self.selected_path = file_path
            self.confirmed = True
            self.dialog.destroy()
            return

        # 드롭다운 선택
        selected = self.combo_var.get()
        if selected in self._path_map and os.path.isfile(self._path_map[selected]):
            self.selected_path = self._path_map[selected]
            self.confirmed = True
            self.dialog.destroy()
            return

        messagebox.showwarning("경고", "불러올 스냅샷을 선택해주세요.", parent=self.dialog)

    def _cancel(self):
        self.dialog.destroy()


# ═══════════════════════════════════════════════════════════════
# 데이터셋 스냅샷 관리 창
# ═══════════════════════════════════════════════════════════════

class SnapshotWindow:
    """
    데이터셋 스냅샷 관리 창.
    - 현재 상태 저장 / 기본 스냅샷 불러오기 / 비교 스냅샷 불러오기 / 비교하기
    - 탭 구조: [기본 스냅샷] [비교 스냅샷] [차이점 분석]
    """

    def __init__(self, parent, analyzer_gui: DatasetAnalyzerGUI):
        self.analyzer_gui  = analyzer_gui
        self.base_snapshot = None
        self.comp_snapshot = None

        self.win = tk.Toplevel(parent)
        self.win.title("데이터셋 스냅샷 관리")
        self.win.geometry("1100x720")
        self.win.minsize(900, 600)

        self._build_ui()

    # ── UI 구성 ───────────────────────────────────────────────
    def _build_ui(self):
        # ─ 상단 액션 버튼 바 ─────────────────────────────────
        top_bar = ttk.Frame(self.win, padding="8 8 8 4")
        top_bar.pack(fill=tk.X)

        ttk.Button(top_bar, text="현재 상태 저장",        command=self.cmd_save,      width=16).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_bar, text="기본 스냅샷 불러오기",   command=self.cmd_load_base, width=18).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_bar, text="비교 스냅샷 불러오기",   command=self.cmd_load_comp, width=18).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_bar, text="비교하기",               command=self.cmd_compare,   width=10).pack(side=tk.LEFT, padx=3)

        # ─ 상태 표시 줄 ──────────────────────────────────────
        status_bar = ttk.Frame(self.win, padding="8 0 8 6")
        status_bar.pack(fill=tk.X)
        ttk.Separator(status_bar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 4))

        inner = ttk.Frame(status_bar)
        inner.pack(fill=tk.X)
        ttk.Label(inner, text="기본:").pack(side=tk.LEFT)
        self.base_status_var = tk.StringVar(value="(없음)")
        ttk.Label(inner, textvariable=self.base_status_var, foreground="navy").pack(side=tk.LEFT, padx=(3, 20))
        ttk.Label(inner, text="비교:").pack(side=tk.LEFT)
        self.comp_status_var = tk.StringVar(value="(없음)")
        ttk.Label(inner, textvariable=self.comp_status_var, foreground="dark green").pack(side=tk.LEFT, padx=3)

        # ─ 메인 노트북 ───────────────────────────────────────
        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 탭 1, 2: 스냅샷 정보 탭
        self.base_tab = ttk.Frame(self.notebook)
        self.comp_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.base_tab, text="기본 스냅샷")
        self.notebook.add(self.comp_tab, text="비교 스냅샷")
        self._build_snapshot_tab(self.base_tab, 'base')
        self._build_snapshot_tab(self.comp_tab, 'comp')

        # 탭 3: 차이점 분석
        self.diff_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.diff_tab, text="차이점 분석")
        self._build_diff_tab()

    # ── 스냅샷 정보 탭 구성 ───────────────────────────────────
    def _build_snapshot_tab(self, parent: ttk.Frame, which: str):
        # 정보 헤더
        info_lf = ttk.LabelFrame(parent, text="스냅샷 정보", padding="10")
        info_lf.pack(fill=tk.X, padx=10, pady=(8, 4))
        info_lf.columnconfigure(1, weight=1)
        info_lf.columnconfigure(3, weight=1)

        # 각 정보 변수
        name_var     = tk.StringVar(value="-")
        date_var     = tk.StringVar(value="-")
        root_var     = tk.StringVar(value="-")
        img_var      = tk.StringVar(value="-")
        pair_var     = tk.StringVar(value="-")
        sz_var       = tk.StringVar(value="-")
        folder_var   = tk.StringVar(value="-")
        memo_var     = tk.StringVar(value="-")

        def lbl(text, row, col, **kw):
            kw.setdefault('padx', (0, 4))
            ttk.Label(info_lf, text=text).grid(row=row, column=col, sticky=tk.W, **kw)
        def val(var, row, col, **kw):
            ttk.Label(info_lf, textvariable=var).grid(row=row, column=col, sticky=tk.W, **kw)

        lbl("이름:",        0, 0);  ttk.Label(info_lf, textvariable=name_var, font=('', 10, 'bold')).grid(row=0, column=1, sticky=tk.W)
        lbl("날짜:",        0, 2, padx=(20, 4));  val(date_var,   0, 3)
        lbl("루트 폴더:",   1, 0, pady=(4, 0));   ttk.Label(info_lf, textvariable=root_var, foreground="gray40").grid(row=1, column=1, columnspan=3, sticky=tk.W, pady=(4, 0))
        lbl("총 이미지:",   2, 0, pady=(4, 0));   val(img_var,    2, 1, pady=(4, 0))
        lbl("총 짝(pair):", 2, 2, padx=(20, 4), pady=(4, 0));  val(pair_var,   2, 3, pady=(4, 0))
        lbl("총 용량:",     3, 0, pady=(4, 0));   val(sz_var,     3, 1, pady=(4, 0))
        lbl("폴더 수:",     3, 2, padx=(20, 4), pady=(4, 0));  val(folder_var, 3, 3, pady=(4, 0))
        lbl("메모:",        4, 0, pady=(4, 0));
        ttk.Label(info_lf, textvariable=memo_var, wraplength=650, justify=tk.LEFT).grid(row=4, column=1, columnspan=3, sticky=tk.W, pady=(4, 0))

        # 변수 보관
        vars_dict = {
            'name': name_var, 'date': date_var, 'root': root_var,
            'img':  img_var,  'pair': pair_var, 'sz':   sz_var,
            'folder_cnt': folder_var, 'memo': memo_var
        }
        if which == 'base':
            self.base_vars = vars_dict
        else:
            self.comp_vars = vars_dict

        # 폴더 테이블
        table_lf = ttk.LabelFrame(parent, text="최하위 폴더별 상세", padding="5")
        table_lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 8))

        cols = ("rel_path", "image_count", "pair_count", "unpaired", "size")
        tree = ttk.Treeview(table_lf, columns=cols, show="headings", height=12)
        tree.heading("rel_path",     text="폴더 경로 (루트 기준 상대)")
        tree.heading("image_count",  text="이미지")
        tree.heading("pair_count",   text="짝(pair)")
        tree.heading("unpaired",     text="미짝")
        tree.heading("size",         text="용량")

        tree.column("rel_path",    width=380)
        tree.column("image_count", width=80,  anchor=tk.CENTER)
        tree.column("pair_count",  width=80,  anchor=tk.CENTER)
        tree.column("unpaired",    width=60,  anchor=tk.CENTER)
        tree.column("size",        width=110, anchor=tk.E)

        sb = ttk.Scrollbar(table_lf, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        if which == 'base':
            self.base_tree = tree
        else:
            self.comp_tree = tree

    # ── 차이점 분석 탭 구성 ───────────────────────────────────
    def _build_diff_tab(self):
        # 요약 섹션
        self.diff_summary_lf = ttk.LabelFrame(self.diff_tab, text="비교 요약", padding="10")
        self.diff_summary_lf.pack(fill=tk.X, padx=10, pady=(8, 4))
        self.diff_summary_label = ttk.Label(
            self.diff_summary_lf,
            text="기본 스냅샷과 비교 스냅샷을 모두 불러온 뒤 '비교하기' 버튼을 눌러주세요.",
            justify=tk.LEFT
        )
        self.diff_summary_label.pack(fill=tk.X)

        # 서브 노트북 (4개 탭)
        self.diff_nb = ttk.Notebook(self.diff_tab)
        self.diff_nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 8))

        self._build_diff_subtab('added',   "신규 추가 폴더")
        self._build_diff_subtab('removed', "삭제된 폴더")
        self._build_diff_subtab('changed', "변경된 폴더")
        self._build_diff_subtab('fuzzy',   "이동 / 재구성")

    def _build_diff_subtab(self, kind: str, title: str):
        frame = ttk.Frame(self.diff_nb)
        self.diff_nb.add(frame, text=title)

        if kind in ('added', 'removed'):
            cols = ("path", "image_count", "pair_count", "size")
            tree = ttk.Treeview(frame, columns=cols, show="headings")
            tree.heading("path",        text="폴더 경로")
            tree.heading("image_count", text="이미지")
            tree.heading("pair_count",  text="짝")
            tree.heading("size",        text="용량")
            tree.column("path",        width=450)
            tree.column("image_count", width=90, anchor=tk.CENTER)
            tree.column("pair_count",  width=90, anchor=tk.CENTER)
            tree.column("size",        width=120, anchor=tk.E)

        elif kind == 'changed':
            cols = ("path", "base_img", "comp_img", "delta_img", "delta_size")
            tree = ttk.Treeview(frame, columns=cols, show="headings")
            tree.heading("path",      text="폴더 경로")
            tree.heading("base_img",  text="기본(이미지)")
            tree.heading("comp_img",  text="비교(이미지)")
            tree.heading("delta_img", text="증감(장)")
            tree.heading("delta_size",text="증감(용량)")
            tree.column("path",       width=320)
            tree.column("base_img",   width=100, anchor=tk.CENTER)
            tree.column("comp_img",   width=100, anchor=tk.CENTER)
            tree.column("delta_img",  width=90,  anchor=tk.CENTER)
            tree.column("delta_size", width=140, anchor=tk.CENTER)

        elif kind == 'fuzzy':
            cols = ("base_path", "comp_path", "delta_img", "delta_size")
            tree = ttk.Treeview(frame, columns=cols, show="headings")
            tree.heading("base_path",  text="기본 경로 (이전)")
            tree.heading("comp_path",  text="비교 경로 (이후/이동)")
            tree.heading("delta_img",  text="증감(장)")
            tree.heading("delta_size", text="증감(용량)")
            tree.column("base_path",  width=310)
            tree.column("comp_path",  width=310)
            tree.column("delta_img",  width=90,  anchor=tk.CENTER)
            tree.column("delta_size", width=140, anchor=tk.CENTER)

        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 5))

        setattr(self, f"diff_{kind}_tree", tree)

    # ── 커맨드 핸들러 ─────────────────────────────────────────
    def cmd_save(self):
        """현재 폴더 상태를 수집하여 스냅샷으로 저장합니다."""
        root_path = self.analyzer_gui.get_active_root_path()
        if not root_path or not os.path.exists(root_path):
            messagebox.showwarning("경고", "유효한 폴더 경로를 먼저 설정해주세요.", parent=self.win)
            return

        dlg = SaveSnapshotDialog(self.win)
        self.win.wait_window(dlg.dialog)
        if not dlg.confirmed:
            return

        name = dlg.name
        memo = dlg.memo
        if not name:
            messagebox.showwarning("경고", "스냅샷 이름을 입력해주세요.", parent=self.win)
            return

        try:
            data = DatasetSnapshot.collect(root_path)
            if data is None:
                messagebox.showerror("오류", "폴더 정보를 수집할 수 없습니다.", parent=self.win)
                return

            filepath = DatasetSnapshot.save(data, name, memo)
            messagebox.showinfo("저장 완료", f"스냅샷이 저장되었습니다.\n\n{filepath}", parent=self.win)

            # 저장 후 기본 스냅샷으로 자동 로드
            self.base_snapshot = DatasetSnapshot.load(str(filepath))
            self._display_snapshot(self.base_snapshot, 'base')
            self.base_status_var.set(f"{name}  ({data['created_at'][:10]})")
            self.notebook.select(0)

        except Exception as e:
            messagebox.showerror("오류", f"스냅샷 저장 중 오류가 발생했습니다:\n{e}", parent=self.win)

    def cmd_load_base(self):
        """기본(Base) 스냅샷을 불러옵니다."""
        path = self._pick_snapshot()
        if not path:
            return
        try:
            self.base_snapshot = DatasetSnapshot.load(path)
            self._display_snapshot(self.base_snapshot, 'base')
            self.base_status_var.set(
                f"{self.base_snapshot.get('name', '?')}  "
                f"({self.base_snapshot.get('created_at', '')[:10]})"
            )
            self.notebook.select(0)
        except Exception as e:
            messagebox.showerror("오류", f"스냅샷 불러오기 실패:\n{e}", parent=self.win)

    def cmd_load_comp(self):
        """비교(Comparison) 스냅샷을 불러옵니다."""
        path = self._pick_snapshot()
        if not path:
            return
        try:
            self.comp_snapshot = DatasetSnapshot.load(path)
            self._display_snapshot(self.comp_snapshot, 'comp')
            self.comp_status_var.set(
                f"{self.comp_snapshot.get('name', '?')}  "
                f"({self.comp_snapshot.get('created_at', '')[:10]})"
            )
            self.notebook.select(1)
        except Exception as e:
            messagebox.showerror("오류", f"스냅샷 불러오기 실패:\n{e}", parent=self.win)

    def cmd_compare(self):
        """두 스냅샷을 비교하고 결과를 차이점 탭에 표시합니다."""
        if not self.base_snapshot or not self.comp_snapshot:
            messagebox.showwarning(
                "경고",
                "기본 스냅샷과 비교 스냅샷을 모두 불러와야 합니다.",
                parent=self.win
            )
            return
        try:
            diff = DatasetSnapshot.compare(self.base_snapshot, self.comp_snapshot)
            self._display_diff(diff)
            self.notebook.select(2)
        except Exception as e:
            messagebox.showerror("오류", f"비교 중 오류가 발생했습니다:\n{e}", parent=self.win)

    # ── 내부 헬퍼 ─────────────────────────────────────────────
    def _pick_snapshot(self):
        """불러오기 다이얼로그를 표시하고 선택된 경로를 반환합니다."""
        dlg = LoadSnapshotDialog(self.win)
        self.win.wait_window(dlg.dialog)
        return dlg.selected_path if dlg.confirmed else None

    def _display_snapshot(self, data: dict, which: str):
        """스냅샷 데이터를 해당 탭의 정보 영역과 테이블에 표시합니다."""
        v    = self.base_vars if which == 'base' else self.comp_vars
        tree = self.base_tree if which == 'base' else self.comp_tree

        dt = data.get('created_at', '')[:19].replace('T', ' ')
        v['name'].set(data.get('name', '-'))
        v['date'].set(dt)
        v['root'].set(data.get('root_path', '-'))
        v['img'].set(f"{data.get('total_images', 0):,} 장")
        v['pair'].set(f"{data.get('total_pairs', 0):,} 쌍  (미짝: {data.get('total_unpaired', 0):,})")
        v['sz'].set(DatasetSnapshot.format_size(data.get('total_size_bytes', 0)))
        v['folder_cnt'].set(f"{data.get('leaf_folder_count', 0)} 개")
        v['memo'].set(data.get('memo', '') or '-')

        tree.delete(*tree.get_children())
        for folder in data.get('leaf_folders', []):
            tree.insert("", tk.END, values=(
                folder['rel_path'],
                f"{folder['image_count']:,}",
                f"{folder['pair_count']:,}",
                folder['unpaired'],
                DatasetSnapshot.format_size(folder['size_bytes'])
            ))

    def _display_diff(self, diff: dict):
        """비교 결과를 차이점 분석 탭에 표시합니다."""
        s = diff['summary']
        fmt = DatasetSnapshot.format_size

        # ── 요약 텍스트 ─────────────────────────────────
        di   = s['delta_images']
        dsz  = s['delta_size']
        si   = '+' if di  >= 0 else ''
        ssz  = '+' if dsz >= 0 else ''
        trend_img = '▲' if di  >= 0 else '▼'
        trend_sz  = '▲' if dsz >= 0 else '▼'

        summary_lines = [
            f"이미지 증감:  {trend_img} {si}{di:,} 장  ({si}{s['rate_images']:.1f}%)     "
            f"용량 증감:  {trend_sz} {fmt(abs(dsz))} ({ssz}{s['rate_size']:.1f}%)",
            f"신규 폴더: {s['added_count']}개   삭제 폴더: {s['removed_count']}개   "
            f"변경된 폴더: {s['changed_count']}개   이동/재구성: {s['fuzzy_count']}개   "
            f"변경 없음: {s['unchanged_count']}개",
        ]
        self.diff_summary_label.config(text="\n".join(summary_lines))

        # ── 서브탭 제목에 건수 반영 ───────────────────────
        self.diff_nb.tab(0, text=f"신규 추가 폴더 ({s['added_count']})")
        self.diff_nb.tab(1, text=f"삭제된 폴더 ({s['removed_count']})")
        self.diff_nb.tab(2, text=f"변경된 폴더 ({s['changed_count']})")
        self.diff_nb.tab(3, text=f"이동/재구성 ({s['fuzzy_count']})")

        # ── 각 트리 초기화 및 채우기 ─────────────────────
        for kind in ('added', 'removed', 'changed', 'fuzzy'):
            getattr(self, f"diff_{kind}_tree").delete(
                *getattr(self, f"diff_{kind}_tree").get_children()
            )

        # Added
        for item in diff['added']:
            self.diff_added_tree.insert("", tk.END, values=(
                item['path'],
                f"{item['image_count']:,}",
                f"{item['pair_count']:,}",
                fmt(item['size_bytes'])
            ))

        # Removed
        for item in diff['removed']:
            self.diff_removed_tree.insert("", tk.END, values=(
                item['path'],
                f"{item['image_count']:,}",
                f"{item['pair_count']:,}",
                fmt(item['size_bytes'])
            ))

        # Changed
        for item in diff['changed']:
            d_i  = item['delta_images']
            d_sz = item['delta_size']
            si   = '+' if d_i  >= 0 else ''
            ssz  = '+' if d_sz >= 0 else ''
            self.diff_changed_tree.insert("", tk.END, values=(
                item['path'],
                f"{item['base']['image_count']:,}",
                f"{item['comp']['image_count']:,}",
                f"{si}{d_i:,}",
                f"{ssz}{fmt(abs(d_sz))} ({'▲' if d_sz >= 0 else '▼'})"
            ))

        # Fuzzy (이동/재구성)
        for item in diff['fuzzy_matched']:
            d_i  = item['delta_images']
            d_sz = item['delta_size']
            si   = '+' if d_i  >= 0 else ''
            ssz  = '+' if d_sz >= 0 else ''
            self.diff_fuzzy_tree.insert("", tk.END, values=(
                item['base_path'],
                item['comp_path'],
                f"{si}{d_i:,}",
                f"{ssz}{fmt(abs(d_sz))} ({'▲' if d_sz >= 0 else '▼'})"
            ))
