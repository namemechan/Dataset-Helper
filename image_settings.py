import json
import os

CONFIG_FILE = 'converter_config.json'

def get_default_settings() -> dict:
    """기본 설정값을 반환합니다."""
    return {
        'input_settings': {
            'source_folder': '',
            'supported_formats': ['jpg', 'jpeg', 'png', 'gif', 'webp'],
            'include_subfolders': True
        },
        'output_settings': {
            'target_folder': '',
            'target_format': 'png',
            'naming_pattern': '{original_name}_converted',
            'use_suffix': True,
            'suffix_text': '_converted',
            'overwrite_policy': 'rename'  # 'skip', 'overwrite', 'rename'
        },
        'conversion_settings': {
            'quality_enabled': True,
            'quality_value': 95,
            'resize_enabled': False,
            'resize_scale': 1.0,
            'optimize': True
        },
        'metadata_settings': {
            'preserve_enabled': True,
            'preservation_methods': {
                'exif': True,
                'png_text': True,
                'steganography': True,
                'all_methods': False
            },
            'ai_info_priority': ['stealth_pnginfo', 'png_text', 'exif'],
            'compression_steganography': True
        },
        'processing_settings': {
            'multiprocessing_enabled': True,
            'max_workers': max(1, int((os.cpu_count() or 1) * 0.3)),
            'chunk_size': 100,
            'memory_limit_mb': 4096
        },
        'logging_settings': {
            'log_level': 'INFO',
            'save_logs': True,
            'log_file_path': 'logs/converter.log',
            'max_log_size_mb': 10
        }
    }

def save_settings(settings: dict, config_file: str = CONFIG_FILE) -> bool:
    """설정을 JSON 파일에 저장합니다."""
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        return True
    except (IOError, TypeError) as e:
        # In a real app, you'd use the logger here.
        print(f"Error saving settings: {e}")
        return False

def load_settings(config_file: str = CONFIG_FILE) -> dict:
    """JSON 파일에서 설정을 불러옵니다. 파일이 없으면 기본값을 사용합니다."""
    if not os.path.exists(config_file):
        return get_default_settings()
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            # You might want to merge with defaults to ensure all keys are present
            # For simplicity, we'll just return what we load.
            return settings
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading settings: {e}. Returning default settings.")
        return get_default_settings()

def validate_settings(settings: dict) -> tuple:
    """설정값의 유효성을 검사합니다."""
    errors = []
    # Example validation (can be expanded significantly)
    if not isinstance(settings.get('input_settings', {}).get('source_folder'), str):
        errors.append("Source folder must be a string.")
    if not isinstance(settings.get('output_settings', {}).get('target_folder'), str):
        errors.append("Target folder must be a string.")
    if not settings.get('input_settings', {}).get('source_folder'):
        errors.append("Source folder cannot be empty.")
    if not settings.get('output_settings', {}).get('target_folder'):
        errors.append("Target folder cannot be empty.")

    is_valid = len(errors) == 0
    return is_valid, errors

# Placeholder for more advanced functions
def migrate_settings(old_settings: dict, version: str) -> dict:
    print("Function 'migrate_settings' is not implemented yet.")
    return old_settings

def export_settings_profile(settings: dict, profile_name: str) -> bool:
    print("Function 'export_settings_profile' is not implemented yet.")
    return False

def import_settings_profile(profile_name: str) -> dict:
    print("Function 'import_settings_profile' is not implemented yet.")
    return None
