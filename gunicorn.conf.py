"""Gunicorn 프로덕션 설정"""
import os

bind = f"{os.getenv('FLASK_HOST', '127.0.0.1')}:{os.getenv('FLASK_PORT', '5000')}"
workers = 2
threads = 4
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"

# 입금 확인 스케줄러는 첫 번째 워커에서만 실행
def on_starting(server):
    """서버 시작 시 스케줄러 가동"""
    pass

def post_worker_init(worker):
    """워커 초기화 후 (첫 번째 워커에서만 스케줄러 실행)"""
    if worker.age == 1:  # 첫 번째 워커
        from payment_checker import payment_checker
        payment_checker.start_periodic(interval_minutes=30)
