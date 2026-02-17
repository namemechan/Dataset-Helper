import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import csv
from pathlib import Path
from dataset_analyzer import DatasetAnalyzer
from utils import ScrollableFrame

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
        self.target_reso = tk.IntVar(value=1024) # kohya-ss의 --resolution 개념
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
        self.export_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Button(btn_frame, text="리핏 일괄 0", command=lambda: self.set_all_repeats(0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="리핏 일괄 1", command=lambda: self.set_all_repeats(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="최적 리핏 설정", command=self.set_optimal_repeats).pack(side=tk.LEFT, padx=2)

        # 3. 요약 정보 영역
        self.summary_frame = ttk.LabelFrame(container, text="요약 결과", padding="10")
        self.summary_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.summary_label = ttk.Label(self.summary_frame, text="검색을 진행해주세요.", justify=tk.LEFT)
        self.summary_label.pack(fill=tk.X)
        
        # 4. 결과 테이블 영역 (Treeview)
        table_frame = ttk.Frame(container, padding="5")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        cols = ("folder", "count", "buckets", "recommend", "repeat", "waste", "steps")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=15)
        
        self.tree.heading("folder", text="폴더 이름", command=lambda: self.treeview_sort_column("folder", False))
        self.tree.heading("count", text="데이터셋 수", command=lambda: self.treeview_sort_column("count", True))
        self.tree.heading("buckets", text="버킷 분포 (종류)")
        self.tree.heading("recommend", text="추천 리핏")
        self.tree.heading("repeat", text="설정 리핏")
        self.tree.heading("waste", text="예상 낭비율", command=lambda: self.treeview_sort_column("waste", True))
        self.tree.heading("steps", text="예상 스텝 (이론/실제)")
        
        self.tree.column("folder", width=180)
        self.tree.column("count", width=100, anchor=tk.CENTER)
        self.tree.column("buckets", width=250)
        self.tree.column("recommend", width=80, anchor=tk.CENTER)
        self.tree.column("repeat", width=80, anchor=tk.CENTER)
        self.tree.column("waste", width=100, anchor=tk.CENTER)
        self.tree.column("steps", width=150, anchor=tk.CENTER)
        
        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        
        self.toggle_path_ui()
        self.toggle_bucket_ui()

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
        
        # 라벨 색상 변경으로 시인성 확보 (선택사항)
        label_color = "black" if self.use_custom_buckets.get() else "gray"
        self.target_reso_label.config(foreground=label_color)
        self.bucket_steps_label.config(foreground=label_color)
        self.min_bucket_label.config(foreground=label_color)
        self.max_bucket_label.config(foreground=label_color)

    def select_folder(self):
        f = filedialog.askdirectory()
        if f: self.independent_folder_path.set(f)

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
                    'target_res': self.target_reso.get(),
                    'bucket_steps': self.bucket_reso_steps.get(),
                    'bucket_min': self.min_bucket_reso.get(),
                    'bucket_max': self.max_bucket_reso.get()
                }
                
            raw_results = DatasetAnalyzer.scan_directories(
                path, self.recursive.get(), self.include_empty.get(), self.include_untagged.get(), 
                num_cores, bucket_settings
            )
            self.parent.after(0, lambda: self.finish_search(raw_results))
        threading.Thread(target=run, daemon=True).start()

    def finish_search(self, raw_results):
        self.results = raw_results
        total_data = sum(r['count'] for r in self.results)
        self.avg_data = total_data / len(self.results) if self.results else 0
        batch_total = self.batch_size.get() * self.grad_acc.get()
        for r in self.results:
            r['recommend'] = DatasetAnalyzer.calculate_recommend_repeat(r['count'], self.avg_data, batch_total)
            r['repeat'] = 1
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()
        self.search_btn.config(state=tk.NORMAL)
        self.analyze_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)

    def update_table(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.results:
            marker = "▲" if r['count'] >= self.avg_data else "▼"
            count_str = f"{marker} {r['count']}개"
            bucket_types = len(r['buckets'])
            buckets_str = f"[{bucket_types}종] " + ", ".join([f"{k}:{v}" for k, v in sorted(r['buckets'].items())])
            steps_display = f"{r['theoretical_steps']:.1f} / {r['steps']}"
            self.tree.insert("", tk.END, values=(
                r['folder_name'], count_str, buckets_str, r['recommend'], r['repeat'],
                f"{r['waste_rate']:.2f}%", steps_display
            ), tags=(r['folder_path'],))
        if self.current_sort[0]: self._apply_sort()

    def update_summary(self):
        if not self.results:
            self.summary_label.config(text="검색 결과가 없습니다.")
            return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        epochs = self.epochs.get()
        total_folders = len(self.results)
        total_data = sum(r['count'] for r in self.results)
        total_steps_per_epoch = sum(r['steps'] for r in self.results)
        total_steps = total_steps_per_epoch * epochs
        total_theo_steps_per_epoch = sum(r['theoretical_steps'] for r in self.results)
        total_theo_steps = total_theo_steps_per_epoch * epochs
        total_waste_slots = 0
        total_slots = 0
        for r in self.results:
            w_slots, _, steps = DatasetAnalyzer.calculate_waste(r['buckets'], r['repeat'], batch_total)
            total_waste_slots += w_slots
            total_slots += steps * batch_total
        avg_waste_rate = (total_waste_slots / total_slots * 100) if total_slots > 0 else 0
        summary_text = (f"최종 배치(배치*그라디언트): {batch_total} | 총 폴더: {total_folders}개 | 총 데이터셋: {total_data}개 | 폴더당 평균: {self.avg_data:.1f}개\n"
                        f"이론적 스텝 (1에포크): {total_theo_steps_per_epoch:.1f} | 이론적 총 스텝 ({epochs}에포크): {total_theo_steps:.1f}\n"
                        f"실제 예상 스텝 (1에포크): {total_steps_per_epoch} | 실제 예상 총 스텝 ({epochs}에포크): {total_steps} | 평균 배치 슬롯 낭비율: {avg_waste_rate:.2f}%")
        self.summary_label.config(text=summary_text)

    def export_to_csv(self):
        if not self.results: return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not file_path: return
        try:
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["[데이터셋 분석 요약 결과]"])
                batch_total = self.batch_size.get() * self.grad_acc.get()
                writer.writerow(["최종 배치", batch_total])
                writer.writerow(["총 폴더 수", len(self.results)])
                writer.writerow(["총 데이터셋 수", sum(r['count'] for r in self.results)])
                writer.writerow(["폴더당 평균 데이터셋", f"{self.avg_data:.2f}"])
                
                # 버킷 설정 정보 추가
                if self.use_custom_buckets.get():
                    writer.writerow(["버킷 설정", "사용자 정의 (kohya-ss 스타일)"])
                    writer.writerow(["기준 해상도(Area)", self.target_reso.get()])
                    writer.writerow(["버킷 크기 단위", self.bucket_reso_steps.get()])
                    writer.writerow(["최소 버킷 크기", self.min_bucket_reso.get()])
                    writer.writerow(["최대 버킷 크기", self.max_bucket_reso.get()])
                else:
                    writer.writerow(["버킷 설정", "기본값 (1024 Area / 64 steps)"])
                
                writer.writerow([])
                # 버킷 종류(수) 헤더 추가
                writer.writerow(["폴더 이름", "데이터셋 수", "추천 리핏", "설정 리핏", "예상 낭비율(%)", "이론적 스텝", "실제 예상 스텝", "버킷 종류(수)", "버킷 분포 상세", "폴더 경로"])
                for r in self.results:
                    buckets_detail = ", ".join([f"{k}:{v}" for k, v in sorted(r['buckets'].items())])
                    # 버킷 종류 수(len(r['buckets'])) 데이터 추가
                    writer.writerow([
                        r['folder_name'], r['count'], r['recommend'], r['repeat'],
                        f"{r['waste_rate']:.2f}", r['theoretical_steps'], r['steps'],
                        len(r['buckets']), buckets_detail, r['folder_path']
                    ])
            messagebox.showinfo("완료", f"분석 결과가 다음 경로에 저장되었습니다:\n{file_path}")
        except Exception as e:
            messagebox.showerror("오류", f"파일 저장 중 오류가 발생했습니다: {e}")

    def on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
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
        r['waste_rate'] = waste_rate
        r['steps'] = steps
        r['theoretical_steps'] = DatasetAnalyzer.calculate_theoretical_steps(r['count'], r['repeat'], batch_total)

    def set_all_repeats(self, val):
        if not self.results: return
        for r in self.results:
            r['repeat'] = val
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()

    def set_optimal_repeats(self):
        if not self.results: return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        for r in self.results:
            if r['count'] >= self.avg_data: r['repeat'] = r['recommend']
            else: r['repeat'] = batch_total
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()

    def update_analysis(self):
        batch_total = self.batch_size.get() * self.grad_acc.get()
        
        # 버킷 설정 가져오기
        if self.use_custom_buckets.get():
            b_target = self.target_reso.get()
            b_steps = self.bucket_reso_steps.get()
            b_min = self.min_bucket_reso.get()
            b_max = self.max_bucket_reso.get()
        else:
            b_target, b_steps, b_min, b_max = 1024, 64, 256, 2048

        total_data = sum(r['count'] for r in self.results)
        self.avg_data = total_data / len(self.results) if self.results else 0
        
        for r in self.results:
            # 원본 차원 정보가 있으면 현재 설정으로 버킷 재계산
            if 'image_dims' in r and r['image_dims']:
                r['buckets'] = DatasetAnalyzer.rebucketize(r['image_dims'], b_steps, b_min, b_max, b_target)
                
            r['recommend'] = DatasetAnalyzer.calculate_recommend_repeat(r['count'], self.avg_data, batch_total)
            self._recalculate_folder(r)
            
        self.update_table()
        self.update_summary()
