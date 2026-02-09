"데이터셋 정리 툴 - 메인 GUI"
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import multiprocessing
import json

from file_manager import FileManager
from tag_processor import TagProcessor
from rename_processor import RenameProcessor
from utils import get_paired_files, ScrollableFrame

from image_converter_tab import ImageConverterGUI
from duplicate_finder_tab import DuplicateFinderGUI
from app_logger import logger
import os
import sys

# 실행 환경(exe/script)에 따라 설정 파일 경로 결정
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

SETTINGS_FILE = APP_DIR / "settings.json"

class DatasetOrganizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("dataset-helper")
        self.root.geometry("900x700") # 높이 약간 증가
        
        self.folder_path = ""
        self.folder_path_var = tk.StringVar() # For linking with tabs
        self.num_cores = multiprocessing.cpu_count()
        
        # UI 변수 초기화 (설정 로드 전 기본값)
        self.core_var = tk.IntVar(value=self.num_cores)
        
        # 태그 탭 변수
        self.use_person_tag = tk.BooleanVar(value=True)
        self.use_move_solo = tk.BooleanVar(value=False) # Solo 태그 이동 옵션 추가
        self.use_custom_move = tk.BooleanVar(value=False)
        self.use_replace = tk.BooleanVar(value=False)
        
        self.use_delete = tk.BooleanVar(value=False)
        self.use_conditional_delete = tk.BooleanVar(value=False) # 조건부 삭제

        # 인접 태그 수정 변수
        self.use_neighbor_modify = tk.BooleanVar(value=False)
        self.neighbor_target = tk.StringVar()
        self.neighbor_pos = tk.StringVar(value="after")
        self.neighbor_add_pos = tk.StringVar(value="prefix")
        self.neighbor_text = tk.StringVar()

        # CSV 기반 특수 처리 변수
        self.use_csv_process = tk.BooleanVar(value=False)
        self.csv_file_path = tk.StringVar()
        self.csv_category = tk.StringVar(value="0")
        self.csv_mode = tk.StringVar(value="add")
        self.csv_add_pos = tk.StringVar(value="prefix")
        self.csv_input_text = tk.StringVar()

        self.use_add = tk.BooleanVar(value=False)
        self.use_conditional_add = tk.BooleanVar(value=False) # 조건부 추가
        
        self.find_subdirs = tk.BooleanVar(value=False)
        self.tag_find_subdirs = tk.BooleanVar(value=False) # 태그 탭용 하위폴더 검색

        # 누락된 태그 추가 변수
        self.use_missing_tag = tk.BooleanVar(value=False)
        self.missing_gender = tk.StringVar(value="girl")
        self.missing_count = tk.StringVar(value="1")
        
        self.create_widgets()
        
        # 설정 로드
        self.load_settings()
        
        # 종료 이벤트 바인딩
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        # 상단 프레임 - 폴더 선택
        top_frame = ttk.Frame(self.root, padding="5")
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="작업 폴더:").pack(side=tk.LEFT)
        
        self.folder_label = ttk.Label(top_frame, text="폴더를 선택하세요", relief=tk.SUNKEN, width=50)
        self.folder_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(top_frame, text="폴더 선택", command=self.select_folder).pack(side=tk.LEFT)
        
        # 코어 수 설정
        ttk.Label(top_frame, text="사용 코어:").pack(side=tk.LEFT, padx=(20, 5))
        core_spin = ttk.Spinbox(top_frame, from_=1, to=multiprocessing.cpu_count(), 
                                textvariable=self.core_var, width=5)
        core_spin.pack(side=tk.LEFT)
        
        # 노트북 (탭)
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 탭 1: 이름 변경
        self.create_rename_tab(notebook)
        
        # 탭 2: 단일 파일 찾기
        self.create_find_single_tab(notebook)
        
        # 탭 3: 태그 처리
        self.create_tag_tab(notebook)

        # 탭 4: 이미지 변환
        self.create_converter_tab(notebook)

        # 탭 5: 중복/유사 이미지 찾기
        self.create_duplicate_tab(notebook)
    
    def create_rename_tab(self, notebook):
        tab_frame = ttk.Frame(notebook)
        notebook.add(tab_frame, text="이름 변경")
        
        scroll = ScrollableFrame(tab_frame)
        scroll.pack(fill=tk.BOTH, expand=True)
        frame = scroll.scrollable_frame
        
        # 입력 프레임 (frame -> scroll.scrollable_frame)
        input_frame = ttk.LabelFrame(frame, text="설정", padding="5")
        input_frame.pack(fill=tk.X, pady=(0, 5))
        input_frame.columnconfigure(1, weight=1) # 입력창 확장
        
        ttk.Label(input_frame, text="기본 이름:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.rename_base = ttk.Entry(input_frame, width=30)
        self.rename_base.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.rename_base.insert(0, "image")
        
        ttk.Label(input_frame, text="시작 번호:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.rename_start = ttk.Entry(input_frame, width=30)
        self.rename_start.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        self.rename_start.insert(0, "1")
        
        ttk.Label(input_frame, text="숫자 자릿수:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.rename_digits = ttk.Entry(input_frame, width=30)
        self.rename_digits.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        self.rename_digits.insert(0, "6")
        
        # 버튼 프레임
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="미리보기", command=self.preview_rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="이름 변경 실행", command=self.execute_rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="실행 취소", command=self.undo_rename, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        
        # 결과 텍스트
        ttk.Label(frame, text="결과:").pack(anchor=tk.W)
        self.rename_text = scrolledtext.ScrolledText(frame, height=20)
        self.rename_text.pack(fill=tk.BOTH, expand=True)
    
    def create_find_single_tab(self, notebook):
        tab_frame = ttk.Frame(notebook)
        notebook.add(tab_frame, text="단일 파일 찾기")
        
        scroll = ScrollableFrame(tab_frame)
        scroll.pack(fill=tk.BOTH, expand=True)
        frame = scroll.scrollable_frame
        
        # 버튼 프레임
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="단일 이미지 찾기", command=self.find_single_images).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="단일 텍스트 찾기", command=self.find_single_texts).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(btn_frame, text="하위 폴더 포함 검색", variable=self.find_subdirs).pack(side=tk.LEFT, padx=15)
        
        # 결과 텍스트
        ttk.Label(frame, text="결과:").pack(anchor=tk.W)
        self.single_text = scrolledtext.ScrolledText(frame, height=15)
        self.single_text.pack(fill=tk.BOTH, expand=True)
        
        # 작업 버튼 프레임
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(action_frame, text="삭제", command=self.delete_single_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="이동", command=self.move_single_files).pack(side=tk.LEFT, padx=5)
        
        self.single_files = []
    
    def create_tag_tab(self, notebook):
        tab_frame = ttk.Frame(notebook)
        notebook.add(tab_frame, text="태그 처리")
        
        scroll = ScrollableFrame(tab_frame)
        scroll.pack(fill=tk.BOTH, expand=True)
        frame = scroll.scrollable_frame
        
        # 메인 컨테이너
        container = ttk.Frame(frame, padding="5")
        container.pack(fill=tk.BOTH, expand=True)
        
        # --- 상단 옵션: 하위 폴더 포함 ---
        frame_top = ttk.Frame(container)
        frame_top.pack(anchor=tk.W, fill=tk.X, pady=(0, 5))
        ttk.Checkbutton(frame_top, text="하위 폴더 포함 검색", variable=self.tag_find_subdirs).pack(side=tk.LEFT)
        
        # --- 옵션 1: 인원수 태그 이동 & Solo 태그 이동 ---
        frame_person = ttk.Frame(container)
        frame_person.pack(anchor=tk.W, fill=tk.X, pady=(0, 5))

        check_person = ttk.Checkbutton(frame_person, text="인원수 태그 맨 앞으로 이동 (1girl, 2boys 등)", 
                                     variable=self.use_person_tag)
        check_person.pack(side=tk.LEFT)

        check_solo = ttk.Checkbutton(frame_person, text="'solo' 태그도 함께 이동", 
                                     variable=self.use_move_solo)
        check_solo.pack(side=tk.LEFT, padx=15)

        # --- 옵션 1.1: 누락된 인원수 태그 주입 (New) ---
        group_missing = ttk.LabelFrame(container, text="인원수 태그 누락 시 자동 추가", padding="5")
        group_missing.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(group_missing, text="사용", variable=self.use_missing_tag).pack(side=tk.LEFT)
        ttk.Separator(group_missing, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Label(group_missing, text="성별:").pack(side=tk.LEFT)
        ttk.Radiobutton(group_missing, text="Girl", variable=self.missing_gender, value="girl").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(group_missing, text="Boy", variable=self.missing_gender, value="boy").pack(side=tk.LEFT, padx=5)
        
        ttk.Label(group_missing, text="인원:").pack(side=tk.LEFT, padx=(15, 5))
        missing_count_cb = ttk.Combobox(group_missing, textvariable=self.missing_count, width=5, state="readonly")
        missing_count_cb['values'] = ("1", "2", "3", "4", "5", "6+")
        missing_count_cb.pack(side=tk.LEFT)

        # --- 옵션 1.5: 태그 추가 (New) ---
        group_add = ttk.LabelFrame(container, text="태그 추가 (인원수/solo 뒤에 자동 삽입)", padding="5")
        group_add.pack(fill=tk.X, pady=5)
        
        # 행 1: 기본 추가 기능
        frame_add_main = ttk.Frame(group_add)
        frame_add_main.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(frame_add_main, text="사용", variable=self.use_add).pack(side=tk.LEFT)
        ttk.Label(frame_add_main, text="추가할 태그:").pack(side=tk.LEFT, padx=5)
        self.add_tag_entry = ttk.Entry(frame_add_main)
        self.add_tag_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 행 2: 조건부 추가 기능
        frame_add_cond = ttk.Frame(group_add)
        frame_add_cond.pack(fill=tk.X, pady=2)
        
        def toggle_cond_add():
            state = tk.NORMAL if self.use_conditional_add.get() else tk.DISABLED
            self.cond_add_entry.config(state=state)

        ttk.Checkbutton(frame_add_cond, text="조건부 추가 사용", variable=self.use_conditional_add, command=toggle_cond_add).pack(side=tk.LEFT)
        ttk.Label(frame_add_cond, text="조건 태그 (|로 구분):").pack(side=tk.LEFT, padx=5)
        self.cond_add_entry = ttk.Entry(frame_add_cond, state=tk.DISABLED)
        self.cond_add_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # --- 옵션 2: 추가 이동 태그 ---
        group_move = ttk.LabelFrame(container, text="추가 이동 태그 (인원수/추가 태그 뒤)", padding="5")
        group_move.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(group_move, text="사용", variable=self.use_custom_move).pack(side=tk.LEFT)
        
        ttk.Label(group_move, text="태그 (|로 구분):").pack(side=tk.LEFT, padx=5)
        self.custom_move_entry = ttk.Entry(group_move)
        self.custom_move_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.custom_move_entry.insert(0, "simple background|white background")
        
        # --- 옵션 3: 태그 치환 ---
        group_replace = ttk.LabelFrame(container, text="태그 치환 (찾아서 변경 - 연속 태그 가능)", padding="5")
        group_replace.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(group_replace, text="사용", variable=self.use_replace).pack(side=tk.LEFT)
        
        ttk.Label(group_replace, text="찾을 태그:").pack(side=tk.LEFT, padx=5)
        self.replace_find_entry = ttk.Entry(group_replace, width=20)
        self.replace_find_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        ttk.Label(group_replace, text="→ 변경할 태그:").pack(side=tk.LEFT, padx=5)
        self.replace_with_entry = ttk.Entry(group_replace, width=20)
        self.replace_with_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # --- 옵션 3.5: 인접 태그 수정 (New) ---
        group_neighbor = ttk.LabelFrame(container, text="인접 태그 접두/미사 추가", padding="5")
        group_neighbor.pack(fill=tk.X, pady=5)
        
        frame_nb_top = ttk.Frame(group_neighbor)
        frame_nb_top.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(frame_nb_top, text="사용", variable=self.use_neighbor_modify).pack(side=tk.LEFT)
        
        ttk.Label(frame_nb_top, text="기준 태그:").pack(side=tk.LEFT, padx=(10, 5))
        self.neighbor_target_entry = ttk.Entry(frame_nb_top, textvariable=self.neighbor_target, width=15)
        self.neighbor_target_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(frame_nb_top, text="추가할 텍스트:").pack(side=tk.LEFT, padx=(10, 5))
        self.neighbor_text_entry = ttk.Entry(frame_nb_top, textvariable=self.neighbor_text, width=15)
        self.neighbor_text_entry.pack(side=tk.LEFT, padx=5)

        frame_nb_bot = ttk.Frame(group_neighbor)
        frame_nb_bot.pack(fill=tk.X, pady=2)
        
        ttk.Label(frame_nb_bot, text="대상 위치:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(frame_nb_bot, text="앞 태그", variable=self.neighbor_pos, value="before").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(frame_nb_bot, text="뒤 태그", variable=self.neighbor_pos, value="after").pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(frame_nb_bot, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=15)
        
        ttk.Label(frame_nb_bot, text="추가 방식:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(frame_nb_bot, text="접두(앞에)", variable=self.neighbor_add_pos, value="prefix").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(frame_nb_bot, text="접미(뒤에)", variable=self.neighbor_add_pos, value="suffix").pack(side=tk.LEFT, padx=5)
        
        # --- 옵션 3.7: CSV 기반 특수 처리 (New) ---
        group_csv = ttk.LabelFrame(container, text="CSV 기반 특수 처리", padding="5")
        group_csv.pack(fill=tk.X, pady=5)
        
        # 행 1: 사용 여부 및 파일 선택
        frame_csv_file = ttk.Frame(group_csv)
        frame_csv_file.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(frame_csv_file, text="사용", variable=self.use_csv_process).pack(side=tk.LEFT)
        ttk.Label(frame_csv_file, text="CSV 파일:").pack(side=tk.LEFT, padx=(10, 5))
        ttk.Entry(frame_csv_file, textvariable=self.csv_file_path, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(frame_csv_file, text="파일 선택", command=self.select_csv_file).pack(side=tk.LEFT)
        
        # 행 2: 카테고리 및 작업 모드
        frame_csv_opts = ttk.Frame(group_csv)
        frame_csv_opts.pack(fill=tk.X, pady=2)
        
        ttk.Label(frame_csv_opts, text="태그 종류(숫자):").pack(side=tk.LEFT)
        ttk.Spinbox(frame_csv_opts, from_=0, to=10, textvariable=self.csv_category, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(frame_csv_opts, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=15)
        
        ttk.Label(frame_csv_opts, text="작업:").pack(side=tk.LEFT)
        ttk.Radiobutton(frame_csv_opts, text="추가", variable=self.csv_mode, value="add").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(frame_csv_opts, text="치환", variable=self.csv_mode, value="replace").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(frame_csv_opts, text="삭제", variable=self.csv_mode, value="delete").pack(side=tk.LEFT, padx=5)
        
        # 행 3: 추가 설정 및 입력칸
        self.frame_csv_input = ttk.Frame(group_csv)
        self.frame_csv_input.pack(fill=tk.X, pady=2)
        
        self.label_csv_pos = ttk.Label(self.frame_csv_input, text="추가 위치:")
        self.label_csv_pos.pack(side=tk.LEFT)
        self.rb_csv_pre = ttk.Radiobutton(self.frame_csv_input, text="앞(접두)", variable=self.csv_add_pos, value="prefix")
        self.rb_csv_pre.pack(side=tk.LEFT, padx=5)
        self.rb_csv_suf = ttk.Radiobutton(self.frame_csv_input, text="뒤(접미)", variable=self.csv_add_pos, value="suffix")
        self.rb_csv_suf.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(self.frame_csv_input, text="입력 문자:").pack(side=tk.LEFT, padx=(15, 5))
        self.csv_text_entry = ttk.Entry(self.frame_csv_input, textvariable=self.csv_input_text)
        self.csv_text_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 모드 변경 시 UI 활성/비활성 제어
        def on_csv_mode_change(*args):
            mode = self.csv_mode.get()
            if mode == 'delete':
                self.csv_text_entry.config(state=tk.DISABLED)
                self.rb_csv_pre.config(state=tk.DISABLED)
                self.rb_csv_suf.config(state=tk.DISABLED)
            elif mode == 'replace':
                self.csv_text_entry.config(state=tk.NORMAL)
                self.rb_csv_pre.config(state=tk.DISABLED)
                self.rb_csv_suf.config(state=tk.DISABLED)
            else: # add
                self.csv_text_entry.config(state=tk.NORMAL)
                self.rb_csv_pre.config(state=tk.NORMAL)
                self.rb_csv_suf.config(state=tk.NORMAL)
        
        self.csv_mode.trace_add("write", on_csv_mode_change)
        on_csv_mode_change() # 초기화

        # --- 옵션 4: 태그 삭제 ---
        group_delete = ttk.LabelFrame(container, text="태그 삭제 (쉼표 자동 정리 - 연속 태그 가능)", padding="5")
        group_delete.pack(fill=tk.X, pady=5)
        
        # 행 1: 기본 삭제 기능
        frame_del_main = ttk.Frame(group_delete)
        frame_del_main.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(frame_del_main, text="사용", variable=self.use_delete).pack(side=tk.LEFT)
        ttk.Label(frame_del_main, text="삭제할 태그 (|로 구분):").pack(side=tk.LEFT, padx=5)
        self.delete_tags_entry = ttk.Entry(frame_del_main)
        self.delete_tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 행 2: 조건부 삭제 기능
        frame_del_cond = ttk.Frame(group_delete)
        frame_del_cond.pack(fill=tk.X, pady=2)
        
        def toggle_cond_del():
            state = tk.NORMAL if self.use_conditional_delete.get() else tk.DISABLED
            self.cond_del_entry.config(state=state)

        ttk.Checkbutton(frame_del_cond, text="조건부 삭제 사용", variable=self.use_conditional_delete, command=toggle_cond_del).pack(side=tk.LEFT)
        ttk.Label(frame_del_cond, text="조건 태그 (|로 구분):").pack(side=tk.LEFT, padx=5)
        self.cond_del_entry = ttk.Entry(frame_del_cond, state=tk.DISABLED)
        self.cond_del_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # --- 실행 버튼 ---
        btn_frame = ttk.Frame(container)
        btn_frame.pack(anchor=tk.W, pady=10)
        
        ttk.Button(btn_frame, text="미리보기", command=self.preview_tags).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="태그 처리 실행", command=self.process_tags).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="실행 취소", command=self.undo_tags, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        
        # --- 결과 텍스트 ---
        ttk.Label(container, text="결과 로그:").pack(anchor=tk.W)
        self.tag_text = scrolledtext.ScrolledText(container, height=15)
        self.tag_text.pack(fill=tk.BOTH, expand=True)

    def create_converter_tab(self, notebook):
        frame = ttk.Frame(notebook, padding="10")
        notebook.add(frame, text="이미지 변환")
        
        # Instantiate the converter GUI embedded
        self.converter_gui = ImageConverterGUI(frame, core_var=self.core_var, is_standalone=False)

    def create_duplicate_tab(self, notebook):
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="중복/유사 이미지")
        self.duplicate_gui = DuplicateFinderGUI(frame, folder_path_var=self.folder_path_var, core_var=self.core_var)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path = folder
            self.folder_path_var.set(folder)
            self.folder_label.config(text=folder)

    def select_csv_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if file_path:
            self.csv_file_path.set(file_path)

    def load_csv_tags(self) -> set:
        """CSV 파일을 읽어 선택된 카테고리에 해당하는 태그 세트 반환"""
        csv_path = self.csv_file_path.get()
        if not csv_path or not os.path.exists(csv_path):
            return set()
            
        category_id = self.csv_category.get().strip()
        tags_set = set()
        
        import csv
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        # 첫 번째 열: 태그, 두 번째 열: 카테고리
                        # 정규화: 소문자화 및 언더바를 공백으로 치환하여 비교 효율 증대
                        tag = row[0].strip().lower().replace('_', ' ')
                        cat = row[1].strip()
                        if cat == category_id:
                            tags_set.add(tag)
        except Exception as e:
            print(f"CSV 로드 오류: {e}")
            
        return tags_set

    def check_folder(self):
        if not self.folder_path:
            messagebox.showwarning("경고", "먼저 작업 폴더를 선택하세요.")
            return False
        return True
    
    def undo_tags(self):
        if not self.check_folder():
            return
            
        result = messagebox.askyesno("확인", "마지막 태그 처리 작업을 취소하시겠습니까?")
        if not result:
            return
            
        success, fail, logs = TagProcessor.undo_last_processing(self.folder_path)
        
        self.tag_text.delete(1.0, tk.END)
        self.tag_text.insert(tk.END, f"복구 성공: {success}개, 실패: {fail}개\n\n")
        self.tag_text.insert(tk.END, "\n".join(logs))
        
        if success > 0:
            messagebox.showinfo("완료", f"실행 취소 완료\n복구: {success}개, 실패: {fail}개")
        elif not logs or "실행 취소할" in logs[0]:
             messagebox.showinfo("알림", "실행 취소할 내역이 없습니다.")
        else:
             messagebox.showerror("오류", "실행 취소 중 오류가 발생했습니다.")

    def preview_rename(self):
        if not self.check_folder():
            return
        
        try:
            base_name = self.rename_base.get().strip()
            start_num = int(self.rename_start.get())
            digits = int(self.rename_digits.get())
            
            if not base_name:
                messagebox.showwarning("경고", "기본 이름을 입력하세요.")
                return
            
            preview = RenameProcessor.preview_rename(
                self.folder_path, base_name, start_num, digits, preview_count=10
            )
            
            self.rename_text.delete(1.0, tk.END)
            self.rename_text.insert(tk.END, "\n".join(preview))
            
        except ValueError:
            messagebox.showerror("오류", "시작 번호와 자릿수는 숫자여야 합니다.")
    
    def execute_rename(self):
        if not self.check_folder():
            return
        
        try:
            base_name = self.rename_base.get().strip()
            start_num = int(self.rename_start.get())
            digits = int(self.rename_digits.get())
            
            if not base_name:
                messagebox.showwarning("경고", "기본 이름을 입력하세요.")
                return
            
            result = messagebox.askyesno("확인", "파일 이름을 변경하시겠습니까?\n(실행 취소 버튼으로 되돌릴 수 있습니다)")
            if not result:
                return
            
            success, fail, logs = RenameProcessor.rename_file_pairs(
                self.folder_path, base_name, start_num, digits
            )
            
            self.rename_text.delete(1.0, tk.END)
            self.rename_text.insert(tk.END, f"성공: {success}개, 실패: {fail}개\n\n")
            self.rename_text.insert(tk.END, "\n".join(logs))
            
            messagebox.showinfo("완료", f"이름 변경 완료\n성공: {success}개, 실패: {fail}개")
            
        except ValueError:
            messagebox.showerror("오류", "시작 번호와 자릿수는 숫자여야 합니다.")
    
    def undo_rename(self):
        if not self.check_folder():
            return
        
        result = messagebox.askyesno("확인", "마지막 이름 변경을 취소하시겠습니까?")
        if not result:
            return
        
        success, fail, logs = RenameProcessor.undo_rename(self.folder_path)
        
        self.rename_text.delete(1.0, tk.END)
        self.rename_text.insert(tk.END, f"복구 성공: {success}개, 실패: {fail}개\n\n")
        self.rename_text.insert(tk.END, "\n".join(logs))
        
        if success > 0:
            messagebox.showinfo("완료", f"실행 취소 완료\n복구: {success}개, 실패: {fail}개")
        else:
            messagebox.showinfo("알림", "실행 취소할 내역이 없습니다.")
    
    def find_single_images(self):
        if not self.check_folder():
            return
        
        fm = FileManager(self.folder_path)
        self.single_files = fm.find_single_images(recursive=self.find_subdirs.get())
        
        self.single_text.delete(1.0, tk.END)
        if self.single_files:
            self.single_text.insert(tk.END, f"총 {len(self.single_files)}개의 단일 이미지 파일을 찾았습니다.\n\n")
            self.single_text.insert(tk.END, fm.get_file_list_text(self.single_files))
        else:
            self.single_text.insert(tk.END, "단일 이미지 파일이 없습니다.")
    
    def find_single_texts(self):
        if not self.check_folder():
            return
        
        fm = FileManager(self.folder_path)
        self.single_files = fm.find_single_texts(recursive=self.find_subdirs.get())
        
        self.single_text.delete(1.0, tk.END)
        if self.single_files:
            self.single_text.insert(tk.END, f"총 {len(self.single_files)}개의 단일 텍스트 파일을 찾았습니다.\n\n")
            self.single_text.insert(tk.END, fm.get_file_list_text(self.single_files))
        else:
            self.single_text.insert(tk.END, "단일 텍스트 파일이 없습니다.")
    
    def delete_single_files(self):
        if not self.single_files:
            messagebox.showwarning("경고", "먼저 단일 파일을 찾아주세요.")
            return
        
        result = messagebox.askyesno("확인", f"{len(self.single_files)}개의 파일을 삭제하시겠습니까?")
        if not result:
            return
        
        fm = FileManager(self.folder_path)
        success, fail = fm.delete_files(self.single_files)
        
        messagebox.showinfo("완료", f"삭제 완료\n성공: {success}개, 실패: {fail}개")
        self.single_files = []
        self.single_text.delete(1.0, tk.END)
        self.single_text.insert(tk.END, "파일 삭제가 완료되었습니다.")
    
    def move_single_files(self):
        if not self.single_files:
            messagebox.showwarning("경고", "먼저 단일 파일을 찾아주세요.")
            return
        
        dest_folder = filedialog.askdirectory(title="이동할 폴더 선택")
        if not dest_folder:
            return
        
        fm = FileManager(self.folder_path)
        success, fail = fm.move_files(self.single_files, dest_folder)
        
        messagebox.showinfo("완료", f"이동 완료\n성공: {success}개, 실패: {fail}개")
        self.single_files = []
        self.single_text.delete(1.0, tk.END)
        self.single_text.insert(tk.END, f"파일이 {dest_folder}로 이동되었습니다.")

    def get_tag_options(self):
        """현재 UI 설정값을 딕셔너리로 반환"""
        options = {
            'use_move_person': self.use_person_tag.get(),
            'use_move_solo': self.use_move_solo.get(), 
            
            # 누락 태그 추가 옵션
            'use_missing_tag': self.use_missing_tag.get(),
            'missing_gender': self.missing_gender.get(),
            'missing_count': self.missing_count.get(),
            
            # 태그 추가 옵션
            'use_add': self.use_add.get(),
            'add_tags': self.add_tag_entry.get().strip(),
            'use_conditional_add': self.use_conditional_add.get(),
            'condition_add_tags': self.cond_add_entry.get().strip(),
            
            'use_move_custom': self.use_custom_move.get(),
            'move_custom_tags': [t.strip() for t in self.custom_move_entry.get().split('|') if t.strip()],
            
            'use_replace': self.use_replace.get(),
            'replace_find': self.replace_find_entry.get().strip(),
            'replace_with': self.replace_with_entry.get().strip(),
            
            # 인접 태그 수정 옵션
            'use_neighbor_modify': self.use_neighbor_modify.get(),
            'neighbor_target': self.neighbor_target.get(),
            'neighbor_pos': self.neighbor_pos.get(),
            'neighbor_add_pos': self.neighbor_add_pos.get(),
            'neighbor_text': self.neighbor_text.get(),
            
            # CSV 기반 특수 처리 옵션
            'use_csv_process': self.use_csv_process.get(),
            'csv_file_path': self.csv_file_path.get(),
            'csv_category': self.csv_category.get(),
            'csv_mode': self.csv_mode.get(),
            'csv_add_pos': self.csv_add_pos.get(),
            'csv_input_text': self.csv_input_text.get(),
            'csv_tags_set': self.load_csv_tags() if self.use_csv_process.get() else set(),

            # 태그 삭제 옵션
            'use_delete': self.use_delete.get(),
            'delete_tags': [t.strip() for t in self.delete_tags_entry.get().split('|') if t.strip()],
            'use_conditional_delete': self.use_conditional_delete.get(),
            'condition_delete_tags': self.cond_del_entry.get().strip(),
        }
        return options

    def preview_tags(self):
        if not self.check_folder():
            return
        
        # txt 파일 가져오기
        paired_files = get_paired_files(self.folder_path, recursive=self.tag_find_subdirs.get())
        text_files = [txt for _, txt in paired_files]
        
        if not text_files:
            messagebox.showinfo("알림", "처리할 txt 파일이 없습니다.")
            return
        
        options = self.get_tag_options()
        
        # 옵션 유효성 검사
        if not any([options['use_move_person'], options['use_move_solo'], options['use_move_custom'], 
                   options['use_replace'], options['use_delete'], options['use_add'], options['use_missing_tag'],
                   options['use_neighbor_modify'], options['use_csv_process']]):
            messagebox.showwarning("경고", "최소한 하나의 기능을 선택해주세요.")
            return
            
        preview = TagProcessor.preview_tag_processing(text_files, options, preview_count=10)
        
        self.tag_text.delete(1.0, tk.END)
        self.tag_text.insert(tk.END, "\n".join(preview))
    
    def process_tags(self):
        if not self.check_folder():
            return
        
        options = self.get_tag_options()
        
        # 옵션 유효성 검사
        if not any([options['use_move_person'], options['use_move_solo'], options['use_move_custom'], 
                   options['use_replace'], options['use_delete'], options['use_add'], options['use_missing_tag'],
                   options['use_neighbor_modify'], options['use_csv_process']]):
            messagebox.showwarning("경고", "최소한 하나의 기능을 선택해주세요.")
            return

        confirm_msg = "선택한 옵션으로 태그 처리를 진행하시겠습니까?\n\n"
        if options['use_replace']: confirm_msg += "- 태그 치환\n"
        if options['use_neighbor_modify']: confirm_msg += f"- 인접 태그 수정 (기준: {options['neighbor_target']})\n"
        if options['use_csv_process']: confirm_msg += f"- CSV 기반 특수 처리 (종류: {options['csv_category']})\n"
        if options['use_delete']: 
            confirm_msg += "- 태그 삭제"
            if options['use_conditional_delete']: confirm_msg += " (조건부)"
            confirm_msg += "\n"
        if options['use_missing_tag']: confirm_msg += f"- 누락된 인원수 태그 추가 ({options['missing_count']}{options['missing_gender']})\n"
        if options['use_move_person']: confirm_msg += "- 인원수 태그 이동\n"
        if options['use_move_solo']: confirm_msg += "- 'solo' 태그 이동\n"
        if options['use_add']: 
            confirm_msg += "- 태그 추가"
            if options['use_conditional_add']: confirm_msg += " (조건부)"
            confirm_msg += "\n"
        if options['use_move_custom']: confirm_msg += "- 추가 태그 이동\n"
        
        result = messagebox.askyesno("확인", confirm_msg)
        if not result:
            return
        
        # txt 파일 가져오기
        paired_files = get_paired_files(self.folder_path, recursive=self.tag_find_subdirs.get())
        text_files = [txt for _, txt in paired_files]
        
        if not text_files:
            messagebox.showinfo("알림", "처리할 txt 파일이 없습니다.")
            return
        
        num_cores = self.core_var.get()
        success, fail, logs = TagProcessor.process_folder(text_files, options, num_cores, folder_path=self.folder_path)
        
        self.tag_text.delete(1.0, tk.END)
        self.tag_text.insert(tk.END, f"성공: {success}개, 실패: {fail}개\n\n")
        self.tag_text.insert(tk.END, "\n".join(logs))
        
        messagebox.showinfo("완료", f"태그 처리 완료\n성공: {success}개, 실패: {fail}개")

    def save_settings(self):
        """현재 설정을 JSON 파일로 저장"""
        settings = {
            "folder_path": self.folder_path,
            "core_var": self.core_var.get(),
            "rename_base": self.rename_base.get(),
            "rename_start": self.rename_start.get(),
            "rename_digits": self.rename_digits.get(),
            
            # 태그 탭 설정
            "use_person_tag": self.use_person_tag.get(),
            "use_move_solo": self.use_move_solo.get(), 
            "use_missing_tag": self.use_missing_tag.get(),
            "missing_gender": self.missing_gender.get(),
            "missing_count": self.missing_count.get(),
            
            "use_add": self.use_add.get(),
            "add_tag_entry": self.add_tag_entry.get(),
            "use_conditional_add": self.use_conditional_add.get(),
            "condition_add_tags": self.cond_add_entry.get(),
            
            "use_custom_move": self.use_custom_move.get(),
            "custom_move_entry": self.custom_move_entry.get(),
            "use_replace": self.use_replace.get(),
            "replace_find_entry": self.replace_find_entry.get(),
            "replace_with_entry": self.replace_with_entry.get(),
            
            "use_neighbor_modify": self.use_neighbor_modify.get(),
            "neighbor_target": self.neighbor_target.get(),
            "neighbor_pos": self.neighbor_pos.get(),
            "neighbor_add_pos": self.neighbor_add_pos.get(),
            "neighbor_text": self.neighbor_text.get(),
            
            "use_csv_process": self.use_csv_process.get(),
            "csv_file_path": self.csv_file_path.get(),
            "csv_category": self.csv_category.get(),
            "csv_mode": self.csv_mode.get(),
            "csv_add_pos": self.csv_add_pos.get(),
            "csv_input_text": self.csv_input_text.get(),

            # 중복 찾기 탭 설정
            "dup_use_independent": self.duplicate_gui.use_independent_path.get(),
            "dup_independent_path": self.duplicate_gui.independent_folder_path.get(),

            "use_delete": self.use_delete.get(),
            "delete_tags_entry": self.delete_tags_entry.get(),
            "use_conditional_delete": self.use_conditional_delete.get(),
            "condition_delete_tags": self.cond_del_entry.get(),
            
            "find_subdirs": self.find_subdirs.get(),
            "tag_find_subdirs": self.tag_find_subdirs.get(),
        }
        
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"설정 저장 실패: {e}")

    def load_settings(self):
        """저장된 설정 불러오기"""
        if not SETTINGS_FILE.exists():
            return
            
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # 폴더 경로
            if "folder_path" in settings:
                self.folder_path = settings["folder_path"]
                self.folder_path_var.set(self.folder_path)
                if self.folder_path:
                    self.folder_label.config(text=self.folder_path)
            
            # 코어 수
            if "core_var" in settings:
                self.core_var.set(settings["core_var"])
            
            # 이름 변경 탭
            if "rename_base" in settings: 
                self.rename_base.delete(0, tk.END)
                self.rename_base.insert(0, settings["rename_base"])
            if "rename_start" in settings:
                self.rename_start.delete(0, tk.END)
                self.rename_start.insert(0, settings["rename_start"])
            if "rename_digits" in settings:
                self.rename_digits.delete(0, tk.END)
                self.rename_digits.insert(0, settings["rename_digits"])
                
            # 태그 탭
            if "use_person_tag" in settings: self.use_person_tag.set(settings["use_person_tag"])
            if "use_move_solo" in settings: self.use_move_solo.set(settings["use_move_solo"]) 
            if "use_missing_tag" in settings: self.use_missing_tag.set(settings["use_missing_tag"])
            if "missing_gender" in settings: self.missing_gender.set(settings["missing_gender"])
            if "missing_count" in settings: self.missing_count.set(settings["missing_count"])
            
            if "use_add" in settings: self.use_add.set(settings["use_add"])
            if "add_tag_entry" in settings:
                self.add_tag_entry.delete(0, tk.END)
                self.add_tag_entry.insert(0, settings["add_tag_entry"])
            if "use_conditional_add" in settings: 
                self.use_conditional_add.set(settings["use_conditional_add"])
                if settings["use_conditional_add"]:
                    self.cond_add_entry.config(state=tk.NORMAL)
            if "condition_add_tags" in settings:
                self.cond_add_entry.delete(0, tk.END)
                self.cond_add_entry.insert(0, settings["condition_add_tags"])
            
            if "use_custom_move" in settings: self.use_custom_move.set(settings["use_custom_move"])
            if "custom_move_entry" in settings:
                self.custom_move_entry.delete(0, tk.END)
                self.custom_move_entry.insert(0, settings["custom_move_entry"])
            if "use_replace" in settings: self.use_replace.set(settings["use_replace"])
            if "replace_find_entry" in settings:
                self.replace_find_entry.delete(0, tk.END)
                self.replace_find_entry.insert(0, settings["replace_find_entry"])
            if "replace_with_entry" in settings:
                self.replace_with_entry.delete(0, tk.END)
                self.replace_with_entry.insert(0, settings["replace_with_entry"])
            
            if "use_neighbor_modify" in settings: self.use_neighbor_modify.set(settings["use_neighbor_modify"])
            if "neighbor_target" in settings: self.neighbor_target.set(settings["neighbor_target"])
            if "neighbor_pos" in settings: self.neighbor_pos.set(settings["neighbor_pos"])
            if "neighbor_add_pos" in settings: self.neighbor_add_pos.set(settings["neighbor_add_pos"])
            if "neighbor_text" in settings: self.neighbor_text.set(settings["neighbor_text"])
            
            if "use_csv_process" in settings: self.use_csv_process.set(settings["use_csv_process"])
            if "csv_file_path" in settings: self.csv_file_path.set(settings["csv_file_path"])
            if "csv_category" in settings: self.csv_category.set(settings["csv_category"])
            if "csv_mode" in settings: self.csv_mode.set(settings["csv_mode"])
            if "csv_add_pos" in settings: self.csv_add_pos.set(settings["csv_add_pos"])
            if "csv_input_text" in settings: self.csv_input_text.set(settings["csv_input_text"])

            if "dup_use_independent" in settings:
                self.duplicate_gui.use_independent_path.set(settings["dup_use_independent"])
                self.duplicate_gui.toggle_ui_state()
            if "dup_independent_path" in settings:
                self.duplicate_gui.independent_folder_path.set(settings["dup_independent_path"])

            if "use_delete" in settings: self.use_delete.set(settings["use_delete"])
            if "delete_tags_entry" in settings:
                self.delete_tags_entry.delete(0, tk.END)
                self.delete_tags_entry.insert(0, settings["delete_tags_entry"])
            if "use_conditional_delete" in settings: 
                self.use_conditional_delete.set(settings["use_conditional_delete"])
                if settings["use_conditional_delete"]:
                    self.cond_del_entry.config(state=tk.NORMAL)
            if "condition_delete_tags" in settings:
                self.cond_del_entry.delete(0, tk.END)
                self.cond_del_entry.insert(0, settings["condition_delete_tags"])
            
            if "find_subdirs" in settings:
                self.find_subdirs.set(settings["find_subdirs"])
            if "tag_find_subdirs" in settings:
                self.tag_find_subdirs.set(settings["tag_find_subdirs"])
                
        except Exception as e:
            print(f"설정 로드 실패: {e}")

    def on_closing(self):
        """프로그램 종료 시 호출"""
        self.save_settings()
        if hasattr(self, 'converter_gui'):
            self.converter_gui.on_close()
        self.root.destroy()


def main():
    try:
        os.makedirs('logs', exist_ok=True)
        logger.setup_logger(log_level='INFO', log_file='logs/converter.log')
    except Exception as e:
        print(f"로거 초기화 실패: {e}")

    root = tk.Tk()
    app = DatasetOrganizerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
