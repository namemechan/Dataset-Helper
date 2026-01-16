"""
이름 변경 모듈 - 파일 쌍 일괄 이름 변경 및 실행 취소
"""
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import json
from datetime import datetime
from utils import get_paired_files, format_number

# 실행 취소 파일 경로 (프로그램 실행 디렉토리)
UNDO_FILE_PATH = Path(__file__).parent / ".rename_undo.json"

class RenameProcessor:
    @staticmethod
    def save_undo_info(folder_path: str, rename_history: List[Tuple[str, str, str, str]]):
        """
        실행 취소를 위한 정보 저장
        """
        undo_data = {
            "folder_path": str(Path(folder_path).absolute()),
            "timestamp": datetime.now().isoformat(),
            "history": rename_history
        }
        
        with open(UNDO_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(undo_data, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def load_undo_info(folder_path: str) -> Optional[List[Tuple[str, str, str, str]]]:
        """
        실행 취소 정보 로드 및 경로 검증
        """
        if not UNDO_FILE_PATH.exists():
            return None
        
        try:
            with open(UNDO_FILE_PATH, 'r', encoding='utf-8') as f:
                undo_data = json.load(f)
            
            # 현재 작업 중인 폴더와 저장된 폴더 경로가 일치하는지 확인
            saved_path = Path(undo_data.get("folder_path", ""))
            current_path = Path(folder_path).absolute()
            
            if saved_path != current_path:
                return None
                
            return undo_data.get("history", [])
        except Exception as e:
            print(f"실행 취소 정보 로드 실패: {e}")
            return None
    
    @staticmethod
    def undo_rename(folder_path: str) -> Tuple[int, int, List[str]]:
        """
        이름 변경 실행 취소
        """
        history = RenameProcessor.load_undo_info(folder_path)
        
        if not history:
            return 0, 0, ["현재 폴더에 대한 실행 취소 내역이 없습니다."]
        
        folder = Path(folder_path)
        success = 0
        fail = 0
        logs = []
        
        # 역순으로 복구
        for orig_img_name, orig_txt_name, new_img_name, new_txt_name in history:
            try:
                new_img = folder / new_img_name
                new_txt = folder / new_txt_name
                orig_img = folder / orig_img_name
                orig_txt = folder / orig_txt_name
                
                if new_img.exists():
                    new_img.rename(orig_img)
                if new_txt.exists():
                    new_txt.rename(orig_txt)
                
                logs.append(f"복구 완료: {new_img_name} → {orig_img_name}")
                success += 1
                
            except Exception as e:
                logs.append(f"복구 실패 {new_img_name}: {str(e)}")
                fail += 1
        
        # 사용한 실행 취소 파일 삭제
        if UNDO_FILE_PATH.exists():
            UNDO_FILE_PATH.unlink()
        
        return success, fail, logs
    
    @staticmethod
    def rename_file_pairs(
        folder_path: str,
        base_name: str,
        start_number: int,
        digit_count: int
    ) -> Tuple[int, int, List[str]]:
        """
        이미지-텍스트 파일 쌍 일괄 이름 변경
        """
        folder = Path(folder_path)
        if not folder.exists():
            return 0, 0, ["폴더가 존재하지 않습니다."]
        
        paired_files = get_paired_files(folder)
        
        if not paired_files:
            return 0, 0, ["이름을 변경할 파일 쌍이 없습니다."]
        
        success = 0
        fail = 0
        logs = []
        rename_history = []
        
        current_num = start_number
        temp_pairs = []
        
        # 1단계: 임시 이름으로 변경 (충돌 방지)
        for img_path, txt_path in paired_files:
            try:
                num_str = format_number(current_num, digit_count)
                new_base = f"{base_name}_{num_str}"
                
                temp_img = img_path.parent / f"_temp_{current_num}{img_path.suffix}"
                temp_txt = txt_path.parent / f"_temp_{current_num}{txt_path.suffix}"
                
                orig_img_name = img_path.name
                orig_txt_name = txt_path.name
                
                img_path.rename(temp_img)
                txt_path.rename(temp_txt)
                
                temp_pairs.append((
                    temp_img, temp_txt, new_base, 
                    img_path.suffix, txt_path.suffix,
                    orig_img_name, orig_txt_name
                ))
                current_num += 1
            except Exception as e:
                logs.append(f"임시 변경 실패 {img_path.name}: {str(e)}")
                fail += 1
        
        # 2단계: 최종 이름으로 변경 및 히스토리 기록
        for temp_img, temp_txt, new_base, img_ext, txt_ext, orig_img_name, orig_txt_name in temp_pairs:
            try:
                final_img = temp_img.parent / f"{new_base}{img_ext}"
                final_txt = temp_txt.parent / f"{new_base}{txt_ext}"
                
                temp_img.rename(final_img)
                temp_txt.rename(final_txt)
                
                rename_history.append((
                    orig_img_name, orig_txt_name,
                    final_img.name, final_txt.name
                ))
                
                logs.append(f"변경 완료: {orig_img_name} → {final_img.name}")
                success += 1
            except Exception as e:
                logs.append(f"최종 변경 실패 {new_base}: {str(e)}")
                fail += 1
        
        # 실행 취소 정보 저장 (프로젝트 폴더 내)
        if rename_history:
            RenameProcessor.save_undo_info(folder_path, rename_history)
        
        return success, fail, logs

    @staticmethod
    def preview_rename(
        folder_path: str,
        base_name: str,
        start_number: int,
        digit_count: int,
        preview_count: int = 10
    ) -> List[str]:
        """
        이름 변경 미리보기
        """
        folder = Path(folder_path)
        if not folder.exists():
            return ["폴더가 존재하지 않습니다."]
        
        paired_files = get_paired_files(folder)
        
        if not paired_files:
            return ["이름을 변경할 파일 쌍이 없습니다."]
        
        preview = []
        preview.append(f"총 {len(paired_files)}개의 파일 쌍이 변경됩니다.\n")
        preview.append(f"미리보기 (처음 {min(preview_count, len(paired_files))}개):")
        
        for i, (img_path, txt_path) in enumerate(paired_files[:preview_count]):
            num_str = format_number(start_number + i, digit_count)
            new_base = f"{base_name}_{num_str}"
            
            preview.append(f"\n[{i+1}]")
            preview.append(f"  {img_path.name} → {new_base}{img_path.suffix}")
            preview.append(f"  {txt_path.name} → {new_base}{txt_path.suffix}")
        
        if len(paired_files) > preview_count:
            preview.append(f"\n... 외 {len(paired_files) - preview_count}개")
        
        return preview
