"""
공통 유틸리티 모듈
"""
from multiprocessing import Pool
from pathlib import Path
from typing import List, Tuple, Callable, Any

import tkinter as tk
from tkinter import ttk

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        # 캔버스 생성 (스크롤 영역) - 테두리 제거
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        # 캔버스 안에 프레임 그리기
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        self.canvas.configure(yscrollcommand=scrollbar_y.set)
        
        # Grid 레이아웃
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        
        # 가로 꽉 차게 하기 위한 바인딩
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        
        # 마우스 휠 바인딩
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        # 캔버스 크기가 변하면 내부 프레임 너비도 맞춤
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
        
        # 높이 제어: 
        # 1. 현재 내부 컨텐츠가 요구하는 최소 높이 확인
        req_height = self.scrollable_frame.winfo_reqheight()
        
        # 2. 캔버스(창) 높이가 컨텐츠보다 크면 -> 캔버스 높이에 맞춤 (꽉 채우기)
        # 3. 컨텐츠가 더 크면 -> 컨텐츠 높이 사용 (스크롤 활성화)
        new_height = max(event.height, req_height)
        
        self.canvas.itemconfig(self.canvas_frame, height=new_height)

    def _on_mousewheel(self, event):
        # 현재 포커스가 텍스트 박스 등이 아닐 때만 캔버스 스크롤
        # (ScrolledText 등 내부 스크롤과 충돌 방지)
        widget = event.widget
        if isinstance(widget, str) or not str(widget).startswith(str(self.canvas)):
             # 간단한 체크: 위젯이 이 캔버스의 자식이 아니면 무시할 수도 있음
             # 하지만 사용성을 위해 포커스된 위젯이 스크롤 가능한 위젯이 아니면 전체 스크롤
             pass
        
        # 윈도우에서는 event.delta가 120 단위
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

# 지원하는 이미지 확장자
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
TEXT_EXTENSION = '.txt'

# 인원수 태그 리스트
PERSON_COUNT_TAGS = {
    '1other',
    '1girl',
    '2girls',
    '3girls',
    '4girls',
    '5girls',
    '6+girls',
    'multiple girls',
    '1boy',
    '2boys',
    '3boys',
    '4boys',
    '5boys',
    '6+boys',
}


def is_image_file(file_path: Path) -> bool:
    """파일이 지원하는 이미지 파일인지 확인"""
    return file_path.suffix.lower() in IMAGE_EXTENSIONS


def is_text_file(file_path: Path) -> bool:
    """파일이 txt 파일인지 확인"""
    return file_path.suffix.lower() == TEXT_EXTENSION


def get_paired_files(folder_path: Path) -> List[Tuple[Path, Path]]:
    """
    폴더 내 이미지-텍스트 파일 쌍 반환
    Returns: [(image_path, text_path), ...]
    """
    folder = Path(folder_path)
    if not folder.exists():
        return []
    
    # 모든 이미지 파일 찾기
    image_files = [f for f in folder.iterdir() if f.is_file() and is_image_file(f)]
    
    paired = []
    for img in image_files:
        txt_file = img.with_suffix(TEXT_EXTENSION)
        if txt_file.exists():
            paired.append((img, txt_file))
    
    return sorted(paired, key=lambda x: x[0].name)


def process_with_multicore(func: Callable, items: List[Any], num_cores: int) -> List[Any]:
    """
    멀티코어로 작업 처리
    Args:
        func: 처리할 함수
        items: 처리할 아이템 리스트
        num_cores: 사용할 코어 수
    Returns:
        처리 결과 리스트
    """
    if num_cores <= 1 or len(items) == 0:
        return [func(item) for item in items]
    
    with Pool(processes=num_cores) as pool:
        results = pool.map(func, items)
    
    return results


def format_number(num: int, digits: int) -> str:
    """숫자를 지정된 자릿수로 포맷팅"""
    return str(num).zfill(digits)