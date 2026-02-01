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
        self.tag_set = None # 태그 집합 (Set[str])
        
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

def read_tags_worker(path: str) -> Tuple[str, Set[str]]:
    """이미지 경로에 대응하는 텍스트 파일의 태그 읽기"""
    try:
        txt_path = os.path.splitext(path)[0] + '.txt'
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # 쉼표로 구분하고 공백 제거, 소문자 변환하여 집합 생성
                tags = {t.strip().lower() for t in content.split(',') if t.strip()}
                return path, tags
    except Exception:
        pass
    return path, set()

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
                       check_tag: bool = False,
                       match_resolution: bool = True,
                       similarity_threshold: int = 5,
                       tag_similarity_threshold: int = 100,
                       progress_callback=None,
                       max_workers: int = None,
                       range_threshold: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """
        range_threshold: (start, end) 튜플. 설정되면 유사도 그룹 검색 모드로 동작하며 반환 구조가 달라짐.
        tag_similarity_threshold: 0~100 (Jaccard Similarity %)
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
        
        # 3. 그룹화 (비율 기준 1차 필터링)
        potential_groups = defaultdict(list)
        if match_resolution:
            for info in image_infos:
                w, h = info.resolution
                if h == 0: ratio = 0
                else: ratio = round(w / h, 2)
                potential_groups[ratio].append(info)
        else:
            potential_groups['all'] = image_infos

        # ---------------------------------------------------------
        # 4. 각 검사(MD5, Tag, dHash) 실행 및 데이터 수집
        # ---------------------------------------------------------
        
        # --- 4-1. MD5 ---
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
                        if progress_callback and completed % 50 == 0:
                             progress_callback(completed, len(md5_targets), "완전 중복(MD5) 계산 중...")

        # --- 4-2. Tag ---
        if check_tag:
            tag_targets = []
            for group in potential_groups.values():
                if len(group) >= 2:
                    tag_targets.extend([info.path for info in group])
            
            if tag_targets:
                if progress_callback: progress_callback(0, len(tag_targets), "태그 정보 읽는 중...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_path = {executor.submit(read_tags_worker, p): p for p in tag_targets}
                    completed = 0
                    for future in concurrent.futures.as_completed(future_to_path):
                        if self.stop_event.is_set(): break
                        path, tags = future.result()
                        image_infos_map[path].tag_set = tags
                        completed += 1
                        if progress_callback and completed % 50 == 0:
                            progress_callback(completed, len(tag_targets), "태그 정보 읽는 중...")

        # --- 4-3. dHash ---
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
                        if progress_callback and completed % 50 == 0:
                            progress_callback(completed, len(dhash_targets), "유사도(dHash) 계산 중...")

        if self.stop_event.is_set(): return {}

        # ---------------------------------------------------------
        # 5. 비교 및 그룹핑 (Union-Find)
        # ---------------------------------------------------------
        if progress_callback: progress_callback(0, 0, "비교 분석 중...")

        # 모든 간선(Edge) 수집
        # Edge 타입: ('md5', u, v), ('tag', u, v), ('dhash', u, v, distance)
        
        md5_edges = []
        tag_edges = []
        dhash_edges = [] # (u, v, dist)

        for group in potential_groups.values():
            if len(group) < 2: continue
            
            # 1) MD5 비교
            if check_md5:
                md5_map = defaultdict(list)
                for info in group:
                    if info.md5_val: md5_map[info.md5_val].append(info)
                for items in md5_map.values():
                    if len(items) > 1:
                        for i in range(len(items)-1):
                            md5_edges.append((items[i], items[i+1]))

            # 2) Tag 및 dHash 비교 (N^2 Loop 최적화)
            # 그룹 내 아이템 리스트
            items = group
            n = len(items)
            
            # 태그나 dHash 중 하나라도 체크되어 있으면 루프
            if check_tag or check_dhash:
                for i in range(n):
                    for j in range(i + 1, n):
                        u, v = items[i], items[j]
                        
                        # Tag Match Check
                        if check_tag and u.tag_set and v.tag_set:
                            # Jaccard Similarity
                            intersection = len(u.tag_set & v.tag_set)
                            union = len(u.tag_set | v.tag_set)
                            if union > 0:
                                sim = (intersection / union) * 100
                                if sim >= tag_similarity_threshold:
                                    tag_edges.append((u, v))
                        
                        # dHash Match Check
                        if check_dhash and u.dhash_val is not None and v.dhash_val is not None:
                            dist = (u.dhash_val ^ v.dhash_val).bit_count()
                            
                            # Range 모드면 최대치까지 수집, 아니면 Threshold 이하만 수집
                            limit = range_threshold[1] if range_threshold else similarity_threshold
                            if dist <= limit:
                                dhash_edges.append((u, v, dist))

        # ---------------------------------------------------------
        # 6. 결과 생성
        # ---------------------------------------------------------

        # 공통 함수: 간선 리스트를 받아 그룹 Dict 반환
        def build_groups_from_edges(nodes, edges):
            if not edges: return {}
            uf = UnionFind(nodes)
            for u, v in edges:
                uf.union(u, v)
            
            groups = defaultdict(list)
            for node in nodes:
                root = uf.find(node)
                groups[root].append(node)
            
            res_groups = {}
            counter = 0
            for root, items in groups.items():
                if len(items) > 1:
                    res_groups[f"group_{counter}"] = {'type': 'similar', 'items': items}
                    counter += 1
            return res_groups

        # 전체 노드 집합
        all_nodes = set(image_infos)

        # 1) 일반 모드 (Not Range Search)
        if not range_threshold:
            # 모든 활성 간선 합치기
            active_edges = []
            active_edges.extend(md5_edges)
            active_edges.extend(tag_edges)
            active_edges.extend([(u, v) for u, v, d in dhash_edges]) # 거리 조건은 위에서 이미 필터링됨
            
            final_groups = build_groups_from_edges(all_nodes, active_edges)
            
            # 결과 타입 마킹 (우선순위: exact > similar)
            # 여기서는 편의상 통합된 그룹을 'similar'로 퉁치거나, 
            # MD5만으로 묶인 그룹인지 확인하는 로직이 필요할 수 있으나,
            # "태그 기반"이 섞이면 'exact'라 부르기 모호함.
            # 다만 UI 표시를 위해 MD5 only 그룹은 분리하고 싶을 수 있음.
            # 하지만 사용자가 옵션을 섞어 썼으므로 통합 그룹핑이 맞음.
            
            # UI 호환성을 위해 타입 결정 로직 개선:
            # - MD5 only 체크 시: type='exact'
            # - 그 외: type='similar'
            
            result_type = 'exact' if check_md5 and not check_dhash and not check_tag else 'similar'
            for key, val in final_groups.items():
                val['type'] = result_type
            
            return final_groups

        # 2) 범위 검색 모드 (Range Search)
        else:
            # 반환 구조: {'mode': 'range', 'md5': {group...}, 'dhash': {threshold: {group...}}}
            # 태그 검색 결과는 어떻게? 
            # -> 사용자가 "태그 검색"도 켰다면, 태그로 인한 연결은 "유사도 0(혹은 현재 Range)"에 포함되어야 함.
            # -> 논리: "태그가 같으면(유사하면) 시각적 차이가 있어도 그룹핑한다"
            # -> 즉, 각 Threshold 단계마다 (dHash <= Th) U (Tag Edges) U (MD5 Edges) 를 수행.
            
            start_th, end_th = range_threshold
            range_results = {} 
            
            # MD5 결과는 별도로 담기 (UI에서 "완전 중복" 섹션에 표시됨)
            # 주의: Range 모드에서 MD5는 "0" 거리에 해당하지만, UI 트리가 분리되어 있음.
            # 태그 에지도 "별도 트리"로 보여주는게 좋을까? 아니면 dHash 트리에 합칠까?
            # 사용자가 "dHash랑 같이 쓰기 애매할려나?" 했으므로 합치는게 나음.
            
            # MD5 전용 결과 (UI 표시용)
            md5_only_groups = build_groups_from_edges(all_nodes, md5_edges)
            for v in md5_only_groups.values(): v['type'] = 'exact'

            # Range Loop
            for th in range(start_th, end_th + 1):
                # 해당 임계값에 맞는 dHash 에지 + 태그 에지 + MD5 에지
                current_dhash_edges = [(u, v) for u, v, d in dhash_edges if d <= th]
                
                # Tag와 MD5는 "항상 포함" (유사도에 관계없이 매칭된 것이므로)
                combined_edges = []
                combined_edges.extend([(u,v) for u,v in current_dhash_edges])
                combined_edges.extend(tag_edges)
                combined_edges.extend(md5_edges)
                
                if not combined_edges: continue
                
                # 그룹핑
                th_groups = build_groups_from_edges(all_nodes, combined_edges)
                if th_groups:
                    range_results[th] = th_groups

            return {'mode': 'range', 'md5': md5_only_groups, 'dhash': range_results}

    def stop(self):
        self.stop_event.set()
