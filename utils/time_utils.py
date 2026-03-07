from datetime import datetime
import pytz
from config import SLEEP_START, SLEEP_END

def get_kst_now():
    """현재 한국 시간을 반환합니다."""
    kst = pytz.timezone('Asia/Seoul')
    return datetime.now(kst)

def is_sleep_time():
    """현재가 설정된 취침 시간인지 확인합니다."""
    now = get_kst_now()
    return SLEEP_START <= now.hour < SLEEP_END

def calculate_d_day(deadline_str, current_datetime):
    """
    deadline_str (YYYY-MM-DD)와 현재 날짜를 비교해 디데이 포맷을 반환합니다.
    """
    if not deadline_str:
        return ""
    
    deadline_date = datetime.strptime(deadline_str, "%Y-%m-%d").date()
    today = current_datetime.date()
    d_day = (deadline_date - today).days

    if d_day > 0:
        return f" **(D-{d_day})**"
    elif d_day == 0:
        return f" **(D-Day)**"
    else:
        return f" **(D+{abs(d_day)})**"
