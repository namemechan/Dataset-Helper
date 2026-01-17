import os
import hashlib
from PIL import Image
from collections import defaultdict
import threading
from typing import List, Dict, Tuple, Set, Optional, Any
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

class UnionFind:
    """그룹핑을 위한 유니온-파인드 자료구조"""
    def __init__(self, elements):
        self.parent = {e: e for e in elements}

    def find(self, k):
        if self.parent[k] != k:
            self.parent[k] = self.find(self.parent[k])
        return self.parent[k]

    def union(self, a, b):
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a

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
                       progress_callback=None,
                       max_workers: int = None,
                       range_threshold: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """
        range_threshold: (start, end) 튜플. 설정되면 유사도 그룹 검색 모드로 동작하며 반환 구조가 달라짐.
        """
        
        self.stop_event.clear()
        workers = max_workers if max_workers else self.max_workers

        # 1. 파일 스캔
        files = self.scan_files(folder_path, recursive=True)
        total_files = len(files)
        if total_files == 0: return {}

        # 2. 메타데이터(해상도) 병렬 로드
        image_infos_map = {} # path -> ImageInfo
        
        if progress_callback: progress_callback(0, total_files, "파일 정보 읽는 중...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
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
        
        # 3. 그룹화
        potential_groups = defaultdict(list)
        if match_resolution:
            for info in image_infos:
                w, h = info.resolution
                if h == 0: ratio = 0
                else: ratio = round(w / h, 2)
                potential_groups[ratio].append(info)
        else:
            potential_groups['all'] = image_infos

        duplicates = {}
        group_id_counter = 0
        
        # --- 4-1. MD5 검사 ---
        if check_md5:
            md5_targets = []
            for group in potential_groups.values():
                if len(group) >= 2:
                    md5_targets.extend([info.path for info in group])
            
            if md5_targets:
                if progress_callback: progress_callback(0, len(md5_targets), "완전 중복(MD5) 계산 중...")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_path = {executor.submit(compute_md5_worker, p): p for p in md5_targets}
                    
                    completed = 0
                    for future in concurrent.futures.as_completed(future_to_path):
                        if self.stop_event.is_set(): break
                        path, md5 = future.result()
                        image_infos_map[path].md5_val = md5
                        
                        completed += 1
                        if progress_callback and completed % 10 == 0:
                            progress_callback(completed, len(md5_targets), "완전 중복(MD5) 계산 중...")

            # MD5 그룹핑 (Range 모드여도 MD5는 단일 결과)
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

        # --- 4-2. dHash 검사 (최적화 적용) ---
        if check_dhash and not self.stop_event.is_set():
            dhash_targets = []
            for group in potential_groups.values():
                if len(group) >= 2:
                    dhash_targets.extend([info.path for info in group])
            
            if dhash_targets:
                if progress_callback: progress_callback(0, len(dhash_targets), "유사도(dHash) 계산 중...")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_path = {executor.submit(compute_dhash_worker, p): p for p in dhash_targets}
                    
                    completed = 0
                    for future in concurrent.futures.as_completed(future_to_path):
                        if self.stop_event.is_set(): break
                        path, dhash = future.result()
                        image_infos_map[path].dhash_val = dhash
                        
                        completed += 1
                        if progress_callback and completed % 10 == 0:
                            progress_callback(completed, len(dhash_targets), "유사도(dHash) 계산 중...")

            if progress_callback: progress_callback(0, 0, "유사도 비교 분석 중...")

            # 비교 로직 시작
            if range_threshold:
                # === 범위 검색 모드 (최적화) ===
                start_th, end_th = range_threshold
                range_results = {} # {threshold: {group_id: ...}}
                
                # 1단계: 모든 관계(Edge) 수집 (최대 허용 오차 기준)
                all_edges = [] # (index_i, index_j, distance)
                
                # 빠른 처리를 위해 리스트화
                all_items = []
                for group in potential_groups.values():
                    if len(group) < 2: continue
                    valid_items = [info for info in group if info.dhash_val is not None]
                    if len(valid_items) < 2: continue
                    
                    # 그룹 내 비교
                    n = len(valid_items)
                    for i in range(n):
                        for j in range(i + 1, n):
                            dist = (valid_items[i].dhash_val ^ valid_items[j].dhash_val).bit_count()
                            if dist <= end_th:
                                # 전체 아이템 리스트 기준 인덱스로 저장하거나, 객체 자체를 저장
                                all_edges.append((valid_items[i], valid_items[j], dist))
                                
                if self.stop_event.is_set(): return {}

                # 2단계: 각 임계값별로 그룹핑 수행 (Union-Find)
                for th in range(start_th, end_th + 1):
                    # 해당 임계값 이하인 간선만 필터링
                    active_edges = [(u, v) for u, v, d in all_edges if d <= th]
                    if not active_edges:
                        continue
                        
                    # 관련된 모든 노드 추출
                    related_nodes = set()
                    for u, v in active_edges:
                        related_nodes.add(u)
                        related_nodes.add(v)
                    
                    uf = UnionFind(related_nodes)
                    for u, v in active_edges:
                        uf.union(u, v)
                    
                    # 그룹 생성
                    groups = defaultdict(list)
                    for node in related_nodes:
                        root = uf.find(node)
                        groups[root].append(node)
                    
                    # 결과 저장
                    th_groups = {}
                    local_counter = 0
                    for root, items in groups.items():
                        if len(items) > 1:
                            # MD5 중복 체크 (선택사항, 여기서는 범위 검색 특성상 모든 그룹을 보여주는게 좋음)
                            th_groups[f"similar_th{th}_{local_counter}"] = {'type': 'similar', 'items': items, 'threshold': th}
                            local_counter += 1
                    
                    if th_groups:
                        range_results[th] = th_groups

                return {'mode': 'range', 'md5': duplicates, 'dhash': range_results}

            else:
                # === 기존 단일 검색 모드 ===
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
                            
                            dist = (valid_items[i].dhash_val ^ valid_items[j].dhash_val).bit_count()
                            
                            if dist <= similarity_threshold:
                                current_group.append(valid_items[j])
                                visited.add(j)
                        
                        if len(current_group) > 1:
                            # MD5 중복 확인
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

        return duplicates

    def stop(self):
        self.stop_event.set()
