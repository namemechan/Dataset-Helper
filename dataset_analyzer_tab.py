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
        self.export_btn.pack(side=tk.LEFT, padx=2)
        
        self.mismatch_btn = ttk.Button(btn_frame, text="버킷 미스 매치", command=self.show_mismatch_window, state=tk.DISABLED)
        self.mismatch_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Button(btn_frame, text="리핏 일괄 설정", command=self.ask_all_repeats).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="추천 리핏 설정", command=self.set_recommended_repeats).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="최적 리핏 설정", command=self.set_optimal_repeats).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="균등 리핏 설정", command=self.set_averaged_repeats).pack(side=tk.LEFT, padx=2)

        # 3. 요약 정보 영역
        self.summary_frame = ttk.LabelFrame(container, text="요약 결과", padding="10")
        self.summary_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.summary_label = ttk.Label(self.summary_frame, text="검색을 진행해주세요.", justify=tk.LEFT)
        self.summary_label.pack(fill=tk.X)
        
        # 4. 결과 테이블 영역 (Treeview)
        table_frame = ttk.Frame(container, padding="5")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        cols = ("folder", "count", "buckets", "recommend", "repeat", "total_ops", "steps", "waste")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=15)
        
        self.tree.heading("folder", text="폴더 이름", command=lambda: self.treeview_sort_column("folder", False))
        self.tree.heading("count", text="원본 수", command=lambda: self.treeview_sort_column("count", True))
        self.tree.heading("buckets", text="버킷(종류)")
        self.tree.heading("recommend", text="추천 리핏")
        self.tree.heading("repeat", text="설정 리핏")
        self.tree.heading("total_ops", text="처리량(이론/실제)")
        self.tree.heading("steps", text="스텝(이론/실제)")
        self.tree.heading("waste", text="낭비율", command=lambda: self.treeview_sort_column("waste", True))
        
        self.tree.column("folder", width=180)
        self.tree.column("count", width=80, anchor=tk.CENTER)
        self.tree.column("buckets", width=220)
        self.tree.column("recommend", width=80, anchor=tk.CENTER)
        self.tree.column("repeat", width=80, anchor=tk.CENTER)
        self.tree.column("total_ops", width=150, anchor=tk.CENTER)
        self.tree.column("steps", width=150, anchor=tk.CENTER)
        self.tree.column("waste", width=80, anchor=tk.CENTER)
        
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
        
        for r in self.results:
            r['repeat'] = 1
            
        self._update_recommend_column()
        self.update_table()
        self.update_summary()
        self.search_btn.config(state=tk.NORMAL)
        self.analyze_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        
        # 미스매치 데이터 확인 및 버튼 활성화
        total_mismatches = sum(len(r.get('mismatches', [])) for r in self.results)
        if total_mismatches > 0:
            self.mismatch_btn.config(state=tk.NORMAL)
        else:
            self.mismatch_btn.config(state=tk.DISABLED)

    def _update_recommend_column(self):
        """표의 '추천 리핏' 열을 C+B 방식으로 업데이트"""
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
            
            # 총 연산량 (이론/실제) 계산
            theo_ops = r['count'] * r['repeat']
            actual_ops = r['steps'] * batch_total
            ops_display = f"{theo_ops} / {actual_ops}"
            
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
        
        # 미스매치 건수 합산
        total_mismatches = sum(len(r.get('mismatches', [])) for r in self.results)
        mismatch_text = f"⚠️ 비율 미스매치 감지: {total_mismatches}건\n" if total_mismatches > 0 else ""

        summary_text = (f"{mismatch_text}"
                        f"최종 배치(배치*그라디언트): {batch_total} | 총 폴더: {total_folders}개 | 총 데이터셋: {total_data}개 | 폴더당 평균: {self.avg_data:.1f}개\n"
                        f"이론적 스텝 (1에포크): {total_theo_steps_per_epoch:.1f} | 이론적 총 스텝 ({epochs}에포크): {total_theo_steps:.1f}\n"
                        f"실제 예상 스텝 (1에포크): {total_steps_per_epoch} | 실제 예상 총 스텝 ({epochs}에포크): {total_steps} | 평균 배치 슬롯 낭비율: {avg_waste_rate:.2f}%")
        self.summary_label.config(text=summary_text)

    def show_mismatch_window(self):
        """미스매치 상세 목록을 보여주는 팝업 창"""
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
        tree.heading("file", text="파일명")
        tree.heading("res", text="원본 해상도")
        tree.heading("orig_ar", text="원본 AR")
        tree.heading("bucket_ar", text="버킷 AR")
        tree.heading("bucket_res", text="배정 버킷")
        tree.heading("path", text="폴더 경로")
        
        tree.column("file", width=150)
        tree.column("res", width=100, anchor=tk.CENTER)
        tree.column("orig_ar", width=80, anchor=tk.CENTER)
        tree.column("bucket_ar", width=80, anchor=tk.CENTER)
        tree.column("bucket_res", width=100, anchor=tk.CENTER)
        tree.column("path", width=300)
        
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
                writer.writerow(["폴더 이름", "원본 수", "추천 리핏", "설정 리핏", "처리량(이론)", "처리량(실제)", "이론적 스텝", "스텝(실제)", "낭비율(%)", "버킷 종류(수)", "버킷 분포 상세", "폴더 경로"])
                for r in self.results:
                    buckets_detail = ", ".join([f"{k}:{v}" for k, v in sorted(r['buckets'].items())])
                    theo_ops = r['count'] * r['repeat']
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

    def on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item_id or column != "#5": return # 설정 리핏 열
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
        """추천 리핏 설정: 표에 계산된 '추천 리핏(C+B)' 값을 설정 리핏으로 적용"""
        if not self.results: return
        for r in self.results:
            r['repeat'] = r.get('recommend', 1)
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()

    def set_optimal_repeats(self):
        """최적 리핏 설정: 기존 방식(소규모 폴더 = 최종 배치값) 적용으로 낭비율 최소화"""
        if not self.results: return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        for r in self.results:
            # 평균보다 적은 폴더는 최종 배치값으로 고정 (버킷 낭비 0% 유도)
            if r['count'] < self.avg_data:
                r['repeat'] = batch_total
            else:
                r['repeat'] = r.get('recommend', 1)
            self._recalculate_folder(r)
        self.update_table()
        self.update_summary()

    def set_averaged_repeats(self):
        """균등 리핏 설정: 리핏 1 기준 고정 목표치를 사용하여 부드럽고 자연스러운 리핏 산출 (무한증폭 수정)"""
        if not self.results: return
        batch_total = self.batch_size.get() * self.grad_acc.get()
        
        # [중요] 누를 때마다 늘어나는 버그 수정: 리핏 1 기준의 '고정된' 목표 스텝 사용
        # 모든 폴더가 리핏 1일 때의 총 스텝을 구하여 평균 기준점을 잡음
        base_total_steps = 0
        for r in self.results:
            _, _, steps = DatasetAnalyzer.calculate_waste(r['buckets'], 1, batch_total)
            base_total_steps += steps
        
        # 리핏 1 기준의 평균 스텝 (이 값이 기준점이 되어 무한 증폭을 막음)
        avg_base_step = base_total_steps / len(self.results) if self.results else 1
        
        for r in self.results:
            if r['count'] > 0:
                # 1. 이상적인 리핏 계산 (평균 스텝에 도달하기 위한 값)
                # ideal_r = (기준평균스텝 * 배치) / 이미지수
                ideal_r = (avg_base_step * batch_total) / r['count']
                
                # 2. 탐색 범위 (이상적 리핏 주변으로 제한하여 퀀텀 점프 방지)
                base_r = max(1, round(ideal_r))
                search_range = [max(1, base_r - 1), base_r, base_r + 1, base_r + 2]
                
                best_r = base_r
                min_score = float('inf')
                
                for cand in sorted(list(set(search_range))):
                    _, waste_rate, steps = DatasetAnalyzer.calculate_waste(r['buckets'], cand, batch_total)
                    
                    # 3. 점수제 도입 (Stiffness 제거)
                    # 스텝 차이(거리)를 가장 중요하게 보고, 낭비율은 미세한 가중치로만 사용
                    step_error = abs(steps - avg_base_step)
                    waste_penalty = (waste_rate / 100) * 0.5 # 낭비율의 영향력을 낮춤
                    
                    # 최종 점수 = 거리 오차 + 낭비 패널티
                    score = step_error + waste_penalty
                    
                    if score < min_score:
                        min_score = score
                        best_r = cand
                    elif abs(score - min_score) < 1e-7:
                        # 점수가 같다면 짝수 선호
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
        
        # 버킷 목록 미리 생성 (미스매치 계산용)
        bucket_list = DatasetAnalyzer.make_buckets(b_target, b_min, b_max, b_steps)
        bucket_ars = [bw / bh for bw, bh in bucket_list]
        
        for r in self.results:
            # 원본 차원 정보가 있으면 현재 설정으로 버킷 재계산
            if 'image_dims' in r and r['image_dims']:
                r['buckets'] = DatasetAnalyzer.rebucketize(r['image_dims'], b_steps, b_min, b_max, b_target)
                
                # 미스매치 재계산
                r['mismatches'] = []
                # image_dims만으론 파일명을 알 수 없으므로, 초기 스캔 때 저장된 구조가 필요할 수 있음.
                # 하지만 analyze_folder_worker가 이미 r['mismatches']를 채워왔으므로, 
                # 여기서 비율만 다시 체크함 (이미지 순서가 dims와 동일하다고 가정)
                # 원본 파일명 정보를 보존하기 위해 초기 스캔 시 image_dims에 파일명을 포함하도록 수정하는 것이 정석이나,
                # 일단은 '이미지 정보'가 유효할 때만 비율 차이만 다시 계산함.
                # (실제 파일명이 누락될 수 있으므로, 재분석 시에는 "미스매치 재감지" 문구 정도만 업데이트)
                
                for w, h in r['image_dims']:
                    orig_ar = w / h
                    diffs = [abs(orig_ar - b_ar) for b_ar in bucket_ars]
                    best_idx = diffs.index(min(diffs))
                    b_ar = bucket_ars[best_idx]
                    bw, bh = bucket_list[best_idx]
                    
                    if abs(orig_ar - b_ar) / b_ar > 0.3:
                        r['mismatches'].append({
                            'file_name': "(계산 갱신됨)",
                            'resolution': f"{w}x{h}",
                            'orig_ar': round(orig_ar, 3),
                            'bucket_ar': round(b_ar, 3),
                            'bucket_res': f"{bw}x{bh}",
                            'folder_path': r['folder_path']
                        })
            
            self._recalculate_folder(r)
            
        self._update_recommend_column() # 추천 리핏 열 갱신
        self.update_table()
        self.update_summary()
        
        # 버튼 상태 업데이트
        total_mismatches = sum(len(r.get('mismatches', [])) for r in self.results)
        if total_mismatches > 0:
            self.mismatch_btn.config(state=tk.NORMAL)
        else:
            self.mismatch_btn.config(state=tk.DISABLED)
