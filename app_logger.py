import logging
import logging.handlers
import datetime
import psutil
import threading
import time
import os

class ImageConverterLogger:
    def __init__(self, name='ImageConverter'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.log_stream = None  # For GUI handler
        self.statistics = {
            'start_time': None,
            'end_time': None,
            'total_files': 0,
            'converted_files': 0,
            'failed_files': 0,
            'skipped_files': 0,
            'total_processing_time': 0,
            'metadata_preserved': 0,
            'metadata_failed': 0,
        }
        self.file_handler = None
        self.gui_handler = None

    def setup_logger(self, log_level: str = 'INFO', log_file: str = None):
        # Remove existing handlers to avoid duplication
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(mod)s] %(message)s', '%Y-%m-%d %H:%M:%S')

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File Handler (Daily Log)
        if log_file:
            # log_file 인자가 들어오더라도 날짜 기반 파일명으로 덮어씀 (일관성 유지)
            log_dir = os.path.dirname(log_file) if os.path.dirname(log_file) else 'logs'
        else:
            log_dir = 'logs'
            
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        today_str = datetime.datetime.now().strftime('%Y-%m-%d')
        daily_log_file = os.path.join(log_dir, f"app_{today_str}.log")
        
        self.file_handler = logging.handlers.RotatingFileHandler(daily_log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        self.file_handler.setLevel(log_level)
        self.file_handler.setFormatter(formatter)
        self.logger.addHandler(self.file_handler)

    def setup_gui_logging_handler(self, text_widget):
        self.log_stream = GuiLoggingStream(text_widget)
        self.gui_handler = logging.StreamHandler(self.log_stream)
        self.gui_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%H:%M:%S')
        self.gui_handler.setFormatter(formatter)
        self.logger.addHandler(self.gui_handler)

    def reset_statistics(self):
        self.statistics = {
            'start_time': time.time(),
            'end_time': None,
            'total_files': 0,
            'converted_files': 0,
            'failed_files': 0,
            'skipped_files': 0,
            'total_processing_time': 0,
            'metadata_preserved': 0,
            'metadata_failed': 0,
        }

    def log(self, level, message, module='main'):
        self.logger.log(level, message, extra={'custom_module': module})

    def debug(self, message, module='main'):
        self.logger.debug(message, extra={'custom_module': module})

    def info(self, message, module='main'):
        self.logger.info(message, extra={'custom_module': module})

    def warning(self, message, module='main'):
        self.logger.warning(message, extra={'custom_module': module})

    def error(self, message, module='main', exc_info=False):
        self.logger.error(message, extra={'custom_module': module}, exc_info=exc_info)

    def critical(self, message, module='main', exc_info=False):
        self.logger.critical(message, extra={'custom_module': module}, exc_info=exc_info)

    def log_conversion_start(self, source_file: str, target_format: str):
        self.info(f'이미지 변환 시작: {source_file} -> .{target_format}', module='converter_engine')

    def log_metadata_detection(self, metadata_types: list, file_path: str):
        if metadata_types:
            self.debug(f'{file_path}에서 다음 메타데이터 발견: {", ".join(metadata_types)}', module='metadata_handler')
        else:
            self.debug(f'{file_path}에서 메타데이터를 찾을 수 없음', module='metadata_handler')

    def log_performance_stats(self, processing_time: float, memory_usage: int):
        self.debug(f'처리 시간: {processing_time:.2f}초, 메모리 사용량: {memory_usage / 1024 / 1024:.2f}MB', module='performance')

    def log_error(self, error_type: str, error_msg: str, file_path: str = None):
        log_message = f'[{error_type}] {error_msg}'
        if file_path:
            log_message += f' (파일: {file_path})'
        self.error(log_message, module='error_handler')
        if file_path:
            self.statistics['failed_files'] += 1


    def get_statistics(self) -> dict:
        if self.statistics['start_time']:
            self.statistics['end_time'] = time.time()
            self.statistics['total_processing_time'] = self.statistics['end_time'] - self.statistics['start_time']
        return self.statistics

    def export_logs(self, output_path: str) -> bool:
        if not self.log_stream:
            self.error('GUI 로그 핸들러가 설정되지 않아 로그를 내보낼 수 없습니다.', module='logger_module')
            return False
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(self.log_stream.text_widget.get('1.0', 'end'))
            self.info(f'로그를 {output_path} 파일로 저장했습니다.', module='logger_module')
            return True
        except Exception as e:
            self.error(f'로그 파일 저장 중 오류 발생: {e}', module='logger_module')
            return False

class GuiLoggingStream:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.text_widget.config(state='disabled')

    def write(self, message):
        self.text_widget.config(state='normal')
        self.text_widget.insert('end', message)
        self.text_widget.see('end')
        self.text_widget.config(state='disabled')

    def flush(self):
        pass

def setup_gui_logging_handler(logger_instance, text_widget) -> logging.Handler:
    handler = GuiLoggingStream(text_widget)
    log_handler = logging.StreamHandler(handler)
    log_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%H:%M:%S')
    log_handler.setFormatter(formatter)
    logger_instance.logger.addHandler(log_handler)
    return log_handler

# This custom filter allows adding module information to the log record
class ModuleFilter(logging.Filter):
    def filter(self, record):
        record.mod = getattr(record, 'custom_module', 'main')
        return True

# Global logger instance
logger = ImageConverterLogger()
logger.logger.addFilter(ModuleFilter())

