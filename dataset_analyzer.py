import os
import sys
import json
import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Set, Optional, Any
from PIL import Image
from utils import is_image_file, TEXT_EXTENSION, process_with_multicore
from collections import defaultdict

# 대용량 이미지 처리 시 경고 방지
Image.MAX_IMAGE_PIXELS = None

class DatasetAnalyzer:
    # 버킷 설정 기본값 (UI에서 변경 가능)
    DEFAULT_STEPS = 64
    DEFAULT_MIN = 256
    DEFAULT_MAX = 2048

    @staticmethod
    def make_buckets(target_res: int, min_res: int, max_res: int, steps: int) -> List[Tuple[int, int]]:
        """
        kohya-ss (sd-scripts) 스타일의 정밀 버킷 목록 생성 로직.
        설정된 target_res * target_res 면적을 유지할 수 있는 유효한 해상도 조합만 생성합니다.
        """
        target_area = target_res * target_res
        buckets = set()

        # 1. 정방형 버킷 추가
        buckets.add((target_res, target_res))

        # 2. 가로/세로 조합 생성
        for w in range(min_res, max_res + 1, steps):
            # w * h <= target_area 가 되는 최대 h 찾기 (steps 배수)
            h = (target_area // w // steps) * steps

            # 범위를 벗어나는 경우 (극단적 종횡비) 억지로 맞추지 않고 제외
            if h < min_res or h > max_res:
                continue

            buckets.add((w, h))
            buckets.add((h, w))

        # 중복 제거 및 정렬
        sorted_buckets = sorted(list(buckets), key=lambda x: x[0] / x[1])
        return sorted_buckets

    @staticmethod
    def get_bucket_size(width: int, height: int, 
                        steps: int = 64, 
                        min_res: int = 256, 
                        max_res: int = 2048,
                        target_res: int = 1024) -> Tuple[int, int]:
        """
        이미지 해상도에 대해 가장 가까운 비율의 버킷을 반환합니다.
        """
        buckets = DatasetAnalyzer.make_buckets(target_res, min_res, max_res, steps)
        
        orig_ratio = width / height
        best_bucket = buckets[0]
        min_ratio_diff = float('inf')

        for bw, bh in buckets:
            ratio = bw / bh
            diff = abs(orig_ratio - ratio)
            if diff < min_ratio_diff:
                min_ratio_diff = diff
                best_bucket = (bw, bh)
                    
        return best_bucket

    @staticmethod
    def rebucketize(dims: List[Tuple[int, int]], steps: int, min_res: int, max_res: int, target_res: int = 1024) -> Dict[str, int]:
        """이미지 해상도 리스트를 받아 새로운 설정으로 버킷 분포를 다시 계산합니다."""
        new_buckets = defaultdict(int)
        # 버킷 목록 미리 생성
        bucket_list = DatasetAnalyzer.make_buckets(target_res, min_res, max_res, steps)
        bucket_ars = [bw / bh for bw, bh in bucket_list]
        
        for w, h in dims:
            orig_ar = w / h
            # 가장 가까운 비율 찾기
            diffs = [abs(orig_ar - b_ar) for b_ar in bucket_ars]
            best_idx = diffs.index(min(diffs))
            bw, bh = bucket_list[best_idx]
            new_buckets[f"{bw}x{bh}"] += 1
        return dict(new_buckets)

    @staticmethod
    def analyze_folder_worker(folder_info: Dict) -> Dict:
        path = folder_info['path']
        include_untagged = folder_info['include_untagged']
        steps = folder_info.get('bucket_steps', 64)
        min_res = folder_info.get('bucket_min', 256)
        max_res = folder_info.get('bucket_max', 2048)
        target_res = folder_info.get('target_res', 1024)
        
        # 버킷 목록 생성
        bucket_list = DatasetAnalyzer.make_buckets(target_res, min_res, max_res, steps)
        bucket_ars = [bw / bh for bw, bh in bucket_list]
        
        images_in_folder = []
        buckets = defaultdict(int)
        image_dims = []
        mismatches = [] # 종횡비 미스매치 리스트 추가
        
        try:
            for entry in os.scandir(path):
                if entry.is_file():
                    file_path = Path(entry.path)
                    if is_image_file(file_path):
                        if not include_untagged:
                            txt_file = file_path.with_suffix(TEXT_EXTENSION)
                            if not txt_file.exists():
                                continue
                        
                        try:
                            with Image.open(file_path) as img:
                                w, h = img.size
                                image_dims.append((w, h))
                                
                                # 가장 가까운 비율 버킷 찾기
                                orig_ar = w / h
                                diffs = [abs(orig_ar - b_ar) for b_ar in bucket_ars]
                                best_idx = diffs.index(min(diffs))
                                bw, bh = bucket_list[best_idx]
                                b_ar = bucket_ars[best_idx]
                                
                                # [New] 종횡비 미스매치 감지 (차이가 30% 이상일 때)
                                if abs(orig_ar - b_ar) / b_ar > 0.3:
                                    mismatches.append({
                                        'file_name': file_path.name,
                                        'resolution': f"{w}x{h}",
                                        'orig_ar': round(orig_ar, 3),
                                        'bucket_ar': round(b_ar, 3),
                                        'bucket_res': f"{bw}x{bh}",
                                        'folder_path': str(path)
                                    })
                                
                                buckets[f"{bw}x{bh}"] += 1
                                images_in_folder.append(file_path)
                        except:
                            continue
        except Exception as e:
            print(f"폴더 분석 오류 ({path}): {e}")

        return {
            'folder_name': path.name,
            'folder_path': str(path),
            'count': len(images_in_folder),
            'buckets': dict(buckets),
            'image_dims': image_dims,
            'mismatches': mismatches # 결과에 미스매치 포함
        }

    @staticmethod
    def scan_directories(root_path: str, recursive: bool, include_empty: bool, include_untagged: bool, 
                         num_cores: int = 1, bucket_settings: Dict = None) -> List[Dict]:
        root = Path(root_path)
        if not root.exists():
            return []

        target_folders = []
        def is_leaf_dir(p: Path) -> bool:
            try:
                for entry in os.scandir(p):
                    if entry.is_dir():
                        return False
                return True
            except:
                return True

        if recursive:
            for p in root.rglob("*"):
                if p.is_dir():
                    if include_empty:
                        if is_leaf_dir(p):
                            target_folders.append(p)
                    else:
                        target_folders.append(p)
        else:
            target_folders.append(root)
            if include_empty:
                for p in root.iterdir():
                    if p.is_dir() and is_leaf_dir(p):
                        target_folders.append(p)

        target_folders = sorted(list(set(target_folders)))
        
        worker_input = []
        for p in target_folders:
            info = {'path': p, 'include_untagged': include_untagged}
            if bucket_settings:
                info.update(bucket_settings)
            worker_input.append(info)
            
        results = process_with_multicore(DatasetAnalyzer.analyze_folder_worker, worker_input, num_cores)
        
        if not include_empty:
            results = [r for r in results if r['count'] > 0]

        return results

    @staticmethod
    def calculate_recommend_repeats(folders: List[Dict], batch_total: int) -> List[int]:
        """C+B 혼합 방식: 전체 폴더의 스텝 균형을 잡은 뒤 낭비율을 최소화하는 리핏 산출"""
        if not folders: return []
        if batch_total <= 0: return [1] * len(folders)
        
        # 1단계: 리핏 1 기준 각 폴더의 기본 스텝 계산
        base_steps = []
        for f in folders:
            _, _, steps = DatasetAnalyzer.calculate_waste(f['buckets'], 1, batch_total)
            base_steps.append(steps)
            
        # 2단계: 목표 스텝 설정 (0을 제외한 중앙값)
        import statistics
        valid_steps = [s for s in base_steps if s > 0]
        if not valid_steps: return [1] * len(folders)
        target_step = statistics.median(valid_steps)

        results = []
        for i, f in enumerate(folders):
            bs = base_steps[i]
            if bs <= 0:
                results.append(1)
                continue
            
            # 3단계: 리핏 역산 및 탐색 범위 설정
            approx_r = target_step / bs
            target_r = max(1, round(approx_r))
            
            # 낭비율 최소화 탐색 (목표 리핏 주변 ±25% 범위)
            search_range = max(2, int(target_r * 0.25))
            start_r = max(1, target_r - search_range)
            end_r = target_r + search_range
            
            best_r = target_r
            min_waste = float('inf')
            
            for r in range(start_r, end_r + 1):
                _, waste_rate, _ = DatasetAnalyzer.calculate_waste(f['buckets'], r, batch_total)
                # 낭비율이 더 낮거나, 낭비율이 같은 경우 목표 리핏에 더 가까운 값 선택
                if waste_rate < min_waste:
                    min_waste = waste_rate
                    best_r = r
                elif abs(waste_rate - min_waste) < 1e-7:
                    if abs(r - target_r) < abs(best_r - target_r):
                        best_r = r
            
            results.append(best_r)
        return results

    @staticmethod
    def calculate_waste(count_per_bucket: Dict[str, int], repeat: int, batch_total: int) -> Tuple[int, float, int]:
        """
        Returns: (waste_slots, waste_rate, total_steps)
        """
        total_slots = 0
        waste_slots = 0
        total_steps = 0
        
        for bucket_name, count in count_per_bucket.items():
            bucket_total = count * repeat
            remainder = bucket_total % batch_total
            
            steps = (bucket_total + batch_total - 1) // batch_total
            total_steps += steps
            
            if remainder > 0:
                waste = batch_total - remainder
                waste_slots += waste
            
            total_slots += steps * batch_total

        waste_rate = (waste_slots / total_slots * 100) if total_slots > 0 else 0
        return waste_slots, waste_rate, total_steps

    @staticmethod
    def calculate_theoretical_steps(count: int, repeat: int, batch_total: int) -> float:
        """단순 공식: (데이터 수 * 리핏) / 배치"""
        if batch_total == 0: return 0
        return (count * repeat) / batch_total


# ─────────────────────────────────────────────────────────────
# 데이터셋 스냅샷 시스템
# ─────────────────────────────────────────────────────────────

class DatasetSnapshot:
    """데이터셋 스냅샷 수집·저장·불러오기·비교 기능을 담당하는 정적 유틸리티 클래스."""

    SNAPSHOT_FOLDER = "snapshots"
    FORMAT_VERSION = "1.0"

    # 지원 이미지 확장자 (utils.IMAGE_EXTENSIONS와 동일)
    _IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}

    # ── 경로 헬퍼 ──────────────────────────────────────────────
    @staticmethod
    def get_snapshot_dir() -> Path:
        """스냅샷 저장 폴더 경로를 반환합니다 (EXE 패키징 환경 고려)."""
        if getattr(sys, 'frozen', False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent
        return base / DatasetSnapshot.SNAPSHOT_FOLDER

    # ── 포맷 유틸 ─────────────────────────────────────────────
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """bytes를 사람이 읽기 쉬운 단위로 변환합니다."""
        if size_bytes == 0:
            return "0 B"
        size_bytes = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    @staticmethod
    def _is_image(path: Path) -> bool:
        return path.suffix.lower() in DatasetSnapshot._IMAGE_EXTS

    @staticmethod
    def _is_leaf(p: Path) -> bool:
        """하위 디렉토리가 없는 최하위 폴더인지 확인합니다."""
        try:
            return not any(x.is_dir() for x in p.iterdir())
        except Exception:
            return True

    # ── 데이터 수집 ───────────────────────────────────────────
    @staticmethod
    def collect(root_path: str) -> Optional[dict]:
        """
        지정된 루트 폴더의 구조와 데이터셋 현황을 수집하여 딕셔너리로 반환합니다.
        반환 딕셔너리는 save()에 바로 전달할 수 있습니다.
        """
        root = Path(root_path)
        if not root.exists():
            return None

        leaf_folders: List[dict] = []

        def scan_dir(p: Path) -> None:
            if DatasetSnapshot._is_leaf(p):
                images: List[str] = []
                pairs: int = 0
                folder_size: int = 0
                try:
                    for f in p.iterdir():
                        if f.is_file():
                            try:
                                folder_size += f.stat().st_size
                            except OSError:
                                pass
                            if DatasetSnapshot._is_image(f):
                                images.append(f.stem)
                    for stem in images:
                        if (p / f"{stem}.txt").exists():
                            pairs += 1
                except Exception:
                    pass

                # 루트 기준 상대 경로 계산
                try:
                    rel = str(p.relative_to(root))
                except ValueError:
                    rel = p.name
                # 루트 자체가 리프인 경우 표시용으로 이름 사용
                display_path = root.name if rel == '.' else rel

                leaf_folders.append({
                    'rel_path': display_path,
                    'name': p.name,
                    'image_count': len(images),
                    'pair_count': pairs,
                    'unpaired': len(images) - pairs,
                    'size_bytes': folder_size,
                })
            else:
                try:
                    for child in sorted(p.iterdir()):
                        if child.is_dir():
                            scan_dir(child)
                except Exception:
                    pass

        scan_dir(root)

        # 폴더 트리 구조 생성
        def build_tree(p: Path) -> dict:
            node: dict = {'name': p.name, 'children': []}
            try:
                for child in sorted(p.iterdir()):
                    if child.is_dir():
                        node['children'].append(build_tree(child))
            except Exception:
                pass
            return node

        total_images = sum(f['image_count'] for f in leaf_folders)
        total_pairs  = sum(f['pair_count']  for f in leaf_folders)
        total_size   = sum(f['size_bytes']  for f in leaf_folders)

        return {
            'format_version':    DatasetSnapshot.FORMAT_VERSION,
            'name':              '',   # save() 호출 시 채워짐
            'created_at':        datetime.datetime.now().isoformat(),
            'root_path':         str(root),
            'root_name':         root.name,
            'memo':              '',   # save() 호출 시 채워짐
            'total_images':      total_images,
            'total_pairs':       total_pairs,
            'total_unpaired':    total_images - total_pairs,
            'total_size_bytes':  total_size,
            'leaf_folder_count': len(leaf_folders),
            'leaf_folders':      leaf_folders,
            'folder_tree':       build_tree(root),
        }

    # ── 저장 ──────────────────────────────────────────────────
    @staticmethod
    def save(data: dict, name: str, memo: str = '') -> Path:
        """
        수집된 스냅샷 데이터를 JSON 파일로 저장합니다.
        타임스탬프를 파일명에 포함하여 이름 중복을 방지합니다.
        저장된 파일의 Path를 반환합니다.
        """
        snapshot_dir = DatasetSnapshot.get_snapshot_dir()
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        data = data.copy()
        data['name'] = name
        data['memo'] = memo

        # 파일명용 안전 문자열 변환
        safe = "".join(
            c if (c.isalnum() or c in ('-', '_', ' ')) else '_'
            for c in name
        ).strip().replace(' ', '_')
        if not safe:
            safe = 'snapshot'

        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{safe}_{ts}.json"
        filepath = snapshot_dir / filename

        # 혹시 동일 파일명 존재 시 카운터 추가
        counter = 1
        while filepath.exists():
            filepath = snapshot_dir / f"{safe}_{ts}_{counter}.json"
            counter += 1

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    # ── 불러오기 ──────────────────────────────────────────────
    @staticmethod
    def load(filepath: str) -> dict:
        """JSON 스냅샷 파일을 딕셔너리로 불러옵니다."""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def list_snapshots() -> List[Tuple[str, str]]:
        """
        snapshots 폴더 내 저장된 스냅샷 목록을 최신순으로 반환합니다.
        Returns: [(표시이름, 절대파일경로), ...]
        """
        snapshot_dir = DatasetSnapshot.get_snapshot_dir()
        if not snapshot_dir.exists():
            return []

        result: List[Tuple[str, str]] = []
        files = sorted(
            snapshot_dir.glob('*.json'),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    meta = json.load(fp)
                dt_str = meta.get('created_at', '')[:16].replace('T', ' ')
                display = f"[{dt_str}]  {meta.get('name', f.stem)}"
                result.append((display, str(f)))
            except Exception:
                result.append((f.stem, str(f)))
        return result

    # ── 비교 ──────────────────────────────────────────────────
    @staticmethod
    def compare(base: dict, comp: dict) -> dict:
        """
        두 스냅샷을 비교하여 차이점 딕셔너리를 반환합니다.

        비교 전략:
          1. rel_path 완전 일치 → 정확 매칭
          2. 이름(name) 일치로 폴더 이동/재구성 감지 → 퍼지 매칭
          3. 나머지 → 추가/삭제 처리

        Returns dict with keys:
          added, removed, changed, fuzzy_matched, unchanged_count, summary
        """
        base_map: Dict[str, dict] = {f['rel_path']: f for f in base.get('leaf_folders', [])}
        comp_map: Dict[str, dict] = {f['rel_path']: f for f in comp.get('leaf_folders', [])}

        base_keys = set(base_map)
        comp_keys = set(comp_map)

        exact_common = base_keys & comp_keys
        base_only    = base_keys - comp_keys
        comp_only    = comp_keys - base_keys

        # ── 퍼지 매칭 (폴더 이름 기준) ────────────────────────
        # comp_only 중 같은 이름을 가진 폴더를 base_only와 연결
        comp_name_map: Dict[str, List[str]] = defaultdict(list)
        for ck in comp_only:
            comp_name_map[comp_map[ck]['name']].append(ck)

        fuzzy_matched: List[dict] = []
        matched_base: Set[str] = set()
        matched_comp: Set[str] = set()

        for bk in sorted(base_only):
            bname = base_map[bk]['name']
            candidates = [
                ck for ck in comp_name_map.get(bname, [])
                if ck not in matched_comp
            ]
            if candidates:
                ck = candidates[0]
                b = base_map[bk]
                c = comp_map[ck]
                fuzzy_matched.append({
                    'base_path':    bk,
                    'comp_path':    ck,
                    'base':         b,
                    'comp':         c,
                    'delta_images': c['image_count'] - b['image_count'],
                    'delta_pairs':  c['pair_count']  - b['pair_count'],
                    'delta_size':   c['size_bytes']  - b['size_bytes'],
                })
                matched_base.add(bk)
                matched_comp.add(ck)

        # ── 추가 / 삭제 ──────────────────────────────────────
        removed = [
            {'path': k, **base_map[k]}
            for k in base_only if k not in matched_base
        ]
        added = [
            {'path': k, **comp_map[k]}
            for k in comp_only if k not in matched_comp
        ]

        # ── 변경 / 변경없음 ──────────────────────────────────
        changed: List[dict] = []
        unchanged_count = 0
        for k in exact_common:
            b = base_map[k]
            c = comp_map[k]
            if b['image_count'] != c['image_count'] or b['size_bytes'] != c['size_bytes']:
                changed.append({
                    'path':         k,
                    'base':         b,
                    'comp':         c,
                    'delta_images': c['image_count'] - b['image_count'],
                    'delta_pairs':  c['pair_count']  - b['pair_count'],
                    'delta_size':   c['size_bytes']  - b['size_bytes'],
                })
            else:
                unchanged_count += 1

        # ── 요약 통계 ─────────────────────────────────────────
        b_img  = base.get('total_images',     0)
        c_img  = comp.get('total_images',     0)
        b_pair = base.get('total_pairs',      0)
        c_pair = comp.get('total_pairs',      0)
        b_sz   = base.get('total_size_bytes', 0)
        c_sz   = comp.get('total_size_bytes', 0)

        d_img  = c_img  - b_img
        d_pair = c_pair - b_pair
        d_sz   = c_sz   - b_sz

        rate_img = (d_img / b_img * 100) if b_img > 0 else 0.0
        rate_sz  = (d_sz  / b_sz  * 100) if b_sz  > 0 else 0.0

        return {
            'added':           added,
            'removed':         removed,
            'changed':         changed,
            'fuzzy_matched':   fuzzy_matched,
            'unchanged_count': unchanged_count,
            'summary': {
                'delta_images':     d_img,
                'delta_pairs':      d_pair,
                'delta_size':       d_sz,
                'rate_images':      rate_img,
                'rate_size':        rate_sz,
                'added_count':      len(added),
                'removed_count':    len(removed),
                'changed_count':    len(changed),
                'fuzzy_count':      len(fuzzy_matched),
                'unchanged_count':  unchanged_count,
            },
        }
