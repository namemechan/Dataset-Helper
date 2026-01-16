import os
import pathlib
from typing import List, Dict, Any

def scan_directory(directory_path: str, extensions: List[str], include_subdirs: bool = True) -> List[str]:
    """지정된 디렉토리에서 특정 확장자를 가진 파일 목록을 검색합니다."""
    allowed_extensions = [ext.lower() for ext in extensions]
    found_files = []
    try:
        if include_subdirs:
            for root, _, files in os.walk(directory_path):
                for name in files:
                    if name.lower().endswith(tuple(allowed_extensions)):
                        found_files.append(os.path.join(root, name))
        else:
            for name in os.listdir(directory_path):
                if os.path.isfile(os.path.join(directory_path, name)) and name.lower().endswith(tuple(allowed_extensions)):
                    found_files.append(os.path.join(directory_path, name))
    except FileNotFoundError:
        # logger.error(f"디렉토리를 찾을 수 없습니다: {directory_path}", module="file_manager")
        return []
    except PermissionError:
        # logger.error(f"디렉토리 접근 권한이 없습니다: {directory_path}", module="file_manager")
        return []
    return found_files

def validate_file_access(file_path: str, mode: str = 'r') -> bool:
    """파일에 대한 읽기/쓰기 권한을 확인합니다."""
    try:
        if mode == 'r':
            return os.access(file_path, os.R_OK)
        elif mode == 'w':
            # For writing, we need to check the directory's permissions.
            parent_dir = os.path.dirname(file_path)
            if not parent_dir:
                parent_dir = "."
            return os.access(parent_dir, os.W_OK)
        return False
    except Exception:
        return False

def generate_output_filename(input_path: str, output_dir: str, target_format: str, naming_pattern: str = '{original_name}_converted') -> str:
    """출력 파일 경로를 생성합니다."""
    original_name = pathlib.Path(input_path).stem
    ext = target_format.lower().replace('.', '')
    try:
        new_name = naming_pattern.format(original_name=original_name, ext=ext)
    except (KeyError, ValueError):
        # 패턴이 잘못된 경우 기본값 사용
        new_name = f"{original_name}_converted"
    
    # 보안: 경로 조작 문자 제거 (Path Traversal 방지)
    safe_name = os.path.basename(new_name)
    return os.path.join(output_dir, f"{safe_name}.{ext}")

def handle_file_conflicts(output_path: str, policy: str = 'rename') -> str:
    """파일 충돌 시 정책에 따라 처리합니다 (skip, overwrite, rename)."""
    if not os.path.exists(output_path) or policy == 'overwrite':
        return output_path

    if policy == 'skip':
        return None # None을 반환하여 건너뛰도록 알림

    # Rename policy
    base, ext = os.path.splitext(output_path)
    counter = 1
    while True:
        new_path = f"{base}_{counter}{ext}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def get_file_info(file_path: str) -> Dict[str, Any]:
    """파일의 상세 정보를 반환합니다."""
    try:
        stat = os.stat(file_path)
        return {
            'path': file_path,
            'size': stat.st_size,
            'created_time': stat.st_ctime,
            'modified_time': stat.st_mtime,
            'is_readable': os.access(file_path, os.R_OK),
            'is_writable': os.access(file_path, os.W_OK),
        }
    except FileNotFoundError:
        return None

def create_backup(file_path: str, backup_dir: str = None) -> str:
    """파일의 백업을 생성합니다."""
    if not os.path.exists(file_path):
        return None

    if backup_dir:
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        backup_path = os.path.join(backup_dir, os.path.basename(file_path))
    else:
        backup_path = file_path + '.bak'

    try:
        import shutil
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception:
        return None
