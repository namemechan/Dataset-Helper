"""
태그 처리 모듈 - 태그 치환, 삭제, 이동 및 정렬 기능
"""
from pathlib import Path
from typing import List, Tuple, Dict, Set
from utils import PERSON_COUNT_TAGS, process_with_multicore
from functools import partial


class TagProcessor:
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
        
        Args:
            content: 원본 태그 문자열
            options: 처리 옵션 딕셔너리
                {
                    'use_replace': bool, 'replace_find': str, 'replace_with': str,
                    'use_delete': bool, 'delete_tags': List[str], # 여기서 delete_tags는 문자열 리스트일 수도 있고, 연속된 태그 문자열일 수도 있음
                    'use_add': bool, 'add_tags': str, # 추가할 태그
                    'use_move_person': bool,
                    'use_move_custom': bool, 'move_custom_tags': List[str]
                }
        """
        tags = TagProcessor.parse_tags(content)
        original_tags = tags[:]
        changes = []

        # 0. 누락된 인원수 태그 추가 (New)
        # 가장 먼저 실행하여 이후 로직(이동 등)에 반영되도록 함
        if options.get('use_missing_tag'):
            # 현재 태그 중 인원수 태그가 있는지 확인
            has_person_tag = any(tag in tags for tag in PERSON_COUNT_TAGS)
            
            if not has_person_tag:
                gender = options.get('missing_gender', 'girl')
                count = options.get('missing_count', '1')
                
                # 태그 생성 (1girl, 2girls, 6+girls ...)
                # 6+는 s가 이미 붙어있다고 가정하거나 붙임. PERSON_COUNT_TAGS에는 '6+girls'로 되어 있음.
                if count == "6+":
                    new_tag = f"6+{gender}s"
                elif count == "1":
                    new_tag = f"1{gender}"
                else:
                    new_tag = f"{count}{gender}s"
                
                # 중복 방지 (이미 리스트에 있을 수도 있으므로)
                if new_tag not in tags:
                    tags.insert(0, new_tag)
                    changes.append(f"주입: 누락된 인원수 태그 '{new_tag}' 추가")

        # --- 헬퍼 함수: 리스트 내 서브 시퀀스 찾아서 교체/삭제 ---
        def replace_subsequence(current_tags: List[str], find_seq: List[str], replace_seq: List[str] = None) -> Tuple[List[str], int]:
            if not find_seq:
                return current_tags, 0
            
            result_tags = []
            i = 0
            count = 0
            n = len(current_tags)
            m = len(find_seq)
            
            while i < n:
                # 현재 위치부터 find_seq 길이만큼 비교
                if i + m <= n and current_tags[i:i+m] == find_seq:
                    # 매칭됨
                    if replace_seq:
                        result_tags.extend(replace_seq)
                    count += 1
                    i += m # 매칭된 길이만큼 건너뜀
                else:
                    result_tags.append(current_tags[i])
                    i += 1
            return result_tags, count

        # 1. 태그 치환 (Replace) - 단일 및 연속 태그 지원
        if options.get('use_replace') and options.get('replace_find'):
            find_str = options['replace_find'].strip()
            replace_str = options.get('replace_with', '').strip()
            
            find_seq = TagProcessor.parse_tags(find_str)
            replace_seq = TagProcessor.parse_tags(replace_str)
            
            if find_seq:
                tags, replaced_count = replace_subsequence(tags, find_seq, replace_seq)
                if replaced_count > 0:
                    changes.append(f"치환: '{find_str}' → '{replace_str}' ({replaced_count}건)")

        # 2. 태그 삭제 (Delete) - 단일 및 연속 태그 지원
        # 기존 List[str] 입력도 지원하고, 쉼표로 구분된 긴 문자열도 처리하기 위해 로직 개선
        if options.get('use_delete') and options.get('delete_tags'):
            raw_delete_input = options['delete_tags']
            # delete_tags가 리스트라면 하나씩 처리, 하지만 연속된 태그("1girl, solo")를 지우려는 의도를 파악해야 함.
            # UI에서 리스트로 오지만, 여기서는 각 요소를 하나의 시퀀스로 볼지 개별 태그로 볼지 결정해야 함.
            # 보통 |로 구분된 값들이 들어옴. "tag1, tag2 | tag3" -> ["tag1, tag2", "tag3"]
            
            total_deleted = 0
            deleted_items = []
            
            for del_item in raw_delete_input:
                del_seq = TagProcessor.parse_tags(del_item)
                if not del_seq:
                    continue
                
                tags, count = replace_subsequence(tags, del_seq, None) # None means delete
                if count > 0:
                    total_deleted += count
                    deleted_items.append(del_item)
            
            if total_deleted > 0:
                changes.append(f"삭제: {', '.join(deleted_items)}")

        # 3. 태그 이동 및 정렬 (Move / Reorder)
        use_person = options.get('use_move_person', False)
        use_solo = options.get('use_move_solo', False)
        use_custom = options.get('use_move_custom', False)
        
        person_group = []
        solo_group = [] # solo 태그 별도 관리
        custom_group = []
        other_group = []
        
        custom_targets = set(options.get('move_custom_tags', [])) if use_custom else set()
        
        if use_person or use_solo or use_custom:
            for tag in tags:
                # 인원수 태그 확인
                if use_person and tag in PERSON_COUNT_TAGS:
                    person_group.append(tag)
                # Solo 태그 확인
                elif use_solo and tag == 'solo':
                    solo_group.append(tag)
                # 사용자 지정 이동 태그 확인
                elif use_custom and tag in custom_targets:
                    custom_group.append(tag)
                # 나머지
                else:
                    other_group.append(tag)
            
            # 재조립: 인원수 -> Solo -> 사용자 지정 -> (여기서 추가 태그 삽입 예정) -> 나머지
            # 인원수 태그 정렬 (보통 하나만 있지만 여러 개일 경우 1girl < 2girls 순 등 사전순 정렬 보장)
            person_group.sort() 
            
            # 현재까지의 앞단
            front_tags = person_group + solo_group + custom_group
            
            # 4. 태그 추가 (Add) - 인원수/Solo/Custom 그룹 바로 뒤
            if options.get('use_add') and options.get('add_tags'):
                add_str = options['add_tags']
                new_add_tags = TagProcessor.parse_tags(add_str)
                
                # 중복 방지 로직 없이 단순 추가
                if new_add_tags:
                    front_tags.extend(new_add_tags)
                    changes.append(f"추가: '{add_str}'")

            new_order = front_tags + other_group
            
            # 순서가 바뀌었거나 태그가 추가되었는지 확인
            if new_order != tags: # 내용이 다르거나 순서가 다르면
                tags = new_order
                moved_info = []
                if person_group: moved_info.append("인원수")
                if solo_group: moved_info.append("solo")
                if custom_group: moved_info.append("지정 태그")
                if moved_info:
                    changes.append(f"이동: {', '.join(moved_info)} 앞으로")

        # 만약 이동 옵션은 껐는데 추가 옵션만 켰을 경우 처리 (위 블록에 안 들어감)
        elif options.get('use_add') and options.get('add_tags'):
            add_str = options['add_tags']
            new_add_tags = TagProcessor.parse_tags(add_str)
            if new_add_tags:
                tags = new_add_tags + tags
                changes.append(f"추가: '{add_str}' (맨 앞)")

        final_content = TagProcessor.join_tags(tags)
        return final_content, changes

    @staticmethod
    def process_single_file(file_path: Path, options: Dict) -> Tuple[bool, str, List[str]]:
        """
        단일 파일 처리 래퍼
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            new_content, changes = TagProcessor.process_tags_logic(content, options)
            
            if new_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return True, f"변경됨: {file_path.name} | {' / '.join(changes)}", changes
            else:
                return True, f"변경 없음: {file_path.name}", []
        
        except Exception as e:
            return False, f"오류: {file_path.name} - {str(e)}", []

    @staticmethod
    def process_folder(text_files: List[Path], options: Dict, num_cores: int = 1) -> Tuple[int, int, List[str]]:
        """
        폴더 일괄 처리
        """
        if not text_files:
            return 0, 0, ["처리할 파일이 없습니다."]
        
        # partial을 사용하여 options를 고정 인자로 전달
        worker = partial(TagProcessor.process_single_file, options=options)
        
        results = process_with_multicore(
            worker,
            text_files,
            num_cores
        )
        
        success = sum(1 for r in results if r[0])
        fail = sum(1 for r in results if not r[0])
        logs = [r[1] for r in results]
        
        return success, fail, logs
    
    @staticmethod
    def preview_tag_processing(text_files: List[Path], options: Dict, preview_count: int = 10) -> List[str]:
        """
        미리보기 생성
        """
        if not text_files:
            return ["처리할 파일이 없습니다."]
        
        preview = []
        preview.append(f"대상 파일: {len(text_files)}개\n")
        
        # 옵션 요약
        op_summary = []
        if options.get('use_replace'): op_summary.append(f"[치환] {options['replace_find']} -> {options['replace_with']}")
        if options.get('use_delete'): op_summary.append(f"[삭제] {len(options['delete_tags'])}개 태그")
        if options.get('use_move_person'): op_summary.append("[이동] 인원수 태그")
        if options.get('use_move_custom'): op_summary.append(f"[이동] 사용자 지정 {len(options['move_custom_tags'])}개 태그")
        
        preview.append(f"적용 옵션: {', '.join(op_summary) if op_summary else '없음'}\n")
        preview.append("-" * 50)
        
        count = 0
        for file_path in text_files:
            if count >= preview_count:
                break
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                new_content, changes = TagProcessor.process_tags_logic(content, options)
                
                if changes: # 변경사항이 있는 경우만 미리보기에 표시
                    preview.append(f"📄 {file_path.name}")
                    for change in changes:
                        preview.append(f"  └ {change}")
                    
                    # 내용이 너무 길면 자르기
                    short_orig = (content[:60] + '...') if len(content) > 60 else content
                    short_new = (new_content[:60] + '...') if len(new_content) > 60 else new_content
                    
                    preview.append(f"  [전] {short_orig}")
                    preview.append(f"  [후] {short_new}")
                    preview.append("")
                    count += 1
            except Exception as e:
                preview.append(f"❌ {file_path.name}: {e}")
        
        if count == 0:
            preview.append("설정된 옵션으로 변경되는 파일이 상위 파일들에서 발견되지 않았습니다.")
        elif len(text_files) > count:
             preview.append(f"... 외 나머지 파일 대기 중")
            
        return preview
