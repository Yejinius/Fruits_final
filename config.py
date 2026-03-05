"""
OS79 크롤러 설정 파일
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

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
REQUEST_DELAY_MIN = 1.0  # 요청 간 최소 대기 시간 (초)
REQUEST_DELAY_MAX = 3.0  # 요청 간 최대 대기 시간 (초)
REQUEST_TIMEOUT = 30     # 요청 타임아웃 (초)
MAX_RETRIES = 3          # 최대 재시도 횟수

# IP 차단 방지: 403/429 응답 시 백오프
BLOCK_BACKOFF_BASE = 10   # 기본 백오프 (초)
BLOCK_BACKOFF_MAX = 120   # 최대 백오프 (초)

# User-Agent 로테이션 (요청마다 랜덤 선택)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# 네이버 밴드 설정
BAND_PREVIEW_URL = os.getenv("BAND_PREVIEW_URL", "https://band.us/page/101768540")
BAND_PRODUCTION_URL = os.getenv("BAND_PRODUCTION_URL", "")
SHOPPING_MALL_URL = os.getenv("SHOPPING_MALL_URL", "http://localhost:5000")

# Aligo SMS 설정 (https://smartsms.aligo.in)
ALIGO_API_KEY = os.getenv("ALIGO_API_KEY", "")
ALIGO_USER_ID = os.getenv("ALIGO_USER_ID", "")
ALIGO_SENDER = os.getenv("ALIGO_SENDER", "")

# Admin 사이트
ADMIN_BASE_URL = "http://admin.open79.co.kr"
ADMIN_ID = os.getenv("ADMIN_ID", "")
ADMIN_PW = os.getenv("ADMIN_PW", "")

# Flask
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))

# 요청 헤더 (User-Agent는 요청마다 랜덤 선택되므로 여기선 제외)
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
