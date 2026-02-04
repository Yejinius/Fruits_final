"""
OS79 크롤러 설정 파일
"""
import os
from pathlib import Path

# 기본 경로
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "products.db"

# 디렉토리 생성
DATA_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

# 크롤링 대상 사이트
BASE_URL = "https://os79.co.kr"
GOODS_LIST_URL = f"{BASE_URL}/board_order/goods_list.asp"
GOODS_VIEW_URL = f"{BASE_URL}/board_order/goods_view.asp"

# 카테고리 코드 (원본 사이트 메뉴 기준)
CATEGORIES = {
    "A": "과일",
    "B": "고구마, 야채 BEST",
    "C": "수산",
    "D": "축산",
    "E": "쌀, 잡곡",
    "F": "건어물, 기타",
}

# 크롤링 설정
REQUEST_DELAY = 1.0  # 요청 간 대기 시간 (초)
REQUEST_TIMEOUT = 30  # 요청 타임아웃 (초)
MAX_RETRIES = 3  # 최대 재시도 횟수

# User-Agent
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 요청 헤더
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
