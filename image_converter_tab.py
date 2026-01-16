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
        ttk.Entry(self.io_frame, textvariable=self.target_folder_var, width=40).grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Button(self.io_frame, text="찾아보기", command=self.select_target_folder).grid(row=1, column=2)

        # --- Naming Suffix Widgets ---
        self.use_suffix_var = tk.BooleanVar(value=True)
        self.suffix_text_var = tk.StringVar(value="_converted")
        
        suffix_frame = ttk.Frame(self.io_frame)
        suffix_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=2)
        
        ttk.Checkbutton(suffix_frame, text="파일명 접미사 추가:", variable=self.use_suffix_var, command=self.toggle_suffix_entry).pack(side=tk.LEFT)
        self.suffix_entry = ttk.Entry(suffix_frame, textvariable=self.suffix_text_var, width=15)
        self.suffix_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(suffix_frame, text="(예: image_converted.png)").pack(side=tk.LEFT)

        self.io_frame.columnconfigure(1, weight=1)

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

    def toggle_suffix_entry(self):
        state = tk.NORMAL if self.use_suffix_var.get() else tk.DISABLED
        self.suffix_entry.config(state=state)

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

        self.toggle_quality_spinbox()
        self.toggle_resize_spinbox()
        self.toggle_suffix_entry()

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
        
        settings_manager.save_settings(self.settings)

    def update_progress(self, current, total, current_file):
        if self.progress_rate_limiter.is_allowed():
            progress_percent = (current / total) * 100
            self.progress_bar['value'] = progress_percent
            self.status_label_var.set(f"처리 중: [{current}/{total}] {os.path.basename(current_file)}")
            self.parent.update_idletasks()

    def start_conversion(self):
        self.save_settings_from_gui()
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
        self.status_label_var.set(f"변환 완료! 성공: {len(results.get('success',[]))}, 실패: {len(results.get('error',[]))}, 건너뜀: {len(results.get('skipped',[]))}")
        messagebox.showinfo("완료", "이미지 변환이 완료되었습니다.")

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
