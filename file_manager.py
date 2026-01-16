"""
파일 관리 모듈 - 단일 파일 찾기, 삭제, 이동 기능
"""
from pathlib import Path
from typing import List
import shutil
from utils import is_image_file, is_text_file, IMAGE_EXTENSIONS, TEXT_EXTENSION


class FileManager:
    def __init__(self, folder_path: str):
        self.folder = Path(folder_path)
    
    def find_single_images(self, recursive: bool = False) -> List[Path]:
        """
        짝이 없는 이미지 파일 찾기 (txt 파일이 없는 이미지)
        """
        if not self.folder.exists():
            return []
        
        single_images = []
        files = self.folder.rglob("*") if recursive else self.folder.iterdir()
        
        for file in files:
            if file.is_file() and is_image_file(file):
                txt_file = file.with_suffix(TEXT_EXTENSION)
                if not txt_file.exists():
                    single_images.append(file)
        
        return sorted(single_images, key=lambda x: x.name)
    
    def find_single_texts(self, recursive: bool = False) -> List[Path]:
        """
        짝이 없는 텍스트 파일 찾기 (이미지 파일이 없는 txt)
        """
        if not self.folder.exists():
            return []
        
        single_texts = []
        files = self.folder.rglob("*") if recursive else self.folder.iterdir()
        
        for file in files:
            if file.is_file() and is_text_file(file):
                # 같은 이름의 이미지 파일이 있는지 확인
                has_pair = False
                for ext in IMAGE_EXTENSIONS:
                    img_file = file.with_suffix(ext)
                    if img_file.exists():
                        has_pair = True
                        break
                
                if not has_pair:
                    single_texts.append(file)
        
        return sorted(single_texts, key=lambda x: x.name)
    
    def delete_files(self, files: List[Path]) -> tuple[int, int]:
        """
        파일 삭제
        Returns: (성공 수, 실패 수)
        """
        success = 0
        fail = 0
        
        for file in files:
            try:
                if file.exists():
                    file.unlink()
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                print(f"삭제 실패 {file.name}: {e}")
                fail += 1
        
        return success, fail
    
    def move_files(self, files: List[Path], dest_folder: str) -> tuple[int, int]:
        """
        파일 이동
        Returns: (성공 수, 실패 수)
        """
        dest = Path(dest_folder)
        
        # 대상 폴더가 없으면 생성
        if not dest.exists():
            try:
                dest.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"폴더 생성 실패: {e}")
                return 0, len(files)
        
        success = 0
        fail = 0
        
        for file in files:
            try:
                if file.exists():
                    dest_file = dest / file.name
                    shutil.move(str(file), str(dest_file))
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                print(f"이동 실패 {file.name}: {e}")
                fail += 1
        
        return success, fail
    
    def get_file_list_text(self, files: List[Path]) -> str:
        """
        파일 목록을 텍스트로 반환
        """
        if not files:
            return "파일이 없습니다."
        
        return "\n".join([f.name for f in files])