#!/bin/bash
# band_keepalive.sh — Chrome 워치독 + 네이버/밴드 세션 Keep-Alive
# crontab: */360 * * * * /path/to/band_keepalive.sh >> /path/to/data/band_keepalive.log 2>&1
# (6시간마다 실행)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/venv/bin/python"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX band_keepalive 시작"

# 1. Chrome 워치독: 프로세스 확인 + 자동 재시작
if ! curl -s --connect-timeout 2 http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    echo "$LOG_PREFIX Chrome 미실행 감지 → 재시작"
    # 좀비 프로세스 정리
    pkill -f 'chromedriver' 2>/dev/null
    sleep 1
    "$PYTHON" -c "from band_poster import start_persistent_chrome; start_persistent_chrome()"
    sleep 3
fi

# 2. 세션 Keep-Alive: 밴드 페이지 접속하여 세션 갱신
"$PYTHON" -c "
from band_poster import BandPoster, is_chrome_running
if not is_chrome_running():
    print('  Chrome 미실행, 건너뜀')
    exit(0)

poster = BandPoster()
try:
    poster._init_driver()
    # 네이버 메인 접속 (쿠키 갱신)
    poster.driver.get('https://www.naver.com')
    import time; time.sleep(3)
    # 밴드 접속 (밴드 세션 갱신)
    poster.driver.get('https://band.us')
    time.sleep(3)
    # 쿠키 백업
    poster._save_cookies()
    print('  세션 갱신 완료')
except Exception as e:
    print(f'  세션 갱신 실패: {e}')
finally:
    poster.close()
"

echo "$LOG_PREFIX band_keepalive 완료"
