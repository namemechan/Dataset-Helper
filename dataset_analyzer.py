import os
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
        kohya-ss (sd-scripts) 스타일의 버킷 목록 생성 로직.
        설정된 target_res * target_res 면적을 최대한 유지하면서 64단위 조합을 만듭니다.
        """
        target_area = target_res * target_res
        buckets = set()
        
        # 1. 정방형 버킷 추가
        buckets.add((target_res, target_res))
        
        # 2. 가로/세로 조합 생성
        for w in range(min_res, max_res + 1, steps):
            # w * h <= target_area 가 되는 최대 h 찾기 (64배수)
            h = (target_area // w // steps) * steps
            if h < min_res: h = min_res
            if h > max_res: h = max_res
            
            if h >= min_res:
                buckets.add((w, h))
                
            # 반대 조합도 추가 (h * w)
            w2 = (target_area // h // steps) * steps
            if w2 < min_res: w2 = min_res
            if w2 > max_res: w2 = max_res
            if w2 >= min_res:
                buckets.add((w2, h))

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
        # 버킷 목록 생성 (성능을 위해 실제로는 호출 측에서 미리 생성해 전달하는 것이 좋으나, 
        # 여기서는 호환성을 위해 내부에서 생성하거나 캐싱 로직을 고려합니다.)
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
            'image_dims': image_dims
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
                return False

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
    def calculate_recommend_repeat(count: int, avg_count: float, batch_total: int) -> int:
        B = batch_total
        AVG = avg_count
        
        if count == 0:
            return B

        if count < AVG / 2:
            return B * 2
        elif count < AVG:
            return B
        elif count < AVG * 2:
            return max(1, B // 2)
        elif count < AVG * 4:
            return max(1, B // 4)
        elif count < AVG * 8:
            return max(1, B // 8)
        else:
            return 1

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
