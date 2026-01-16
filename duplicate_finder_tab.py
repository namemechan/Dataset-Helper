import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading
import os
import shutil
from duplicate_finder import DuplicateFinder, ImageInfo
from utils import format_number, ScrollableFrame

class DuplicateFinderGUI:
    def __init__(self, parent, folder_path_var=None):
        self.parent = parent
        self.finder = DuplicateFinder()
        self.search_thread = None
        
        # 메인 앱과 폴더 경로 연동
        self.folder_path_var = folder_path_var if folder_path_var else tk.StringVar()
        
        # UI 변수
        self.check_md5 = tk.BooleanVar(value=True)
        self.check_dhash = tk.BooleanVar(value=False)
        self.match_resolution = tk.BooleanVar(value=True)
        self.similarity_threshold = tk.IntVar(value=5)
        
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
        
        # 그룹: 검색 설정
        opt_group = ttk.LabelFrame(left_frame, text="검색 옵션 (중복 선택 가능)", padding="10")
        opt_group.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(opt_group, text="완전 중복 (MD5 해시)", 
                       variable=self.check_md5).pack(anchor=tk.W, pady=2)
        
        ttk.Checkbutton(opt_group, text="유사 이미지 (dHash)", 
                       variable=self.check_dhash,
                       command=self.toggle_threshold).pack(anchor=tk.W, pady=2)
        
        self.threshold_frame = ttk.Frame(opt_group)
        self.threshold_frame.pack(fill=tk.X, pady=5)
        ttk.Label(self.threshold_frame, text="유사도 허용 오차 (0-20):").pack(anchor=tk.W)
        self.threshold_scale = ttk.Scale(self.threshold_frame, from_=0, to=20, 
                                       variable=self.similarity_threshold, orient=tk.HORIZONTAL)
        self.threshold_scale.pack(fill=tk.X)
        self.threshold_label = ttk.Label(self.threshold_frame, text="5")
        self.threshold_label.pack()
        self.threshold_scale.configure(command=lambda v: self.threshold_label.configure(text=str(int(float(v)))))
        
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
        
        self.tree.column("#0", width=120, stretch=False) # Group ID
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
        
        ttk.Button(action_frame, text="선택한 파일 삭제", command=self.delete_selected, style="Accent.TButton").pack(fill=tk.X, pady=2)
        ttk.Button(action_frame, text="선택한 파일 이동...", command=self.move_selected).pack(fill=tk.X, pady=2)
        ttk.Button(action_frame, text="선택한 파일이 속한 폴더 열기", command=self.open_folder).pack(fill=tk.X, pady=2)
        
        self.toggle_threshold() # 초기 상태 설정

    def toggle_threshold(self):
        if not self.check_dhash.get():
            for child in self.threshold_frame.winfo_children():
                child.configure(state=tk.DISABLED)
        else:
            for child in self.threshold_frame.winfo_children():
                child.configure(state=tk.NORMAL)

    def on_preview_resize(self, event):
        """미리보기 영역 크기가 변할 때 이미지 재출력"""
        if self.selected_file_path:
            self.show_preview(self.selected_file_path)

    def start_search(self):
        folder = self.folder_path_var.get()
        if not folder or not os.path.exists(folder):
            messagebox.showwarning("경고", "먼저 상단에서 작업 폴더를 선택해주세요.")
            return
        
        if not self.check_md5.get() and not self.check_dhash.get():
            messagebox.showwarning("경고", "최소한 하나의 검색 옵션을 선택해주세요.")
            return
            
        self.tree.delete(*self.tree.get_children())
        self.found_groups = {}
        self.btn_search.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0
        
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
            results = self.finder.find_duplicates(
                folder,
                check_md5=self.check_md5.get(),
                check_dhash=self.check_dhash.get(),
                match_resolution=self.match_resolution.get(),
                similarity_threshold=self.similarity_threshold.get(),
                progress_callback=self.update_progress
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
        self.progress_var.set(f"검색 완료: {len(results)}개의 중복 그룹 발견")
        
        # 트리뷰 업데이트
        for group_id, data in results.items():
            group_type = data['type']
            items = data['items']
            
            type_text = "[완전 중복]" if group_type == 'exact' else "[유사]"
            rep = items[0]
            
            group_node = self.tree.insert("", tk.END, text=f"{type_text} 그룹 ({len(items)}개)", open=True, 
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
            
        if messagebox.askyesno("삭제 확인", f"정말 삭제하시겠습니까?\n{self.selected_file_path}"):
            try:
                os.remove(self.selected_file_path)
                messagebox.showinfo("완료", "삭제되었습니다.")
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
                shutil.move(self.selected_file_path, os.path.join(dest, os.path.basename(self.selected_file_path)))
                messagebox.showinfo("완료", "이동되었습니다.")
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