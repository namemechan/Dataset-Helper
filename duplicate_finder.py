import os
import hashlib
from PIL import Image
from collections import defaultdict
import threading
from typing import List, Dict, Tuple, Set
import concurrent.futures

# 지원하는 이미지 확장자
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}

class ImageInfo:
    def __init__(self, path: str):
        self.path = path
        self.size = os.path.getsize(path)
        self.resolution = (0, 0)
        self.md5_val = None
        self.dhash_val = None # 이제 int형으로 저장
        
        # 생성 시에는 메타데이터를 읽지 않음 (병렬 처리를 위해 분리)

def process_image_meta(path: str) -> Tuple[str, Tuple[int, int]]:
    """해상도 정보만 빠르게 읽기 (병렬 처리용)"""
    try:
        with Image.open(path) as img:
            return path, img.size
    except Exception:
        return path, (0, 0)

def compute_md5_worker(path: str) -> Tuple[str, str]:
    """MD5 계산 워커"""
    hasher = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return path, hasher.hexdigest()
    except Exception:
        return path, ""

def compute_dhash_worker(path: str, hash_size: int = 8) -> Tuple[str, int]:
    """dHash 계산 워커 (정수형 반환)"""
    try:
        with Image.open(path) as img:
            img = img.convert("L")
            img = img.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.getdata())
            
            diff = 0
            width = hash_size + 1
            bit_index = 0
            
            for row in range(hash_size):
                for col in range(hash_size):
                    if pixels[row * width + col] > pixels[row * width + col + 1]:
                        diff |= (1 << bit_index)
                    bit_index += 1
            
            return path, diff
    except Exception:
        return path, None

class DuplicateFinder:
    def __init__(self):
        self.stop_event = threading.Event()
        # I/O 바운드 작업(파일 읽기)과 일부 CPU 작업(해시)을 위해 스레드 풀 사용
        # PIL과 hashlib은 GIL을 해제하므로 스레딩 효과가 좋음
        self.max_workers = min(32, (os.cpu_count() or 1) * 4) 

    def scan_files(self, folder_path: str, recursive: bool = True) -> List[str]:
        image_files = []
        if recursive:
            for root, _, files in os.walk(folder_path):
                if self.stop_event.is_set(): break
                for file in files:
                    if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                        image_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(folder_path):
                if self.stop_event.is_set(): break
                full_path = os.path.join(folder_path, file)
                if os.path.isfile(full_path) and os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                    image_files.append(full_path)
        return image_files

    def find_duplicates(self, 
                       folder_path: str, 
                       check_md5: bool = False,
                       check_dhash: bool = False,
                       match_resolution: bool = True,
                       similarity_threshold: int = 5,
                       progress_callback=None) -> Dict[str, Dict]:
        
        self.stop_event.clear()
        
        # 1. 파일 스캔
        files = self.scan_files(folder_path, recursive=True)
        total_files = len(files)
        if total_files == 0: return {}

        # 2. 메타데이터(해상도) 병렬 로드
        image_infos_map = {} # path -> ImageInfo
        
        if progress_callback: progress_callback(0, total_files, "파일 정보 읽는 중...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_path = {executor.submit(process_image_meta, f): f for f in files}
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_path):
                if self.stop_event.is_set(): break
                path, size = future.result()
                
                info = ImageInfo(path)
                info.resolution = size
                if size != (0, 0):
                    image_infos_map[path] = info
                
                completed += 1
                if progress_callback and completed % 50 == 0:
                    progress_callback(completed, total_files, "파일 정보 읽는 중...")

        if self.stop_event.is_set(): return {}

        image_infos = list(image_infos_map.values())
        
        # 3. 해상도별 그룹화 (속도 최적화) -> 비율(Aspect Ratio) 그룹화로 개선
        # 해상도가 달라도(리사이징됨) 비율이 같으면 유사 이미지일 확률이 높음
        potential_groups = defaultdict(list)
        if match_resolution:
            for info in image_infos:
                w, h = info.resolution
                if h == 0: 
                    ratio = 0
                else:
                    # 소수점 2자리까지 반올림하여 미세한 픽셀 오차 허용 (약 0.01 오차)
                    ratio = round(w / h, 2)
                potential_groups[ratio].append(info)
        else:
            potential_groups['all'] = image_infos

        duplicates = {}
        group_id_counter = 0
        
        # --- 4-1. MD5 검사 (병렬 처리) ---
        if check_md5:
            # MD5 계산이 필요한 파일 수집
            md5_targets = []
            for group in potential_groups.values():
                if len(group) >= 2:
                    md5_targets.extend([info.path for info in group])
            
            if md5_targets:
                if progress_callback: progress_callback(0, len(md5_targets), "완전 중복(MD5) 계산 중...")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_path = {executor.submit(compute_md5_worker, p): p for p in md5_targets}
                    
                    completed = 0
                    for future in concurrent.futures.as_completed(future_to_path):
                        if self.stop_event.is_set(): break
                        path, md5 = future.result()
                        image_infos_map[path].md5_val = md5
                        
                        completed += 1
                        if progress_callback and completed % 10 == 0:
                            progress_callback(completed, len(md5_targets), "완전 중복(MD5) 계산 중...")

            # 그룹핑 로직 (메인 스레드)
            for group in potential_groups.values():
                if len(group) < 2: continue
                hash_map = defaultdict(list)
                for info in group:
                    if info.md5_val:
                        hash_map[info.md5_val].append(info)
                
                for items in hash_map.values():
                    if len(items) > 1:
                        duplicates[f"exact_{group_id_counter}"] = {'type': 'exact', 'items': items}
                        group_id_counter += 1

        # --- 4-2. dHash 검사 (병렬 처리 + 정수 연산 최적화) ---
        if check_dhash and not self.stop_event.is_set():
            dhash_targets = []
            for group in potential_groups.values():
                if len(group) >= 2:
                    dhash_targets.extend([info.path for info in group])
            
            if dhash_targets:
                if progress_callback: progress_callback(0, len(dhash_targets), "유사도(dHash) 계산 중...")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_path = {executor.submit(compute_dhash_worker, p): p for p in dhash_targets}
                    
                    completed = 0
                    for future in concurrent.futures.as_completed(future_to_path):
                        if self.stop_event.is_set(): break
                        path, dhash = future.result()
                        image_infos_map[path].dhash_val = dhash
                        
                        completed += 1
                        if progress_callback and completed % 10 == 0:
                            progress_callback(completed, len(dhash_targets), "유사도(dHash) 계산 중...")

            # 비교 로직 (O(N^2)이지만 정수 비트 연산이라 매우 빠름)
            if progress_callback: progress_callback(0, 0, "유사도 비교 분석 중...")
            
            for group in potential_groups.values():
                if self.stop_event.is_set(): break
                if len(group) < 2: continue

                valid_items = [info for info in group if info.dhash_val is not None]
                n = len(valid_items)
                visited = set()
                
                for i in range(n):
                    if i in visited: continue
                    
                    current_group = [valid_items[i]]
                    visited.add(i)
                    
                    for j in range(i + 1, n):
                        if j in visited: continue
                        
                        # Hamming Distance (Integer Optimization)
                        # XOR 연산 후 1의 비트 수 세기 (Python 3.10+ bit_count() 사용)
                        dist = (valid_items[i].dhash_val ^ valid_items[j].dhash_val).bit_count()
                        
                        if dist <= similarity_threshold:
                            current_group.append(valid_items[j])
                            visited.add(j)
                    
                    if len(current_group) > 1:
                        # 이미 MD5로 100% 동일하게 묶인 그룹인지 확인 (중복 표시 방지)
                        if check_md5:
                            current_paths = set(item.path for item in current_group)
                            is_duplicate = False
                            for existing in duplicates.values():
                                if existing['type'] == 'exact':
                                    existing_paths = set(item.path for item in existing['items'])
                                    if existing_paths == current_paths:
                                        is_duplicate = True
                                        break
                            if is_duplicate: continue

                        duplicates[f"similar_{group_id_counter}"] = {'type': 'similar', 'items': current_group}
                        group_id_counter += 1

        return duplicates

    def stop(self):
        self.stop_event.set()
