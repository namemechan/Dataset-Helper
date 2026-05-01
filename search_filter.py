"""
검색 및 분류 모듈 - 데이터셋 파일을 조건별로 검색하고 처리하는 로직
"""
import os
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable
from PIL import Image
import concurrent.futures
import threading

from utils import IMAGE_EXTENSIONS, TEXT_EXTENSION, is_image_file, is_text_file


# ------------------------------------------------------------------
# 데이터 구조
# ------------------------------------------------------------------

class FileEntry:
    """검색 결과 단일 항목"""
    def __init__(self, image_path: Optional[Path], txt_path: Optional[Path]):
        self.image_path: Optional[Path] = image_path
        self.txt_path: Optional[Path] = txt_path

    @property
    def display_name(self) -> str:
        base = self.image_path or self.txt_path
        return base.name if base else ""

    @property
    def stem(self) -> str:
        base = self.image_path or self.txt_path
        return base.stem if base else ""

    @property
    def folder(self) -> str:
        base = self.image_path or self.txt_path
        return str(base.parent) if base else ""

    @property
    def image_ext(self) -> str:
        return self.image_path.suffix.lower() if self.image_path else ""

    @property
    def file_size_bytes(self) -> int:
        """이미지 파일 크기(바이트). 이미지 없으면 txt 크기."""
        target = self.image_path if self.image_path else self.txt_path
        try:
            return target.stat().st_size if target and target.exists() else 0
        except Exception:
            return 0

    @property
    def file_size_kb(self) -> float:
        return round(self.file_size_bytes / 1024, 1)

    @property
    def resolution(self) -> Optional[Tuple[int, int]]:
        """이미지 해상도 (w, h). 이미지 없거나 읽기 실패 시 None."""
        if not self.image_path or not self.image_path.exists():
            return None
        try:
            with Image.open(self.image_path) as img:
                return img.size  # (width, height)
        except Exception:
            return None

    @property
    def tag_content(self) -> str:
        """txt 파일 내용 전체. 없으면 빈 문자열."""
        if not self.txt_path or not self.txt_path.exists():
            return ""
        try:
            return self.txt_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    @property
    def tags(self) -> List[str]:
        """쉼표 구분 태그 리스트 (공백 정리, 소문자화)."""
        content = self.tag_content
        if not content.strip():
            return []
        return [t.strip().lower() for t in content.split(",") if t.strip()]

    def has_image(self) -> bool:
        return self.image_path is not None and self.image_path.exists()

    def has_txt(self) -> bool:
        return self.txt_path is not None and self.txt_path.exists()


# ------------------------------------------------------------------
# 검색 조건 적용 로직
# ------------------------------------------------------------------

def _parse_tag_query(query_str: str) -> List[str]:
    """사용자 입력 '태그1 | 태그2' → ['태그1', '태그2'] (공백+소문자 정리)"""
    return [t.strip().lower() for t in query_str.split("|") if t.strip()]


def _match_filename(entry: FileEntry, pattern: str) -> bool:
    """파일명에 패턴(대소문자 무시) 포함 여부"""
    return pattern.lower() in entry.stem.lower()


def _match_size(entry: FileEntry, min_kb: Optional[float], max_kb: Optional[float]) -> bool:
    size = entry.file_size_kb
    if min_kb is not None and size < min_kb:
        return False
    if max_kb is not None and size > max_kb:
        return False
    return True


def _match_resolution(entry: FileEntry,
                      min_w: Optional[int], max_w: Optional[int],
                      min_h: Optional[int], max_h: Optional[int]) -> bool:
    res = entry.resolution
    if res is None:
        # 해상도 조건이 걸려있는데 이미지가 없으면 불일치 처리
        if any(x is not None for x in [min_w, max_w, min_h, max_h]):
            return False
        return True
    w, h = res
    if min_w is not None and w < min_w:
        return False
    if max_w is not None and w > max_w:
        return False
    if min_h is not None and h < min_h:
        return False
    if max_h is not None and h > max_h:
        return False
    return True


def _match_tags(entry: FileEntry, query_tags: List[str]) -> bool:
    """entry의 태그 리스트에 query_tags 중 하나라도 포함되면 True"""
    if not query_tags:
        return True
    entry_tags = entry.tags
    for qt in query_tags:
        if qt in entry_tags:
            return True
    return False


def _match_tags_all(entry: FileEntry, query_tags: List[str]) -> bool:
    """entry의 태그 리스트에 query_tags 모두 포함되면 True"""
    if not query_tags:
        return True
    entry_tags = entry.tags
    return all(qt in entry_tags for qt in query_tags)


# ------------------------------------------------------------------
# 조건 평가 (AND / OR / NOT / 미사용)
# ------------------------------------------------------------------

def _evaluate_condition(entry: FileEntry, condition: Dict) -> bool:
    """
    condition 구조:
    {
      'mode': 'unused' | 'and' | 'or' | 'not',
      'type': 'filename' | 'size' | 'resolution' | 'tag',
      ... (type별 파라미터)
    }
    미사용이면 항상 True 반환.
    """
    mode = condition.get('mode', 'unused')
    if mode == 'unused':
        return True  # 이 조건은 평가에 참여 안 함 → 기여 없음

    ctype = condition.get('type')

    if ctype == 'filename':
        pattern = condition.get('pattern', '')
        if not pattern:
            return True
        matched = _match_filename(entry, pattern)

    elif ctype == 'size':
        matched = _match_size(
            entry,
            condition.get('min_kb'),
            condition.get('max_kb'),
        )

    elif ctype == 'resolution':
        matched = _match_resolution(
            entry,
            condition.get('min_w'),
            condition.get('max_w'),
            condition.get('min_h'),
            condition.get('max_h'),
        )

    elif ctype == 'tag':
        query_tags = _parse_tag_query(condition.get('query', ''))
        if not query_tags:
            return True
        # OR 모드일 때 → 하나라도 포함
        # AND / NOT 모드일 때 → 모두 포함 여부로 판단
        if mode == 'or':
            matched = _match_tags(entry, query_tags)
        else:
            matched = _match_tags_all(entry, query_tags)
    else:
        return True

    if mode == 'not':
        return not matched
    return matched  # 'and' 또는 'or'


def _all_conditions_unused(conditions: List[Dict]) -> bool:
    return all(c.get('mode', 'unused') == 'unused' for c in conditions)


def entry_passes_filter(entry: FileEntry, conditions: List[Dict]) -> bool:
    """
    conditions 리스트를 평가하여 항목이 필터를 통과하는지 반환.

    로직:
    - 미사용 조건은 평가에서 제외.
    - AND 조건 중 하나라도 False → 전체 False.
    - NOT 조건 중 하나라도 False (즉 매칭됨) → 전체 False.
    - 활성 조건이 AND/NOT만 있고 모두 통과하면 → True.
    - OR 조건이 하나라도 있는 경우:
        AND/NOT 모두 통과 AND OR 중 하나 이상 통과 → True.
        활성 조건이 OR만 있는 경우 → OR 중 하나라도 통과하면 True.
    """
    active = [c for c in conditions if c.get('mode', 'unused') != 'unused']
    if not active:
        return True  # 조건 없음 → 전부 통과

    and_not_conds = [c for c in active if c.get('mode') in ('and', 'not')]
    or_conds = [c for c in active if c.get('mode') == 'or']

    # AND / NOT 조건 평가
    for cond in and_not_conds:
        if not _evaluate_condition(entry, cond):
            return False

    # OR 조건 평가
    if or_conds:
        return any(_evaluate_condition(entry, cond) for cond in or_conds)

    return True  # AND/NOT 조건만 있고 모두 통과


# ------------------------------------------------------------------
# 스캔 및 검색
# ------------------------------------------------------------------

def _collect_entries(folder: Path, recursive: bool) -> List[FileEntry]:
    """폴더 내 이미지 파일 기준으로 FileEntry 목록 수집."""
    entries = []
    iter_fn = folder.rglob if recursive else folder.iterdir

    seen_stems = set()

    # 이미지 기준으로 수집
    for f in iter_fn("*") if recursive else folder.iterdir():
        if not f.is_file():
            continue
        if is_image_file(f):
            txt = f.with_suffix(TEXT_EXTENSION)
            entry = FileEntry(
                image_path=f,
                txt_path=txt if txt.exists() else None,
            )
            entries.append(entry)
            seen_stems.add((f.parent, f.stem))

    # txt만 있는 파일도 수집 (이미지 없는 orphan txt)
    for f in (folder.rglob("*") if recursive else folder.iterdir()):
        if not f.is_file():
            continue
        if is_text_file(f):
            key = (f.parent, f.stem)
            if key not in seen_stems:
                entry = FileEntry(image_path=None, txt_path=f)
                entries.append(entry)

    return entries


def search_files(
    folder_path: str,
    recursive: bool,
    conditions: List[Dict],
    num_cores: int = 1,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> List[FileEntry]:
    """
    조건에 맞는 FileEntry 목록 반환.
    num_cores > 1 이면 ThreadPoolExecutor로 병렬 해상도 캐시 처리.
    """
    folder = Path(folder_path)
    if not folder.exists():
        return []

    entries = _collect_entries(folder, recursive)
    total = len(entries)
    if total == 0:
        return []

    # 해상도 조건이 있으면 미리 읽어야 하므로 병렬 처리
    needs_resolution = any(
        c.get('type') == 'resolution' and c.get('mode', 'unused') != 'unused'
        for c in conditions
    )

    if needs_resolution and num_cores > 1:
        def _preload_res(e: FileEntry):
            _ = e.resolution  # 캐시 없이 그냥 호출 (PIL 열기)
            return e

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as ex:
            futures = {ex.submit(_preload_res, e): i for i, e in enumerate(entries)}
            done = 0
            for fut in concurrent.futures.as_completed(futures):
                if stop_event and stop_event.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    return []
                done += 1
                if progress_callback:
                    progress_callback(done, total)

    results = []
    for i, entry in enumerate(entries):
        if stop_event and stop_event.is_set():
            break
        if entry_passes_filter(entry, conditions):
            results.append(entry)
        if progress_callback and not needs_resolution:
            progress_callback(i + 1, total)

    return results


# ------------------------------------------------------------------
# 파일 처리 (삭제 / 이동 / 복사)
# ------------------------------------------------------------------

def _resolve_conflict_path(dest_path: Path) -> Path:
    """대상 경로가 이미 존재하면 _{n} 접미사를 붙여 고유한 경로 반환."""
    if not dest_path.exists():
        return dest_path
    stem = dest_path.stem
    suffix = dest_path.suffix
    parent = dest_path.parent
    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def _get_target_files(entry: FileEntry, target_type: str) -> List[Path]:
    """
    target_type: 'both' | 'image' | 'txt'
    존재하는 파일만 반환.
    """
    files = []
    if target_type in ('both', 'image') and entry.has_image():
        files.append(entry.image_path)
    if target_type in ('both', 'txt') and entry.has_txt():
        files.append(entry.txt_path)
    return files


def process_entries(
    entries: List[FileEntry],
    action: str,           # 'delete' | 'move' | 'copy'
    target_type: str,      # 'both' | 'image' | 'txt'
    dest_folder: str = "", # 이동/복사 시 필요
) -> Tuple[int, int, List[str]]:
    """
    선택된 항목들에 대해 지정한 액션을 수행.
    Returns: (성공 수, 실패 수, 로그 메시지 리스트)
    """
    success = 0
    fail = 0
    logs = []

    if action in ('move', 'copy') and dest_folder:
        dest = Path(dest_folder)
        dest.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        files = _get_target_files(entry, target_type)
        if not files:
            logs.append(f"[건너뜀] 처리 대상 파일 없음: {entry.display_name}")
            continue

        for fpath in files:
            try:
                if action == 'delete':
                    fpath.unlink()
                    logs.append(f"[삭제] {fpath.name}")
                    success += 1

                elif action == 'move':
                    dest_file = _resolve_conflict_path(Path(dest_folder) / fpath.name)
                    shutil.move(str(fpath), str(dest_file))
                    moved_name = dest_file.name
                    suffix_note = f" → {moved_name}" if moved_name != fpath.name else ""
                    logs.append(f"[이동] {fpath.name}{suffix_note}")
                    success += 1

                elif action == 'copy':
                    dest_file = _resolve_conflict_path(Path(dest_folder) / fpath.name)
                    shutil.copy2(str(fpath), str(dest_file))
                    copied_name = dest_file.name
                    suffix_note = f" → {copied_name}" if copied_name != fpath.name else ""
                    logs.append(f"[복사] {fpath.name}{suffix_note}")
                    success += 1

            except Exception as e:
                logs.append(f"[실패] {fpath.name}: {e}")
                fail += 1

    return success, fail, logs


def get_orphan_warning(entries: List[FileEntry], target_type: str) -> List[str]:
    """
    target_type이 'image' 또는 'txt'일 때,
    처리 후 남게 될 짝 없는 파일 목록 반환 (사용자 경고용).
    target_type == 'both' 이면 빈 리스트 반환.
    """
    if target_type == 'both':
        return []

    orphans = []
    for entry in entries:
        if target_type == 'image' and entry.has_image() and entry.has_txt():
            orphans.append(str(entry.txt_path))
        elif target_type == 'txt' and entry.has_txt() and entry.has_image():
            orphans.append(str(entry.image_path))

    return orphans
