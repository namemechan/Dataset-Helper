import time
import math

def format_file_size(size_bytes: int) -> str:
    """Bytes를 사람이 읽기 쉬운 포맷으로 변환합니다 (KB, MB, GB)."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def calculate_progress(current: int, total: int) -> float:
    """진행률을 백분율로 계산합니다."""
    if total == 0:
        return 0.0
    return (current / total) * 100

def estimate_remaining_time(start_time: float, current_progress: float, total_progress: float = 100.0) -> str:
    """남은 예상 시간을 계산하여 문자열로 반환합니다."""
    if current_progress == 0:
        return "계산 중..."
    
    elapsed_time = time.time() - start_time
    total_estimated_time = elapsed_time / (current_progress / total_progress)
    remaining_time = total_estimated_time - elapsed_time

    if remaining_time < 0:
        return "완료 직전..."

    hours, rem = divmod(remaining_time, 3600)
    minutes, seconds = divmod(rem, 60)

    if hours > 0:
        return f"{int(hours):02d}시간 {int(minutes):02d}분 {int(seconds):02d}초"
    elif minutes > 0:
        return f"{int(minutes):02d}분 {int(seconds):02d}초"
    else:
        return f"{int(seconds):02d}초"

class RateLimiter:
    """간단한 비율 제한기. GUI 업데이트가 너무 자주 일어나는 것을 방지합니다."""
    def __init__(self, max_calls_per_second: float):
        self.min_interval = 1.0 / max_calls_per_second
        self.last_call_time = 0

    def is_allowed(self) -> bool:
        """지금 함수를 호출해도 되는지 확인합니다."""
        current_time = time.time()
        if current_time - self.last_call_time >= self.min_interval:
            self.last_call_time = current_time
            return True
        return False

