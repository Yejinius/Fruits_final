#!/bin/bash
# Young Fresh Mall 프로덕션 시작 스크립트
set -e

cd "$(dirname "$0")"

# 가상환경 활성화
source venv/bin/activate 2>/dev/null || {
    echo "venv 없음. 생성 중..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
}

# DB 초기화
python -c "from models import init_db; init_db()"

echo "============================================"
echo "  Young Fresh Mall - Production Server"
echo "============================================"

# Gunicorn으로 실행
exec gunicorn -c gunicorn.conf.py app:app
