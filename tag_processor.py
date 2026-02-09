"""
태그 처리 모듈 - 태그 치환, 삭제, 이동 및 정렬 기능
"""
from pathlib import Path
from typing import List, Tuple, Dict, Set, Optional
from utils import PERSON_COUNT_TAGS, process_with_multicore
from functools import partial
import json
from datetime import datetime
import os

UNDO_DIR = Path("logs/undo")

class TagProcessor:
    @staticmethod
    def save_undo_info(folder_path: str, tag_history: List[Dict[str, str]]):
        """
        태그 처리 실행 취소 정보 저장
        tag_history: [{"file": "relative_path", "content": "original content"}, ...] 
        """
        if not tag_history:
            return

        if not UNDO_DIR.exists():
            UNDO_DIR.mkdir(parents=True, exist_ok=True)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        undo_filename = f"undo_tag_{timestamp}.json"
        undo_path = UNDO_DIR / undo_filename
        
        undo_data = {
            "type": "tag",
            "folder_path": str(Path(folder_path).absolute()),
            "timestamp": datetime.now().isoformat(),
            "history": tag_history
        }
        
        try:
            with open(undo_path, 'w', encoding='utf-8') as f:
                json.dump(undo_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"태그 실행 취소 파일 저장 실패: {e}")

    @staticmethod
    def undo_last_processing(folder_path: str) -> Tuple[int, int, List[str]]:
        """
        태그 처리 실행 취소
        """
        if not UNDO_DIR.exists():
            return 0, 0, ["실행 취소 폴더가 없습니다."]
            
        # 태그 undo 파일 검색
        files = sorted(UNDO_DIR.glob("undo_tag_*.json"), reverse=True)
        
        target_file = None
        current_path = Path(folder_path).absolute()
        
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if Path(data.get("folder_path", "")) == current_path:
                    target_file = file_path
                    break
            except:
                continue
        
        if not target_file:
            return 0, 0, ["실행 취소할 태그 작업 내역이 없습니다."]
            
        # 복구 시작
        success = 0
        fail = 0
        logs = []
        
        try:
            with open(target_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            history = data.get("history", [])
            folder = Path(folder_path)
            
            for item in history:
                rel_path = item['file']
                original_content = item['content']
                file_path = folder / rel_path
                
                try:
                    # 파일이 없으면 생성, 있으면 덮어쓰기
                    # (삭제된 태그를 복구하는 것이므로 내용만 돌려놓으면 됨)
                    # 만약 파일 자체가 삭제되었다면? (단일 파일 찾기 등에서) -> 생성해줌.
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(original_content)
                    success += 1
                    logs.append(f"복구: {rel_path}")
                except Exception as e:
                    logs.append(f"에러 {rel_path}: {e}")
                    fail += 1
            
            # Undo 파일 삭제
            target_file.unlink()
            logs.append(f"실행 취소 파일 삭제됨: {target_file.name}")
            
        except Exception as e:
            return 0, 0, [f"실행 취소 중 치명적 오류: {e}"]
            
        return success, fail, logs

    @staticmethod
    def parse_tags(tag_string: str) -> List[str]:
        """
        태그 문자열을 리스트로 파싱
        쉼표로 구분하고 공백 제거, 빈 태그 제거
        """
        if not tag_string:
            return []
        tags = [tag.strip() for tag in tag_string.split(',')]
        return [tag for tag in tags if tag]
    
    @staticmethod
    def join_tags(tags: List[str]) -> str:
        """태그 리스트를 문자열로 결합"""
        return ', '.join(tags)

    @staticmethod
    def process_tags_logic(
        content: str, 
        options: Dict
    ) -> Tuple[str, List[str]]:
        """
        태그 처리 핵심 로직
        """
        tags = TagProcessor.parse_tags(content)
        original_tags = tags[:]
        changes = []

        # 0. 누락된 인원수 태그 추가
        if options.get('use_missing_tag'):
            has_person_tag = any(tag in tags for tag in PERSON_COUNT_TAGS)
            if not has_person_tag:
                gender = options.get('missing_gender', 'girl')
                count = options.get('missing_count', '1')
                if count == "6+": new_tag = f"6+{gender}s"
                elif count == "1": new_tag = f"1{gender}"
                else: new_tag = f"{count}{gender}s"
                
                if new_tag not in tags:
                    tags.insert(0, new_tag)
                    changes.append(f"주입: 누락된 인원수 태그 '{new_tag}' 추가")

        # --- 헬퍼 함수 ---
        def replace_subsequence(current_tags: List[str], find_seq: List[str], replace_seq: List[str] = None) -> Tuple[List[str], int]:
            if not find_seq: return current_tags, 0
            result_tags = []
            i = 0
            count = 0
            n = len(current_tags)
            m = len(find_seq)
            while i < n:
                if i + m <= n and current_tags[i:i+m] == find_seq:
                    if replace_seq: result_tags.extend(replace_seq)
                    count += 1
                    i += m
                else:
                    result_tags.append(current_tags[i])
                    i += 1
            return result_tags, count
            
        def check_condition(current_tags: List[str], condition_str: str) -> bool:
            if not condition_str: return False
            cond_tags = [t.strip() for t in condition_str.split('|') if t.strip()]
            for ct in cond_tags:
                if ct in current_tags: return True
            return False

        # 1. 태그 치환
        if options.get('use_replace') and options.get('replace_find'):
            find_str = options['replace_find'].strip()
            replace_str = options.get('replace_with', '').strip()
            find_seq = TagProcessor.parse_tags(find_str)
            replace_seq = TagProcessor.parse_tags(replace_str)
            if find_seq:
                tags, replaced_count = replace_subsequence(tags, find_seq, replace_seq)
                if replaced_count > 0:
                    changes.append(f"치환: '{find_str}' → '{replace_str}' ({replaced_count}건)")

        # 1.5 인접 태그 수정 (New)
        if options.get('use_neighbor_modify') and options.get('neighbor_target'):
            target_tag = options['neighbor_target'].strip()
            neighbor_pos = options.get('neighbor_pos', 'after') # 'before' or 'after'
            add_pos = options.get('neighbor_add_pos', 'prefix') # 'prefix' or 'suffix'
            add_text = options.get('neighbor_text', '')
            
            if target_tag and add_text:
                new_tags = tags[:]
                modified_indices = set()
                
                # 타겟 태그의 모든 위치 찾기
                for idx, tag in enumerate(tags):
                    if tag == target_tag:
                        # 인접 인덱스 계산
                        n_idx = idx - 1 if neighbor_pos == 'before' else idx + 1
                        
                        if 0 <= n_idx < len(tags):
                            modified_indices.add(n_idx)
                
                # 실제 수정 적용 (뒤에서부터 수정해야 인덱스 혼란 방지 - 여기서는 인덱스 고정이라 상관없지만 습관적 처리)
                if modified_indices:
                    for m_idx in sorted(list(modified_indices), reverse=True):
                        orig_neighbor = tags[m_idx]
                        if add_pos == 'prefix':
                            tags[m_idx] = add_text + orig_neighbor
                        else:
                            tags[m_idx] = orig_neighbor + add_text
                    
                    changes.append(f"인접수정: '{target_tag}'의 {neighbor_pos} 태그에 '{add_text}' {add_pos} 추가")

        # 1.7 CSV 기반 특수 처리 (New)
        if options.get('use_csv_process') and options.get('csv_tags_set'):
            csv_tags = options['csv_tags_set']
            csv_mode = options.get('csv_mode', 'add')
            csv_input = options.get('csv_input_text', '')
            csv_add_pos = options.get('csv_add_pos', 'prefix')
            
            new_tags_list = []
            csv_changes_count = 0
            
            for tag in tags:
                # 비교를 위한 정규화 (소문자화 및 언더바->공백)
                normalized_tag = tag.lower().replace('_', ' ')
                
                if normalized_tag in csv_tags:
                    csv_changes_count += 1
                    if csv_mode == 'add':
                        processed_tag = (csv_input + tag) if csv_add_pos == 'prefix' else (tag + csv_input)
                        new_tags_list.append(processed_tag)
                    elif csv_mode == 'replace':
                        new_tags_list.append(csv_input)
                    elif csv_mode == 'delete':
                        continue # 추가하지 않음 (삭제)
                else:
                    new_tags_list.append(tag)
            
            if csv_changes_count > 0:
                tags = new_tags_list
                mode_name = "추가" if csv_mode == 'add' else "치환" if csv_mode == 'replace' else "삭제"
                changes.append(f"CSV처리: {csv_changes_count}개 태그 {mode_name} 완료")

        # 2. 태그 삭제
        if options.get('use_delete') and options.get('delete_tags'):
            should_delete = True
            if options.get('use_conditional_delete'):
                if not check_condition(tags, options.get('condition_delete_tags', '')):
                    should_delete = False
            
            if should_delete:
                raw_delete_input = options['delete_tags']
                total_deleted = 0
                deleted_items = []
                for del_item in raw_delete_input:
                    del_seq = TagProcessor.parse_tags(del_item)
                    if not del_seq: continue
                    tags, count = replace_subsequence(tags, del_seq, None)
                    if count > 0:
                        total_deleted += count
                        deleted_items.append(del_item)
                if total_deleted > 0:
                    changes.append(f"삭제: {', '.join(deleted_items)}")

        # 3. 태그 이동 및 정렬
        use_person = options.get('use_move_person', False)
        use_solo = options.get('use_move_solo', False)
        use_custom = options.get('use_move_custom', False)
        
        person_group = []
        solo_group = []
        custom_group = []
        other_group = []
        custom_targets = set(options.get('move_custom_tags', [])) if use_custom else set()
        
        if use_person or use_solo or use_custom:
            for tag in tags:
                if use_person and tag in PERSON_COUNT_TAGS: person_group.append(tag)
                elif use_solo and tag == 'solo': solo_group.append(tag)
                elif use_custom and tag in custom_targets: custom_group.append(tag)
                else: other_group.append(tag)
            
            person_group.sort()
            front_tags = person_group + solo_group + custom_group
            
            # 4. 태그 추가 (이동 옵션 활성화 시)
            if options.get('use_add') and options.get('add_tags'):
                should_add = True
                if options.get('use_conditional_add'):
                    all_current_tags = person_group + solo_group + custom_group + other_group
                    if not check_condition(all_current_tags, options.get('condition_add_tags', '')):
                        should_add = False
                
                if should_add:
                    add_str = options['add_tags']
                    new_add_tags = TagProcessor.parse_tags(add_str)
                    if new_add_tags:
                        front_tags.extend(new_add_tags)
                        changes.append(f"추가: '{add_str}'")

            new_order = front_tags + other_group
            if new_order != tags:
                tags = new_order
                moved_info = []
                if person_group: moved_info.append("인원수")
                if solo_group: moved_info.append("solo")
                if custom_group: moved_info.append("지정 태그")
                if moved_info:
                    changes.append(f"이동: {', '.join(moved_info)} 앞으로")

        # 4. 태그 추가 (이동 옵션 비활성화 시)
        elif options.get('use_add') and options.get('add_tags'):
            should_add = True
            if options.get('use_conditional_add'):
                if not check_condition(tags, options.get('condition_add_tags', '')):
                    should_add = False
            
            if should_add:
                add_str = options['add_tags']
                new_add_tags = TagProcessor.parse_tags(add_str)
                if new_add_tags:
                    tags = new_add_tags + tags
                    changes.append(f"추가: '{add_str}' (맨 앞)")

        final_content = TagProcessor.join_tags(tags)
        return final_content, changes

    @staticmethod
    def process_single_file(file_path: Path, options: Dict) -> Tuple[bool, str, List[str], str]:
        """
        단일 파일 처리 래퍼
        Returns: (is_changed, log_message, changes, original_content)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            new_content, changes = TagProcessor.process_tags_logic(content, options)
            
            if new_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return True, f"변경됨: {file_path.name} | {' / '.join(changes)}", changes, content
            else:
                return False, f"변경 없음: {file_path.name}", [], content
        
        except Exception as e:
            return False, f"오류: {file_path.name} - {str(e)}", [], ""

    @staticmethod
    def process_folder(text_files: List[Path], options: Dict, num_cores: int = 1, folder_path: str = "") -> Tuple[int, int, List[str]]:
        """
        폴더 일괄 처리
        folder_path: 상대 경로 계산을 위한 기준 폴더 (Undo 저장용)
        """
        if not text_files:
            return 0, 0, ["처리할 파일이 없습니다."]
        
        worker = partial(TagProcessor.process_single_file, options=options)
        
        results = process_with_multicore(
            worker,
            text_files,
            num_cores
        )
        
        success = 0
        fail = 0
        logs = []
        tag_history = []
        
        root_path = Path(folder_path).absolute() if folder_path else None
        
        for i, r in enumerate(results):
            is_changed, log_msg, changes, original_content = r
            logs.append(log_msg)
            
            if is_changed:
                success += 1
                if root_path:
                    try:
                        # 상대 경로 계산
                        rel_path = str(text_files[i].absolute().relative_to(root_path))
                        tag_history.append({
                            "file": rel_path,
                            "content": original_content
                        })
                    except ValueError:
                        # 경로 계산 실패 시 그냥 파일명 사용 (위험하지만 차선책)
                        tag_history.append({
                            "file": text_files[i].name,
                            "content": original_content
                        })
            elif "오류" in log_msg:
                fail += 1
        
        if tag_history and folder_path:
            TagProcessor.save_undo_info(folder_path, tag_history)
        
        return success, fail, logs
    
    @staticmethod
    def preview_tag_processing(text_files: List[Path], options: Dict, preview_count: int = 10) -> List[str]:
        """
        미리보기 생성
        """
        if not text_files:
            return ["처리할 파일이 없습니다."]
        
        preview = []
        
        # 옵션 요약
        op_summary = []
        if options.get('use_replace'): op_summary.append(f"[치환] {options['replace_find']} -> {options['replace_with']}")
        if options.get('use_delete'): 
            op_summary.append(f"[삭제] {len(options['delete_tags'])}개 태그" + (" (조건부)" if options.get('use_conditional_delete') else ""))
        if options.get('use_move_person'): op_summary.append("[이동] 인원수 태그")
        if options.get('use_move_custom'): op_summary.append(f"[이동] 사용자 지정 {len(options['move_custom_tags'])}개 태그")
        if options.get('use_add'):
            op_summary.append(f"[추가] {options['add_tags']}" + (" (조건부)" if options.get('use_conditional_add') else ""))

        preview.append(f"적용 옵션: {', '.join(op_summary) if op_summary else '없음'}\n")
        preview.append("-" * 50)
        
        count = 0
        processed_count = 0
        
        for file_path in text_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                new_content, changes = TagProcessor.process_tags_logic(content, options)
                
                if changes: # 변경사항이 있는 경우
                    processed_count += 1
                    if count < preview_count:
                        preview.append(f"📄 {file_path.name}")
                        for change in changes:
                            preview.append(f"  └ {change}")
                        
                        short_orig = (content[:60] + '...') if len(content) > 60 else content
                        short_new = (new_content[:60] + '...') if len(new_content) > 60 else new_content
                        
                        preview.append(f"  [전] {short_orig}")
                        preview.append(f"  [후] {short_new}")
                        preview.append("")
                        count += 1
            except Exception as e:
                if count < preview_count:
                    preview.append(f"❌ {file_path.name}: {e}")
                    count += 1
        
        # 맨 앞에 요약 추가 (순서상 리스트 insert 사용)
        summary_lines = [
            f"검색된 전체 파일: {len(text_files)}개",
            f"변경 대상 파일: {processed_count}개",
            ""
        ]
        
        # 리스트 합치기
        final_preview = summary_lines + preview
        
        if count == 0 and processed_count == 0:
            final_preview.append("설정된 옵션으로 변경되는 파일이 없습니다.")
        elif count < processed_count:
             final_preview.append(f"... 외 {processed_count - count}개 파일 변경 예정")
            
        return final_preview