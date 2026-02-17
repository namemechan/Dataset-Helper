import os
from pathlib import Path
from typing import List, Dict, Tuple, Set, Optional, Any
from PIL import Image
from utils import is_image_file, TEXT_EXTENSION, process_with_multicore
from collections import defaultdict

# 대용량 이미지 처리 시 경고 방지
Image.MAX_IMAGE_PIXELS = None

class DatasetAnalyzer:
    # 버킷 설정 상숫값
    BUCKET_RESO_STEPS = 64
    MIN_BUCKET_RESO = 256
    MAX_BUCKET_RESO = 2048

    @staticmethod
    def get_bucket_size(width: int, height: int, 
                        steps: int = 64, 
                        min_res: int = 256, 
                        max_res: int = 2048) -> Tuple[int, int]:
        w, h = width, height
        
        # 1. 최대 해상도 제한 및 비율 유지 축소
        if w > max_res or h > max_res:
            scale = min(max_res / w, max_res / h)
            w = max(min_res, int(w * scale))
            h = max(min_res, int(h * scale))

        orig_ratio = width / height
        best_w, best_h = w, h
        min_ratio_diff = float('inf')

        w_near = [ (w // steps) * steps,
                   ((w // steps) + 1) * steps ]
        h_near = [ (h // steps) * steps,
                   ((h // steps) + 1) * steps ]
        
        w_candidates = [v for v in w_near if min_res <= v <= max_res]
        h_candidates = [v for v in h_near if min_res <= v <= max_res]
        
        if not w_candidates: w_candidates = [max_res if w > max_res else min_res]
        if not h_candidates: h_candidates = [max_res if h > max_res else min_res]

        for cw in w_candidates:
            for ch in h_candidates:
                ratio = cw / ch
                diff = abs(orig_ratio - ratio)
                if diff < min_ratio_diff:
                    min_ratio_diff = diff
                    best_w, best_h = cw, ch
                    
        return best_w, best_h

    @staticmethod
    def analyze_folder_worker(folder_info: Dict) -> Dict:
        path = folder_info['path']
        include_untagged = folder_info['include_untagged']
        steps = folder_info.get('bucket_steps', 64)
        min_res = folder_info.get('bucket_min', 256)
        max_res = folder_info.get('bucket_max', 2048)
        
        images_in_folder = []
        buckets = defaultdict(int)
        image_dims = [] # 이미지 원본 차원 저장용
        
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
                                bucket = DatasetAnalyzer.get_bucket_size(w, h, steps, min_res, max_res)
                                buckets[f"{bucket[0]}x{bucket[1]}"] += 1
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
    def rebucketize(dims: List[Tuple[int, int]], steps: int, min_res: int, max_res: int) -> Dict[str, int]:
        """이미지 해상도 리스트를 받아 새로운 설정으로 버킷 분포를 다시 계산합니다."""
        new_buckets = defaultdict(int)
        for w, h in dims:
            bw, bh = DatasetAnalyzer.get_bucket_size(w, h, steps, min_res, max_res)
            new_buckets[f"{bw}x{bh}"] += 1
        return dict(new_buckets)

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
