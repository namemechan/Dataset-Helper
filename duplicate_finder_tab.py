import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading
import os
import shutil
import time
from duplicate_finder import DuplicateFinder, ImageInfo
from utils import format_number, ScrollableFrame

class DuplicateFinderGUI:
    def __init__(self, parent, folder_path_var=None, core_var=None):
        self.parent = parent
        self.finder = DuplicateFinder()
        self.search_thread = None
        self.start_time = 0
        
        # 메인 앱과 폴더 경로 연동
        self.folder_path_var = folder_path_var if folder_path_var else tk.StringVar()
        self.core_var = core_var # 코어 수 설정 변수
        
        # UI 변수
        self.use_independent_path = tk.BooleanVar(value=False)
        self.independent_folder_path = tk.StringVar()
        
        self.check_md5 = tk.BooleanVar(value=True)
        self.check_dhash = tk.BooleanVar(value=False)
        self.check_tag_search = tk.BooleanVar(value=False) # 태그 검색
        
        self.match_resolution = tk.BooleanVar(value=True)
        self.similarity_threshold = tk.IntVar(value=5)
        self.tag_similarity_threshold = tk.IntVar(value=100) # 태그 유사도 (0-100)
        
        # 범위 검색 변수
        self.check_range_search = tk.BooleanVar(value=False)
        self.range_start = tk.IntVar(value=0)
        self.range_end = tk.IntVar(value=3)
        
        # 액션 옵션
        self.delete_pair_txt = tk.BooleanVar(value=False)
        
        self.found_groups = {} 
        self.selected_file_path = None
        
        self.create_widgets()

    def create_widgets(self):
        # 전체 스크롤 적용
        scroll = ScrollableFrame(self.parent)
        scroll.pack(fill=tk.BOTH, expand=True)
        main_content = scroll.scrollable_frame
        
        # 레이아웃: 
        # Left: 설정 (20%) - weight=1
        # Center: 목록 (40%) - weight=2
        # Right: 미리보기 (40%) - weight=2
        
        paned_window = ttk.PanedWindow(main_content, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # --- 1. 왼쪽 패널 (설정) ---
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        
        # 그룹: 독립 경로 설정 (New)
        path_group = ttk.LabelFrame(left_frame, text="경로 설정", padding="10")
        path_group.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(path_group, text="독립적인 경로 사용", 
                       variable=self.use_independent_path, 
                       command=self.toggle_ui_state).pack(anchor=tk.W)
        
        self.independent_path_frame = ttk.Frame(path_group)
        self.independent_path_frame.pack(fill=tk.X, pady=5)
        
        self.independent_entry = ttk.Entry(self.independent_path_frame, textvariable=self.independent_folder_path)
        self.independent_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.independent_btn = ttk.Button(self.independent_path_frame, text="선택", width=5, command=self.select_independent_folder)
        self.independent_btn.pack(side=tk.LEFT)
        
        # 그룹: 검색 설정
        opt_group = ttk.LabelFrame(left_frame, text="검색 옵션 (중복 선택 가능)", padding="10")
        opt_group.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(opt_group, text="완전 중복 (MD5 해시)", 
                       variable=self.check_md5).pack(anchor=tk.W, pady=2)
        
        # 태그 검색 옵션
        ttk.Checkbutton(opt_group, text="태그 내용 기반 검색 (.txt)", 
                       variable=self.check_tag_search,
                       command=self.toggle_ui_state).pack(anchor=tk.W, pady=2)
                       
        self.tag_frame = ttk.Frame(opt_group, padding=(20, 0, 0, 0))
        self.tag_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(self.tag_frame, text="태그 일치율 (%):").pack(anchor=tk.W)
        self.tag_scale = ttk.Scale(self.tag_frame, from_=0, to=100, 
                                 variable=self.tag_similarity_threshold, orient=tk.HORIZONTAL)
        self.tag_scale.pack(fill=tk.X)
        self.tag_label = ttk.Label(self.tag_frame, text="100")
        self.tag_label.pack()
        self.tag_scale.configure(command=lambda v: self.tag_label.configure(text=str(int(float(v)))))
        
        # dHash 옵션
        ttk.Checkbutton(opt_group, text="유사 이미지 (dHash)", 
                       variable=self.check_dhash,
                       command=self.toggle_ui_state).pack(anchor=tk.W, pady=2)
        
        # === 유사도 설정 프레임 ===
        self.threshold_frame = ttk.Frame(opt_group)
        self.threshold_frame.pack(fill=tk.X, pady=5)
        
        # 1) 단일 슬라이더
        self.single_threshold_frame = ttk.Frame(self.threshold_frame)
        self.single_threshold_frame.pack(fill=tk.X)
        
        ttk.Label(self.single_threshold_frame, text="유사도 허용 오차 (0-20):").pack(anchor=tk.W)
        self.threshold_scale = ttk.Scale(self.single_threshold_frame, from_=0, to=20, 
                                       variable=self.similarity_threshold, orient=tk.HORIZONTAL)
        self.threshold_scale.pack(fill=tk.X)
        self.threshold_label = ttk.Label(self.single_threshold_frame, text="5")
        self.threshold_label.pack()
        self.threshold_scale.configure(command=lambda v: self.threshold_label.configure(text=str(int(float(v)))))
        
        # 2) 범위 검색 옵션
        ttk.Separator(self.threshold_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(self.threshold_frame, text="유사도 그룹 검색 (범위)", 
                       variable=self.check_range_search,
                       command=self.toggle_ui_state).pack(anchor=tk.W)
        
        self.range_frame = ttk.Frame(self.threshold_frame)
        self.range_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.range_frame, text="시작값:").pack(side=tk.LEFT)
        ttk.Spinbox(self.range_frame, from_=0, to=20, textvariable=self.range_start, width=3).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(self.range_frame, text="종료값:").pack(side=tk.LEFT)
        ttk.Spinbox(self.range_frame, from_=0, to=20, textvariable=self.range_end, width=3).pack(side=tk.LEFT, padx=5)
        # ==========================
        
        ttk.Separator(opt_group, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(opt_group, text="이미지 비율(Aspect Ratio)이 같은 것끼리만 비교", 
                       variable=self.match_resolution).pack(anchor=tk.W)
        ttk.Label(opt_group, text="(크기가 달라도 비율이 같으면 비교)", font=("", 8), foreground="gray").pack(anchor=tk.W, padx=20)

        # 검색 버튼
        self.btn_search = ttk.Button(left_frame, text="중복 이미지 찾기 시작", command=self.start_search)
        self.btn_search.pack(fill=tk.X, pady=20)
        
        self.btn_stop = ttk.Button(left_frame, text="검색 중지", command=self.stop_search, state=tk.DISABLED)
        self.btn_stop.pack(fill=tk.X)
        
        # 진행 상황
        self.progress_var = tk.StringVar(value="대기 중")
        ttk.Label(left_frame, textvariable=self.progress_var, wraplength=200).pack(pady=10)
        self.progress_bar = ttk.Progressbar(left_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X)

        # --- 2. 중앙 패널 (결과 목록) ---
        center_frame = ttk.Frame(paned_window)
        paned_window.add(center_frame, weight=2)
        
        ttk.Label(center_frame, text="검색 결과").pack(anchor=tk.W, pady=5)
        
        # Treeview
        columns = ("filename", "resolution", "size", "path")
        self.tree = ttk.Treeview(center_frame, columns=columns, show="tree headings")
        self.tree.heading("filename", text="파일 이름")
        self.tree.heading("resolution", text="해상도")
        self.tree.heading("size", text="크기")
        self.tree.heading("path", text="경로")
        
        self.tree.column("#0", width=200, stretch=False) # Group ID area increased
        self.tree.column("filename", width=150)
        self.tree.column("resolution", width=100)
        self.tree.column("size", width=80)
        self.tree.column("path", width=200)
        
        scrollbar = ttk.Scrollbar(center_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # --- 3. 우측 패널 (미리보기 및 액션) ---
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=2)
        
        # 이미지 미리보기 (이벤트 바인딩을 위해 별도 프레임으로 감쌈)
        self.preview_container = ttk.Frame(right_frame, relief=tk.SUNKEN)
        self.preview_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.preview_label = ttk.Label(self.preview_container, text="이미지를 선택하세요", anchor=tk.CENTER)
        self.preview_label.pack(fill=tk.BOTH, expand=True)
        
        # 리사이즈 이벤트 바인딩
        self.preview_label.bind("<Configure>", self.on_preview_resize)
        
        # 정보 표시
        self.info_label = ttk.Label(right_frame, text="", justify=tk.LEFT)
        self.info_label.pack(fill=tk.X, padx=5, pady=5)
        
        # 액션 버튼
        action_frame = ttk.Frame(right_frame)
        action_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(action_frame, text="동일명의 태깅파일(.txt)도 같이 처리", 
                       variable=self.delete_pair_txt).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(action_frame, text="선택한 파일 삭제", command=self.delete_selected, style="Accent.TButton").pack(fill=tk.X, pady=2)
        ttk.Button(action_frame, text="선택한 파일 이동...", command=self.move_selected).pack(fill=tk.X, pady=2)
        ttk.Button(action_frame, text="선택한 파일이 속한 폴더 열기", command=self.open_folder).pack(fill=tk.X, pady=2)
        
        self.toggle_ui_state() # 초기 상태 설정

    def toggle_ui_state(self):
        # 0. 독립 경로 UI 상태
        if self.use_independent_path.get():
            self.independent_entry.config(state=tk.NORMAL)
            self.independent_btn.config(state=tk.NORMAL)
        else:
            self.independent_entry.config(state=tk.DISABLED)
            self.independent_btn.config(state=tk.DISABLED)

        # 1. 태그 UI 상태
        if self.check_tag_search.get():
            for child in self.tag_frame.winfo_children():
                child.configure(state=tk.NORMAL)
        else:
            for child in self.tag_frame.winfo_children():
                child.configure(state=tk.DISABLED)

        # 2. dHash UI 상태
        if not self.check_dhash.get():
            for child in self.threshold_frame.winfo_children():
                for sub in child.winfo_children():
                    sub.configure(state=tk.DISABLED)
        else:
            for child in self.threshold_frame.winfo_children():
                for sub in child.winfo_children():
                    sub.configure(state=tk.NORMAL)
            
            # dHash 범위 검색 상태에 따른 교차 비활성화
            if self.check_range_search.get():
                for child in self.single_threshold_frame.winfo_children():
                    child.configure(state=tk.DISABLED)
                for child in self.range_frame.winfo_children():
                    child.configure(state=tk.NORMAL)
            else:
                for child in self.single_threshold_frame.winfo_children():
                    child.configure(state=tk.NORMAL)
                for child in self.range_frame.winfo_children():
                    child.configure(state=tk.DISABLED)

    def on_preview_resize(self, event):
        """미리보기 영역 크기가 변할 때 이미지 재출력"""
        if self.selected_file_path:
            self.show_preview(self.selected_file_path)

    def select_independent_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.independent_folder_path.set(folder)

    def start_search(self):
        # 경로 결정: 독립 경로 사용 여부에 따라 분기
        if self.use_independent_path.get():
            folder = self.independent_folder_path.get()
            if not folder:
                messagebox.showwarning("경고", "독립 경로 폴더를 선택해주세요.")
                return
        else:
            folder = self.folder_path_var.get()
            
        if not folder or not os.path.exists(folder):
            messagebox.showwarning("경고", "작업 폴더가 올바르지 않습니다.")
            return
        
        if not any([self.check_md5.get(), self.check_dhash.get(), self.check_tag_search.get()]):
            messagebox.showwarning("경고", "최소한 하나의 검색 옵션을 선택해주세요.")
            return
            
        self.tree.delete(*self.tree.get_children())
        self.found_groups = {}
        self.btn_search.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0
        self.start_time = time.time()
        
        # 쓰레드 시작
        self.search_thread = threading.Thread(target=self.run_search, args=(folder,))
        self.search_thread.daemon = True
        self.search_thread.start()

    def stop_search(self):
        if self.finder:
            self.finder.stop()
            self.progress_var.set("중지 요청됨...")

    def run_search(self, folder):
        try:
            # 설정된 코어 수 가져오기 (설정이 없으면 기본값인 None 전달 -> duplicate_finder 내부 로직 따름)
            max_workers = self.core_var.get() if self.core_var else None
            
            # 범위 검색 설정 확인 및 값 교정
            range_threshold = None
            if self.check_dhash.get() and self.check_range_search.get():
                s = self.range_start.get()
                e = self.range_end.get()
                
                # 사용자가 역순으로 입력했을 경우 (예: 6 ~ 3) -> 자동 스왑 (3 ~ 6)
                if s > e:
                    s, e = e, s
                    # UI에도 반영하여 사용자가 알 수 있게 함
                    self.parent.after(0, lambda: self.range_start.set(s))
                    self.parent.after(0, lambda: self.range_end.set(e))
                
                range_threshold = (s, e)

            results = self.finder.find_duplicates(
                folder,
                check_md5=self.check_md5.get(),
                check_dhash=self.check_dhash.get(),
                check_tag=self.check_tag_search.get(),
                match_resolution=self.match_resolution.get(),
                similarity_threshold=self.similarity_threshold.get(),
                tag_similarity_threshold=self.tag_similarity_threshold.get(),
                progress_callback=self.update_progress,
                max_workers=max_workers,
                range_threshold=range_threshold
            )
            self.parent.after(0, self.search_complete, results)
        except Exception as e:
            # self.parent.after(0, messagebox.showerror, "오류", f"검색 중 오류 발생: {e}")
            print(f"Error: {e}") # 디버깅용
            self.parent.after(0, self.reset_ui)

    def update_progress(self, current, total, message):
        progress = (current / total) * 100 if total > 0 else 0
        self.parent.after(0, lambda: self.progress_var.set(message))
        self.parent.after(0, lambda: self.progress_bar.configure(value=progress))

    def search_complete(self, results):
        self.found_groups = results
        self.reset_ui()
        elapsed = time.time() - self.start_time
        
        # 결과 처리 로직 분기
        if isinstance(results, dict) and 'mode' in results and results['mode'] == 'range':
            # === 범위 검색 결과 ===
            md5_results = results.get('md5', {})
            dhash_results = results.get('dhash', {}) # {threshold: {group_id: ...}}
            
            count_total = len(md5_results)
            for th_res in dhash_results.values():
                count_total += len(th_res)
                
            self.progress_var.set(f"검색 완료: 총 {count_total}개의 그룹/쌍 발견 (소요 시간: {elapsed:.2f}초)")
            
            # 1. MD5 결과 표시
            if md5_results:
                md5_root = self.tree.insert("", tk.END, text=f"완전 중복 (MD5) - {len(md5_results)}그룹", open=True)
                self._insert_groups_to_tree(md5_root, md5_results)
            
            # 2. dHash 결과 표시 (Threshold 별로)
            # 키(Threshold)를 오름차순 정렬
            sorted_thresholds = sorted(dhash_results.keys())
            
            for th in sorted_thresholds:
                groups = dhash_results[th]
                if not groups: continue
                
                # 최상위 노드: 유사도_N그룹_M개
                th_node_text = f"유사도_{th}그룹_{len(groups)}개"
                th_root = self.tree.insert("", tk.END, text=th_node_text, open=False)
                
                self._insert_groups_to_tree(th_root, groups)
                
        else:
            # === 기존 단일 검색 결과 ===
            self.progress_var.set(f"검색 완료: {len(results)}개의 중복 그룹/쌍 발견 (소요 시간: {elapsed:.2f}초)")
            self._insert_groups_to_tree("", results) # Root에 바로 추가

    def _insert_groups_to_tree(self, parent_node, groups_dict):
        """트리뷰에 그룹 목록을 삽입하는 헬퍼 함수"""
        for group_id, data in groups_dict.items():
            group_type = data['type']
            items = data['items']
            
            # 용어 결정: 2개면 '쌍', 3개 이상이면 '그룹'
            term = "쌍" if len(items) == 2 else "그룹"
            
            if group_type == 'exact':
                label = f"[완전 중복] {term}"
            else:
                label = f"[유사] {term}"
            
            rep = items[0]
            group_node = self.tree.insert(parent_node, tk.END, text=f"{label} ({len(items)}개)", open=True, 
                                        values=("", f"{rep.resolution[0]}x{rep.resolution[1]}", "", ""))
            
            for item in items:
                size_str = f"{item.size / 1024:.1f} KB"
                self.tree.insert(group_node, tk.END, text="", 
                               values=(os.path.basename(item.path), 
                                       f"{item.resolution[0]}x{item.resolution[1]}",
                                       size_str,
                                       item.path))

    def reset_ui(self):
        self.btn_search.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0

    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        
        item_id = selected_items[0]
        item = self.tree.item(item_id)
        
        # 그룹 노드를 선택했거나 값이 없는 경우
        values = item['values']
        if not values or not values[3]: 
            return
            
        file_path = values[3]
        self.selected_file_path = file_path
        self.show_preview(file_path)

    def show_preview(self, path):
        try:
            image = Image.open(path)
            
            # 가용한 영역 크기 확인
            canvas_width = self.preview_label.winfo_width()
            canvas_height = self.preview_label.winfo_height()
            
            # 최초 실행 시나 아주 작은 경우 기본값 설정
            if canvas_width < 10 or canvas_height < 10:
                canvas_width, canvas_height = 300, 300
            
            # 여백 고려 (패딩 10px)
            display_width = max(canvas_width - 10, 10)
            display_height = max(canvas_height - 10, 10)
            
            # 리사이즈 (비율 유지)
            image.thumbnail((display_width, display_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(image)
            self.preview_label.config(image=photo, text="")
            self.preview_label.image = photo 
            
            stat = os.stat(path)
            info_text = (f"파일명: {os.path.basename(path)}\n"
                        f"경로: {os.path.dirname(path)}\n"
                        f"크기: {image.size[0]}x{image.size[1]} ({stat.st_size/1024:.1f} KB)")
            self.info_label.config(text=info_text)
            
        except Exception as e:
            self.preview_label.config(image='', text="이미지를 불러올 수 없습니다.")
            self.info_label.config(text=f"오류: {e}")

    def delete_selected(self):
        if not self.selected_file_path:
            return
            
        file_path = self.selected_file_path
        txt_path = os.path.splitext(file_path)[0] + '.txt'
        has_txt = self.delete_pair_txt.get() and os.path.exists(txt_path)
        
        msg = f"정말 삭제하시겠습니까?\n이미지: {os.path.basename(file_path)}"
        if has_txt:
            msg += f"\n캡션: {os.path.basename(txt_path)}"
            
        if messagebox.askyesno("삭제 확인", msg):
            try:
                os.remove(file_path)
                deleted_msg = "이미지 삭제됨"
                
                if has_txt:
                    os.remove(txt_path)
                    deleted_msg += ", 캡션 삭제됨"
                
                messagebox.showinfo("완료", deleted_msg)
                
                selected = self.tree.selection()[0]
                self.tree.delete(selected)
                self.selected_file_path = None
                self.preview_label.config(image='', text="삭제됨")
                self.info_label.config(text="")
            except Exception as e:
                messagebox.showerror("오류", f"삭제 실패: {e}")

    def move_selected(self):
        if not self.selected_file_path:
            return
            
        dest = filedialog.askdirectory(title="이동할 폴더 선택")
        if dest:
            try:
                file_path = self.selected_file_path
                txt_path = os.path.splitext(file_path)[0] + '.txt'
                
                shutil.move(file_path, os.path.join(dest, os.path.basename(file_path)))
                moved_msg = "이미지 이동됨"
                
                if self.delete_pair_txt.get() and os.path.exists(txt_path):
                    shutil.move(txt_path, os.path.join(dest, os.path.basename(txt_path)))
                    moved_msg += ", 캡션 이동됨"

                messagebox.showinfo("완료", moved_msg)
                selected = self.tree.selection()[0]
                self.tree.delete(selected)
                self.selected_file_path = None
                self.preview_label.config(image='', text="이동됨")
            except Exception as e:
                messagebox.showerror("오류", f"이동 실패: {e}")

    def open_folder(self):
        if self.selected_file_path:
            try:
                os.startfile(os.path.dirname(self.selected_file_path))
            except Exception as e:
                messagebox.showerror("오류", f"폴더 열기 실패: {e}")
