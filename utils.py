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

        # 마지막으로 적용한 값 추적 (실제 변화 없으면 즉시 종료)
        self._last_canvas_w = 0
        self._last_frame_h  = 0
        # 단일 debounce job (scrollregion + width를 한 채널로 통합)
        self._layout_job = None

        # 캔버스 생성 (스크롤 영역) - 테두리 제거
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)

        self.scrollable_frame = ttk.Frame(self.canvas)

        # height 미지정 → 컨텐츠가 자연스럽게 결정, 강제 지정하지 않음
        self.canvas_frame = self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )

        self.canvas.configure(yscrollcommand=scrollbar_y.set)

        # Grid 레이아웃
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")

        # canvas 리사이즈 → width 즉시 반영 + scrollregion 예약 (단일 진입점)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # 컨텐츠 변화 → scrollregion 갱신 예약만 (width는 건드리지 않음)
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)

        # 마우스 휠 바인딩:
        # bind_all 대신 canvas + scrollable_frame 에만 바인딩해
        # 다른 탭·위젯의 이벤트가 이 핸들러까지 전파되는 것을 차단한다.
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>",   self._on_mousewheel)   # Linux ↑
        self.canvas.bind("<Button-5>",   self._on_mousewheel)   # Linux ↓
        # scrollable_frame 내부 위젯 위에서도 휠이 동작하도록 enter/leave로 관리
        self.canvas.bind("<Enter>", self._bind_mousewheel_to_canvas)
        self.canvas.bind("<Leave>", self._unbind_mousewheel_from_canvas)

    # ------------------------------------------------------------------
    # 마우스 휠: Enter/Leave 방식으로 범위를 캔버스가 hover될 때만 한정
    # ------------------------------------------------------------------

    def _bind_mousewheel_to_canvas(self, event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>",   self._on_mousewheel)
        self.canvas.bind_all("<Button-5>",   self._on_mousewheel)

    def _unbind_mousewheel_from_canvas(self, event=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_canvas_configure(self, event):
        """캔버스 너비/높이 변화 — 너비는 내부 프레임에 맞추고,
        높이는 컨텐츠 vs 캔버스 중 큰 값으로 맞춰 창 리사이즈 시 위젯이 늘어나게 함"""
        w = event.width
        if w != self._last_canvas_w:
            self._last_canvas_w = w
            self.canvas.itemconfig(self.canvas_frame, width=w)

        # 창을 늘렸을 때 내부 프레임도 함께 늘어나도록 height 조정
        req_height = self.scrollable_frame.winfo_reqheight()
        new_height = max(event.height, req_height)
        self.canvas.itemconfig(self.canvas_frame, height=new_height)

        self._schedule_scrollregion()

    def _on_frame_configure(self, event):
        """컨텐츠 변화 — scrollregion 갱신만 예약"""
        self._schedule_scrollregion()

    def _schedule_scrollregion(self):
        """scrollregion 갱신을 debounce — 연속 이벤트를 마지막 한 번으로 합침.
        debounce를 50ms로 설정해 창 리사이즈 중 연속 발화를 충분히 묶는다."""
        if self._layout_job:
            self.canvas.after_cancel(self._layout_job)
        self._layout_job = self.canvas.after(50, self._apply_scrollregion)

    def _apply_scrollregion(self):
        """실제 scrollregion 적용 — 높이가 실제로 바뀐 경우에만 configure 호출"""
        self._layout_job = None
        bbox = self.canvas.bbox("all")
        if bbox is None:
            return
        frame_h = bbox[3]
        if frame_h == self._last_frame_h:
            return
        self._last_frame_h = frame_h
        self.canvas.configure(scrollregion=bbox)

    def _on_mousewheel(self, event):
        # ScrolledText 등 자체 스크롤을 가진 위젯 위에 있으면 위임하지 않음
        widget = event.widget
        try:
            widget_name = str(widget)
        except Exception:
            widget_name = ""
        # 위젯이 이 ScrollableFrame 소속이 아니면(다른 스크롤 영역) 무시
        if widget_name and not widget_name.startswith(str(self)):
            return
        # 윈도우에서는 event.delta가 120 단위, Linux는 num으로 구분
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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


def get_paired_files(folder_path: Path, recursive: bool = False) -> List[Tuple[Path, Path]]:
    """
    폴더 내 이미지-텍스트 파일 쌍 반환
    Args:
        folder_path: 검색할 폴더 경로
        recursive: 하위 폴더 포함 여부
    Returns: [(image_path, text_path), ...]
    """
    folder = Path(folder_path)
    if not folder.exists():
        return []
    
    # 파일 탐색
    if recursive:
        files = folder.rglob("*")
    else:
        files = folder.iterdir()
        
    # 모든 이미지 파일 찾기
    image_files = [f for f in files if f.is_file() and is_image_file(f)]
    
    paired = []
    for img in image_files:
        txt_file = img.with_suffix(TEXT_EXTENSION)
        if txt_file.exists():
            paired.append((img, txt_file))
    
    return sorted(paired, key=lambda x: str(x[0])) # 전체 경로 기준으로 정렬


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