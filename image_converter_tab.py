import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os

# Assuming other modules are in the same directory
import image_settings as settings_manager
import image_file_utils as file_manager
import image_converter_engine as converter_engine
from app_logger import logger, setup_gui_logging_handler
from image_utils import RateLimiter
from utils import ScrollableFrame

class ImageConverterGUI:
    def __init__(self, parent, core_var=None, is_standalone=True):
        self.parent = parent
        self.core_var = core_var
        self.is_standalone = is_standalone
        
        if self.is_standalone:
            self.parent.title("이미지 일괄 변환기")
            self.parent.geometry("1000x850") 
            self.parent.minsize(800, 600)
            if self.core_var is None:
                self.core_var = tk.IntVar(value=os.cpu_count())

        self.settings = settings_manager.load_settings()
        self.conversion_thread = None
        self.is_running = False
        self.is_paused = False
        self.last_conversion_results = []

        self.progress_rate_limiter = RateLimiter(max_calls_per_second=10)
        
        # 새 기능 변수
        self.output_to_input_var = tk.BooleanVar(value=False)
        self.input_conflict_mode_var = tk.StringVar(value='rename')
        self.delete_original_var = tk.BooleanVar(value=False)
        self.delete_confirm_popup_var = tk.StringVar(value='show')  # 'show' | 'hide'
        
        # Checkbox variables for input extensions
        self.input_ext_vars = {} 
        self.all_ext_var = tk.BooleanVar(value=True)

        self.setup_main_layout()
        self.setup_widgets()
        self.load_settings_to_gui()
        
        # Setup logging to GUI
        setup_gui_logging_handler(logger, self.log_text)

    def setup_main_layout(self):
        # 전체 스크롤 적용
        scroll = ScrollableFrame(self.parent)
        scroll.pack(fill=tk.BOTH, expand=True)
        main_content = scroll.scrollable_frame

        # PanedWindow로 좌우 분할
        paned_window = ttk.PanedWindow(main_content, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel for settings (weight=1: 덜 늘어남)
        settings_panel = ttk.Frame(paned_window)
        paned_window.add(settings_panel, weight=1)

        # Right panel for logs and progress (weight=3: 더 많이 늘어남)
        right_panel = ttk.Frame(paned_window)
        paned_window.add(right_panel, weight=3)

        # --- Create Frames for each section ---
        self.io_frame = ttk.LabelFrame(settings_panel, text="입력/출력 설정", padding="10")
        self.io_frame.pack(fill=tk.X, pady=5)

        self.filter_frame = ttk.LabelFrame(settings_panel, text="입력 파일 필터", padding="10")
        self.filter_frame.pack(fill=tk.X, pady=5)

        self.format_frame = ttk.LabelFrame(settings_panel, text="포맷 설정", padding="10")
        self.format_frame.pack(fill=tk.X, pady=5)

        self.conversion_opts_frame = ttk.LabelFrame(settings_panel, text="변환 옵션", padding="10")
        self.conversion_opts_frame.pack(fill=tk.X, pady=5)

        self.metadata_frame = ttk.LabelFrame(settings_panel, text="메타데이터 설정", padding="10")
        self.metadata_frame.pack(fill=tk.X, pady=5)
        
        # 처리 설정 프레임 제거 (메인 UI 통합)

        self.action_frame = ttk.Frame(settings_panel, padding="10")
        self.action_frame.pack(fill=tk.X, pady=10)

        # --- Right Panel Widgets ---
        self.progress_frame = ttk.LabelFrame(right_panel, text="진행 상황", padding="10")
        self.progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.log_frame = ttk.LabelFrame(right_panel, text="실시간 로그", padding="10")
        self.log_frame.pack(fill=tk.BOTH, expand=True)

    def setup_widgets(self):
        # --- I/O Widgets ---
        self.source_folder_var = tk.StringVar()
        self.target_folder_var = tk.StringVar()
        ttk.Label(self.io_frame, text="입력 폴더:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.io_frame, textvariable=self.source_folder_var, width=40).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(self.io_frame, text="찾아보기", command=self.select_source_folder).grid(row=0, column=2)

        ttk.Label(self.io_frame, text="출력 폴더:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.target_folder_entry = ttk.Entry(self.io_frame, textvariable=self.target_folder_var, width=40)
        self.target_folder_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.target_folder_browse_btn = ttk.Button(self.io_frame, text="찾아보기", command=self.select_target_folder)
        self.target_folder_browse_btn.grid(row=1, column=2)

        # --- 입력폴더에 출력 옵션 ---
        output_to_input_cb = ttk.Checkbutton(
            self.io_frame, text="입력 폴더에 출력",
            variable=self.output_to_input_var,
            command=self.toggle_output_to_input
        )
        output_to_input_cb.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))

        # 충돌 처리 옵션 프레임 (output_to_input 활성 시만 enabled)
        self.conflict_mode_frame = ttk.Frame(self.io_frame)
        self.conflict_mode_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=(20, 0), pady=(0, 2))
        ttk.Label(self.conflict_mode_frame, text="이름 충돌 시:").pack(side=tk.LEFT, padx=(0, 6))
        self.rb_conflict_skip = ttk.Radiobutton(
            self.conflict_mode_frame, text="패스",
            variable=self.input_conflict_mode_var, value='skip'
        )
        self.rb_conflict_skip.pack(side=tk.LEFT, padx=3)
        self.rb_conflict_overwrite = ttk.Radiobutton(
            self.conflict_mode_frame, text="덮어쓰기",
            variable=self.input_conflict_mode_var, value='overwrite'
        )
        self.rb_conflict_overwrite.pack(side=tk.LEFT, padx=3)
        self.rb_conflict_rename = ttk.Radiobutton(
            self.conflict_mode_frame, text="숫자 추가",
            variable=self.input_conflict_mode_var, value='rename'
        )
        self.rb_conflict_rename.pack(side=tk.LEFT, padx=3)

        # --- Naming Suffix Widgets ---
        self.use_suffix_var = tk.BooleanVar(value=True)
        self.suffix_text_var = tk.StringVar(value="_converted")
        
        suffix_frame = ttk.Frame(self.io_frame)
        suffix_frame.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=2)
        
        ttk.Checkbutton(suffix_frame, text="파일명 접미사 추가:", variable=self.use_suffix_var, command=self.toggle_suffix_entry).pack(side=tk.LEFT)
        self.suffix_entry = ttk.Entry(suffix_frame, textvariable=self.suffix_text_var, width=15)
        self.suffix_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(suffix_frame, text="(예: image_converted.png)").pack(side=tk.LEFT)

        self.io_frame.columnconfigure(1, weight=1)

        # 초기 상태 반영
        self.toggle_output_to_input()

        # --- Filter Widgets ---
        # All Checkbox
        ttk.Checkbutton(self.filter_frame, text="전체 (All)", variable=self.all_ext_var, command=self.toggle_all_extensions).pack(anchor=tk.W)
        
        # Individual Checkboxes
        ext_container = ttk.Frame(self.filter_frame)
        ext_container.pack(fill=tk.X, pady=2)
        
        extensions = ["JPG", "PNG", "WEBP", "GIF", "BMP", "TIFF"]
        for i, ext in enumerate(extensions):
            var = tk.BooleanVar(value=True)
            self.input_ext_vars[ext] = var
            cb = ttk.Checkbutton(ext_container, text=ext, variable=var, command=lambda: self.all_ext_var.set(False))
            cb.grid(row=0, column=i, sticky=tk.W, padx=5)

        # --- Format Widgets ---
        self.target_format_var = tk.StringVar()
        formats = ["PNG", "JPG", "WEBP", "GIF"]
        for i, fmt in enumerate(formats):
            value = fmt.lower()
            if value == "jpg":
                value = "jpeg"
            ttk.Radiobutton(self.format_frame, text=fmt, variable=self.target_format_var, value=value).pack(side=tk.LEFT, padx=5)

        # --- Conversion Options Widgets ---
        self.quality_enabled_var = tk.BooleanVar()
        self.quality_value_var = tk.IntVar()
        ttk.Checkbutton(self.conversion_opts_frame, text="품질 설정 사용", variable=self.quality_enabled_var, command=self.toggle_quality_spinbox).grid(row=0, column=0, sticky=tk.W)
        self.quality_spinbox = ttk.Spinbox(self.conversion_opts_frame, from_=1, to=100, textvariable=self.quality_value_var, width=5)
        self.quality_spinbox.grid(row=0, column=1, sticky=tk.W, padx=5)

        self.resize_enabled_var = tk.BooleanVar()
        self.resize_scale_var = tk.DoubleVar()
        ttk.Checkbutton(self.conversion_opts_frame, text="리사이즈 사용", variable=self.resize_enabled_var, command=self.toggle_resize_spinbox).grid(row=1, column=0, sticky=tk.W)
        self.resize_spinbox = ttk.Spinbox(self.conversion_opts_frame, from_=0.1, to=5.0, increment=0.1, textvariable=self.resize_scale_var, width=5)
        self.resize_spinbox.grid(row=1, column=1, sticky=tk.W, padx=5)

        # --- Metadata Widgets ---
        self.preserve_metadata_var = tk.BooleanVar()
        ttk.Checkbutton(self.metadata_frame, text="메타데이터 보존", variable=self.preserve_metadata_var).pack(anchor=tk.W)

        # --- Action Buttons ---
        self.start_button = ttk.Button(self.action_frame, text="변환 시작", command=self.start_conversion)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.pause_button = ttk.Button(self.action_frame, text="일시정지", command=self.pause_conversion, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.stop_button = ttk.Button(self.action_frame, text="중지", command=self.stop_conversion, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.undo_button = ttk.Button(self.action_frame, text="마지막 작업 취소", command=self.undo_last_conversion, state=tk.DISABLED)
        self.undo_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # --- 변환 후 원본 삭제 옵션 ---
        delete_frame = ttk.LabelFrame(self.action_frame.master, text="원본 삭제 설정", padding="6")
        delete_frame.pack(fill=tk.X, pady=(0, 4))

        delete_cb = ttk.Checkbutton(
            delete_frame, text="변환 후 원본 삭제",
            variable=self.delete_original_var,
            command=self.toggle_delete_options
        )
        delete_cb.pack(anchor=tk.W)

        self.delete_opts_frame = ttk.Frame(delete_frame)
        self.delete_opts_frame.pack(anchor=tk.W, padx=(20, 0))
        ttk.Label(self.delete_opts_frame, text="삭제 전 확인:").pack(side=tk.LEFT, padx=(0, 6))
        self.rb_delete_show = ttk.Radiobutton(
            self.delete_opts_frame, text="확인 팝업 표시",
            variable=self.delete_confirm_popup_var, value='show'
        )
        self.rb_delete_show.pack(side=tk.LEFT, padx=3)
        self.rb_delete_hide = ttk.Radiobutton(
            self.delete_opts_frame, text="바로 삭제",
            variable=self.delete_confirm_popup_var, value='hide'
        )
        self.rb_delete_hide.pack(side=tk.LEFT, padx=3)

        # 초기 상태
        self.toggle_delete_options()

        # --- Progress Bar and Labels ---
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(fill=tk.X, expand=True, pady=5)
        self.status_label_var = tk.StringVar()
        self.status_label_var.set("대기 중...")
        ttk.Label(self.progress_frame, textvariable=self.status_label_var).pack(anchor=tk.W)

        # --- Log Text Area ---
        self.log_text = tk.Text(self.log_frame, wrap=tk.WORD, height=10, state=tk.DISABLED)
        log_scrollbar = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text['yscrollcommand'] = log_scrollbar.set
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def toggle_output_to_input(self):
        """'입력 폴더에 출력' 체크박스 상태에 따라 출력폴더 입력·충돌옵션·접미사연동 제어."""
        is_checked = self.output_to_input_var.get()
        # 출력폴더 입력란/버튼 비활성화
        folder_state = tk.DISABLED if is_checked else tk.NORMAL
        self.target_folder_entry.config(state=folder_state)
        self.target_folder_browse_btn.config(state=folder_state)
        # 충돌 처리 라디오버튼 활성/비활성
        # 단, 접미사가 켜져 있으면 충돌 자체가 사실상 발생하지 않으므로 비활성
        use_suffix = self.use_suffix_var.get() if hasattr(self, 'use_suffix_var') else False
        conflict_state = tk.DISABLED if (not is_checked or use_suffix) else tk.NORMAL
        for rb in (self.rb_conflict_skip, self.rb_conflict_overwrite, self.rb_conflict_rename):
            rb.config(state=conflict_state)

    def toggle_suffix_entry(self):
        state = tk.NORMAL if self.use_suffix_var.get() else tk.DISABLED
        self.suffix_entry.config(state=state)
        # 접미사 켜지면 충돌옵션은 의미없으므로 비활성
        if self.output_to_input_var.get():
            conflict_state = tk.DISABLED if self.use_suffix_var.get() else tk.NORMAL
            for rb in (self.rb_conflict_skip, self.rb_conflict_overwrite, self.rb_conflict_rename):
                rb.config(state=conflict_state)

    def toggle_delete_options(self):
        """'변환 후 원본 삭제' 체크박스 상태에 따라 하위 라디오버튼 활성/비활성."""
        state = tk.NORMAL if self.delete_original_var.get() else tk.DISABLED
        self.rb_delete_show.config(state=state)
        self.rb_delete_hide.config(state=state)

    def select_source_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.source_folder_var.set(folder)

    def select_target_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.target_folder_var.set(folder)
            
    def toggle_all_extensions(self):
        state = self.all_ext_var.get()
        for var in self.input_ext_vars.values():
            var.set(state)

    def toggle_quality_spinbox(self):
        self.quality_spinbox.config(state=tk.NORMAL if self.quality_enabled_var.get() else tk.DISABLED)

    def toggle_resize_spinbox(self):
        self.resize_spinbox.config(state=tk.NORMAL if self.resize_enabled_var.get() else tk.DISABLED)

    def load_settings_to_gui(self):
        self.source_folder_var.set(self.settings['input_settings']['source_folder'])
        self.target_folder_var.set(self.settings['output_settings']['target_folder'])
        self.target_format_var.set(self.settings['output_settings']['target_format'])
        
        # Load suffix settings
        self.use_suffix_var.set(self.settings['output_settings'].get('use_suffix', True))
        self.suffix_text_var.set(self.settings['output_settings'].get('suffix_text', '_converted'))
        
        self.quality_enabled_var.set(self.settings['conversion_settings']['quality_enabled'])
        self.quality_value_var.set(self.settings['conversion_settings']['quality_value'])
        self.resize_enabled_var.set(self.settings['conversion_settings']['resize_enabled'])
        self.resize_scale_var.set(self.settings['conversion_settings']['resize_scale'])
        self.preserve_metadata_var.set(self.settings['metadata_settings']['preserve_enabled'])
        
        # Load supported formats
        saved_formats = self.settings['input_settings'].get('supported_formats', [])
        saved_formats = [fmt.lower().replace('.', '') for fmt in saved_formats]
        
        if not saved_formats or len(saved_formats) >= len(self.input_ext_vars):
            self.all_ext_var.set(True)
            for var in self.input_ext_vars.values():
                var.set(True)
        else:
            self.all_ext_var.set(False)
            for var in self.input_ext_vars.values():
                var.set(False)
            for ext, var in self.input_ext_vars.items():
                if ext.lower() in saved_formats or (ext == "JPG" and ("jpg" in saved_formats or "jpeg" in saved_formats)):
                    var.set(True)

        # 새 기능: 입력폴더에 출력
        out_settings = self.settings.get('output_settings', {})
        self.output_to_input_var.set(out_settings.get('output_to_input', False))
        self.input_conflict_mode_var.set(out_settings.get('input_conflict_mode', 'rename'))

        # 새 기능: 변환 후 원본 삭제
        del_settings = self.settings.get('delete_settings', {})
        self.delete_original_var.set(del_settings.get('delete_original', False))
        self.delete_confirm_popup_var.set(del_settings.get('delete_confirm_popup', 'show'))

        self.toggle_quality_spinbox()
        self.toggle_resize_spinbox()
        self.toggle_suffix_entry()
        self.toggle_output_to_input()
        self.toggle_delete_options()

    def save_settings_from_gui(self):
        self.settings['input_settings']['source_folder'] = self.source_folder_var.get()
        self.settings['output_settings']['target_folder'] = self.target_folder_var.get()
        self.settings['output_settings']['target_format'] = self.target_format_var.get()
        
        use_suffix = self.use_suffix_var.get()
        suffix_text = self.suffix_text_var.get()
        self.settings['output_settings']['use_suffix'] = use_suffix
        self.settings['output_settings']['suffix_text'] = suffix_text
        
        if use_suffix:
            self.settings['output_settings']['naming_pattern'] = f"{{original_name}}{suffix_text}"
        else:
            self.settings['output_settings']['naming_pattern'] = "{original_name}"

        self.settings['conversion_settings']['quality_enabled'] = self.quality_enabled_var.get()
        self.settings['conversion_settings']['quality_value'] = self.quality_value_var.get()
        self.settings['conversion_settings']['resize_enabled'] = self.resize_enabled_var.get()
        self.settings['conversion_settings']['resize_scale'] = self.resize_scale_var.get()
        self.settings['metadata_settings']['preserve_enabled'] = self.preserve_metadata_var.get()
        
        # Save supported formats
        selected_formats = []
        if self.all_ext_var.get():
            selected_formats = [f".{ext.lower()}" for ext in self.input_ext_vars.keys()]
            if ".jpg" in selected_formats:
                selected_formats.append(".jpeg")
        else:
            for ext, var in self.input_ext_vars.items():
                if var.get():
                    selected_formats.append(f".{ext.lower()}")
                    if ext == "JPG":
                        selected_formats.append(".jpeg")
        
        if not selected_formats:
            selected_formats = [".jpg", ".jpeg", ".png", ".webp"]
            
        self.settings['input_settings']['supported_formats'] = selected_formats

        # 새 기능: 입력폴더에 출력
        self.settings['output_settings']['output_to_input'] = self.output_to_input_var.get()
        self.settings['output_settings']['input_conflict_mode'] = self.input_conflict_mode_var.get()

        # 새 기능: 변환 후 원본 삭제
        if 'delete_settings' not in self.settings:
            self.settings['delete_settings'] = {}
        self.settings['delete_settings']['delete_original'] = self.delete_original_var.get()
        self.settings['delete_settings']['delete_confirm_popup'] = self.delete_confirm_popup_var.get()
        
        settings_manager.save_settings(self.settings)

    def update_progress(self, current, total, current_file):
        if self.progress_rate_limiter.is_allowed():
            progress_percent = (current / total) * 100
            self.progress_bar['value'] = progress_percent
            self.status_label_var.set(f"처리 중: [{current}/{total}] {os.path.basename(current_file)}")
            self.parent.update_idletasks()

    def start_conversion(self):
        self.save_settings_from_gui()

        # output_to_input 모드면 validate용 target_folder를 source로 임시 대입
        if self.settings['output_settings'].get('output_to_input', False):
            self.settings['output_settings']['target_folder'] = self.settings['input_settings']['source_folder']

        is_valid, errors = settings_manager.validate_settings(self.settings)
        if not is_valid:
            messagebox.showerror("설정 오류", "\n".join(errors))
            return

        source_folder = self.settings['input_settings']['source_folder']
        supported_formats = self.settings['input_settings']['supported_formats']

        # Inject core count from main app
        if self.core_var:
            num_cores = self.core_var.get()
            self.settings['processing_settings']['multiprocessing_enabled'] = num_cores > 1
            self.settings['processing_settings']['max_workers'] = num_cores
        
        logger.info(f"변환 대상 확장자: {', '.join(supported_formats)}")
        logger.info(f"사용 코어 수: {self.settings['processing_settings']['max_workers']}")
        
        file_list = file_manager.scan_directory(source_folder, supported_formats)

        if not file_list:
            messagebox.showinfo("정보", "선택된 폴더에서 변환할 파일을 찾을 수 없습니다.\n입력 필터 설정을 확인해주세요.")
            return

        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        self.undo_button.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.last_conversion_results = []

        control_callbacks = {
            'check_stop': lambda: not self.is_running,
            'check_pause': lambda: self.is_paused
        }

        self.conversion_thread = threading.Thread(
            target=self.run_batch_conversion, 
            args=(file_list, self.settings, self.update_progress, control_callbacks),
            daemon=True
        )
        self.conversion_thread.start()

    def run_batch_conversion(self, file_list, settings, progress_callback, control_callbacks):
        results = converter_engine.batch_convert_images(file_list, settings, progress_callback, control_callbacks)
        self.parent.after(0, self.conversion_finished, results)

    def conversion_finished(self, results):
        self.last_conversion_results = results.get('success', [])
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        if self.last_conversion_results:
            self.undo_button.config(state=tk.NORMAL)

        success_count = len(results.get('success', []))
        error_count = len(results.get('error', []))
        skipped_count = len(results.get('skipped', []))
        self.status_label_var.set(
            f"변환 완료! 성공: {success_count}, 실패: {error_count}, 건너뜀: {skipped_count}"
        )

        # 원본 삭제 기능
        if self.delete_original_var.get() and results.get('original_paths'):
            original_paths = results['original_paths']
            orig_count = len(original_paths)
            orig_size = sum(os.path.getsize(p) for p in original_paths if os.path.exists(p))
            conv_size = sum(
                os.path.getsize(r['output'])
                for r in results.get('success', [])
                if os.path.exists(r.get('output', ''))
            )

            summary_msg = (
                f"[변환 결과 요약]\n"
                f"  변환 전 원본:  {orig_count}개  /  {self._fmt_size(orig_size)}\n"
                f"  변환 완료:     {success_count}개  /  {self._fmt_size(conv_size)}\n\n"
            )
            logger.info(summary_msg.strip(), module="delete_original")

            if self.delete_confirm_popup_var.get() == 'show':
                answer = messagebox.askyesno(
                    "원본 삭제 확인",
                    summary_msg + "원본 파일을 삭제하시겠습니까?\n\n"
                    "  [예] → 원본 삭제\n  [아니오] → 원본 유지"
                )
                if answer:
                    self._delete_original_files(original_paths)
                else:
                    logger.info("사용자가 원본 유지를 선택했습니다.", module="delete_original")
                    messagebox.showinfo("완료", "이미지 변환이 완료되었습니다.\n원본 파일은 유지됩니다.")
                    return
            else:
                # 확인 없이 바로 삭제
                self._delete_original_files(original_paths)
                return

        messagebox.showinfo("완료", "이미지 변환이 완료되었습니다.")

    def _fmt_size(self, size_bytes: int) -> str:
        """바이트를 읽기 쉬운 단위로 변환."""
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def _delete_original_files(self, original_paths: list):
        """원본 파일 목록을 삭제하고 결과를 로그/팝업으로 알립니다."""
        deleted_count = 0
        failed_count = 0
        for path in original_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"원본 삭제: {path}", module="delete_original")
                    deleted_count += 1
            except OSError as e:
                logger.error(f"원본 삭제 실패: {path} - {e}", module="delete_original")
                failed_count += 1
        msg = f"원본 파일 {deleted_count}개를 삭제했습니다."
        if failed_count:
            msg += f"\n삭제 실패: {failed_count}개 (로그 확인)"
        logger.info(msg, module="delete_original")
        messagebox.showinfo("완료", f"이미지 변환이 완료되었습니다.\n{msg}")

    def undo_last_conversion(self):
        if not self.last_conversion_results:
            messagebox.showinfo("정보", "취소할 작업이 없습니다.")
            return

        msg = f"{len(self.last_conversion_results)}개의 파일을 삭제합니다. 계속하시겠습니까?"
        if messagebox.askyesno("마지막 작업 취소", msg):
            deleted_count = 0
            for result in self.last_conversion_results:
                try:
                    if os.path.exists(result['output']):
                        os.remove(result['output'])
                        logger.info(f"파일 삭제: {result['output']}", module="undo")
                        deleted_count += 1
                except OSError as e:
                    logger.error(f"파일 삭제 실패: {result['output']} - {str(e)}", module="undo")
            
            messagebox.showinfo("완료", f"{deleted_count}개의 파일을 삭제했습니다.")
            self.last_conversion_results = []
            self.undo_button.config(state=tk.DISABLED)

    def pause_conversion(self):
        if self.is_paused:
            self.is_paused = False
            self.pause_button.config(text="일시정지")
            logger.info("변환을 재개합니다.")
        else:
            self.is_paused = True
            self.pause_button.config(text="재개")
            logger.info("변환을 일시정지합니다.")

    def stop_conversion(self):
        if self.is_running:
            self.is_running = False 
            logger.info("변환 중지를 요청했습니다. 현재 파일 완료 후 중지됩니다.")
            self.stop_button.config(state=tk.DISABLED)

    def on_close(self):
        self.save_settings_from_gui()
        if self.is_standalone:
            self.parent.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = ImageConverterGUI(root, is_standalone=True)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
