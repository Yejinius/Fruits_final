"""
입금 확인 자동화 모듈
- Admin 주문관리 페이지에서 입금 상태 확인
- 입금 확인 시 DB 업데이트 + SMS 발송
- 하이브리드 스케줄러: 주문 후 10분, 유휴 시 30분
"""
import re
import threading
from datetime import datetime
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

from models import get_session, Order, log_event
from config import ADMIN_BASE_URL, ADMIN_ID, ADMIN_PW
from sms import send_payment_confirmed_sms


class PaymentChecker:
    """Admin 사이트에서 입금 상태를 확인하고 SMS를 발송하는 체커"""

    BASE_URL = ADMIN_BASE_URL

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logged_in = False
        self._timer = None
        self._running = False

    def login(self) -> bool:
        resp = self.session.post(
            f"{self.BASE_URL}/m/include/asp/login_ok.asp",
            data={"m_id": ADMIN_ID, "m_passwd": ADMIN_PW}
        )
        self.logged_in = "location.replace" in resp.text
        return self.logged_in

    def _fetch_admin_orders(self) -> List[Dict]:
        """Admin 주문관리 페이지에서 주문 목록 파싱"""
        if not self.logged_in:
            if not self.login():
                log_event('error', 'payment', 'Admin 로그인 실패')
                return []

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/m/customer/p_order_list.asp",
                timeout=30
            )
            html = resp.content.decode('euc-kr', errors='ignore')
        except Exception as e:
            log_event('error', 'payment', f'Admin 주문목록 조회 실패: {e}')
            return []

        soup = BeautifulSoup(html, 'html.parser')
        rows = soup.find_all('tr', class_='tr_class')

        orders = []
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 5:
                continue

            customer_name = tds[0].get_text(strip=True)
            info_text = tds[1].get_text(strip=True, separator=' ')

            # 입금완료/입금대기 상태 파싱
            if '입금완료' in info_text:
                payment_status = 'paid'
            elif '입금대기' in info_text:
                payment_status = 'pending'
            else:
                payment_status = 'unknown'

            # g_goods_idx 추출
            link = row.find('a', href=re.compile(r'g_goods_idx='))
            g_goods_idx = None
            if link:
                match = re.search(r'g_goods_idx=(\d+)', link.get('href', ''))
                if match:
                    g_goods_idx = match.group(1)

            # 상품명 추출 (상태 키워드 뒤의 텍스트)
            product_name = ''
            for keyword in ['입금완료', '입금대기']:
                if keyword in info_text:
                    parts = info_text.split(keyword)
                    if len(parts) > 1:
                        product_name = parts[-1].strip()
                    break

            orders.append({
                'customer_name': customer_name,
                'payment_status': payment_status,
                'g_goods_idx': g_goods_idx,
                'product_name': product_name,
                'raw_info': info_text,
            })

        return orders

    def check_payments(self) -> Dict:
        """
        미입금 주문 확인 → Admin에서 입금완료된 건 자동 처리
        1:1 매칭: 각 Admin 입금완료 건은 하나의 DB 주문만 매칭

        Returns: {'checked': N, 'confirmed': N, 'still_pending': N}
        """
        db_session = get_session()
        awaiting_orders = db_session.query(Order).filter(
            Order.status == 'awaiting_payment',
            Order.payment_confirmed_at == None
        ).order_by(Order.created_at.asc()).all()

        if not awaiting_orders:
            log_event('info', 'payment', '미입금 주문 없음 — 체크 스킵')
            db_session.close()
            return {'checked': 0, 'confirmed': 0, 'still_pending': 0}

        log_event('info', 'payment', f'입금 확인 시작: {len(awaiting_orders)}건 체크')

        # Admin 주문 목록 가져오기
        admin_orders = self._fetch_admin_orders()

        # 입금완료된 Admin 주문 (1:1 매칭을 위해 사용 후 제거)
        paid_entries = [
            ao for ao in admin_orders if ao['payment_status'] == 'paid'
        ]

        confirmed_count = 0
        for order in awaiting_orders:
            # 1:1 매칭: 매칭된 Admin 엔트리의 인덱스 반환
            matched_idx = self._match_order_to_admin(order, paid_entries)
            if matched_idx is not None:
                self._confirm_payment_for_order(db_session, order)
                paid_entries.pop(matched_idx)  # 사용된 엔트리 제거 (1:1)
                confirmed_count += 1

        db_session.close()

        still_pending = len(awaiting_orders) - confirmed_count
        result = {
            'checked': len(awaiting_orders),
            'confirmed': confirmed_count,
            'still_pending': still_pending,
        }

        if confirmed_count > 0:
            log_event('info', 'payment', f'입금 확인 완료: {confirmed_count}건 확인, {still_pending}건 미입금')
        else:
            log_event('info', 'payment', f'입금 확인 결과: {still_pending}건 미입금')

        # 미입금 건이 남아있으면 30분 뒤 재실행
        if still_pending > 0:
            self.schedule_check(delay_minutes=30)

        return result

    def _match_order_to_admin(self, order: Order, paid_entries: List[Dict]) -> Optional[int]:
        """
        우리 주문과 Admin 입금완료 건을 매칭
        Returns: 매칭된 paid_entries 인덱스 (없으면 None)

        매칭 우선순위:
        1순위: 고객명 + 상품명 매칭 (가장 정확)
        2순위: 입금자명 + 상품명 매칭 (입금자명이 다를 수 있으므로)
        고객명만으로는 매칭하지 않음 (동일 고객 복수 주문 오매칭 방지)
        """
        # 1순위: 고객명 + 상품명 동시 매칭
        for idx, entry in enumerate(paid_entries):
            if entry['customer_name'] != order.customer_name:
                continue
            # 상품명 매칭 필수
            if self._match_product_name(order, entry):
                return idx

        # 2순위: 입금자명 + 상품명 매칭
        if order.depositor_name:
            for idx, entry in enumerate(paid_entries):
                if entry['customer_name'] != order.depositor_name:
                    continue
                if self._match_product_name(order, entry):
                    return idx

        return None

    def _match_product_name(self, order: Order, admin_entry: Dict) -> bool:
        """주문 상품명과 Admin 상품명 매칭 (부분 매칭)"""
        admin_product = admin_entry.get('product_name', '')
        if not admin_product:
            return False
        for item in order.items:
            if not item.product_name:
                continue
            # 양방향 부분 매칭 (Admin 상품명이 축약될 수 있으므로)
            if (item.product_name[:15] in admin_product or
                    admin_product[:15] in item.product_name):
                return True
        return False

    def _confirm_payment_for_order(self, db_session, order: Order):
        """단일 주문의 입금 확인 처리"""
        order.payment_confirmed_at = datetime.now()
        order.status = 'paid'
        db_session.commit()

        log_event('info', 'payment',
                  f'입금 확인: {order.order_number} ({order.customer_name}, {order.total_amount:,}원)',
                  related_id=order.order_number)

        # 입금확인 SMS 발송
        try:
            _ = order.items  # lazy load
            send_payment_confirmed_sms(order)
        except Exception as e:
            log_event('error', 'sms',
                      f'입금확인 SMS 발송 실패: {order.order_number} - {e}',
                      related_id=order.order_number)

    def confirm_payment_manual(self, order_number: str) -> Dict:
        """수동 입금 확인 (API에서 호출) — Admin 입금 상태 확인 후 처리"""
        db_session = get_session()
        order = db_session.query(Order).filter_by(order_number=order_number).first()

        if not order:
            db_session.close()
            return {'success': False, 'error': '주문을 찾을 수 없습니다.'}

        if order.payment_confirmed_at:
            db_session.close()
            return {'success': False, 'error': '이미 입금 확인된 주문입니다.'}

        if order.status not in ('awaiting_payment', 'pending'):
            db_session.close()
            return {'success': False, 'error': f'입금 대기 상태가 아닙니다. (현재: {order.status})'}

        # Admin에서 실제 입금 상태 확인
        admin_orders = self._fetch_admin_orders()
        paid_entries = [ao for ao in admin_orders if ao['payment_status'] == 'paid']
        _ = order.items  # lazy load for matching

        if self._match_order_to_admin(order, paid_entries) is None:
            db_session.close()
            return {'success': False, 'error': 'Admin에서 아직 입금 확인되지 않은 주문입니다.'}

        self._confirm_payment_for_order(db_session, order)
        db_session.close()

        return {'success': True, 'order_number': order_number}

    # ── 스케줄러 ──────────────────────────────────

    def schedule_check(self, delay_minutes=30):
        """지정 시간 후 check_payments 실행 예약"""
        self._cancel_timer()
        delay_seconds = delay_minutes * 60
        self._timer = threading.Timer(delay_seconds, self._run_check)
        self._timer.daemon = True
        self._timer.start()
        print(f"[Payment] {delay_minutes}분 후 입금 확인 예약됨")

    def on_new_order(self):
        """새 주문 발생 — 10분 뒤 체크 예약 (기존 예약 취소 후)"""
        self.schedule_check(delay_minutes=10)

    def start_periodic(self, interval_minutes=30):
        """30분 주기 체크 시작 (앱 시작 시 호출)"""
        # 미입금 건이 있는지 확인 후 스케줄링
        db_session = get_session()
        pending_count = db_session.query(Order).filter(
            Order.status == 'awaiting_payment',
            Order.payment_confirmed_at == None
        ).count()
        db_session.close()

        if pending_count > 0:
            print(f"[Payment] 미입금 {pending_count}건 있음 — {interval_minutes}분 후 첫 체크 시작")
            self.schedule_check(delay_minutes=interval_minutes)
        else:
            print("[Payment] 미입금 주문 없음 — 대기 모드")

    def _run_check(self):
        """타이머에서 실행되는 체크 함수"""
        try:
            self.check_payments()
        except Exception as e:
            log_event('error', 'payment', f'자동 입금 확인 실패: {e}', detail=str(e))

    def _cancel_timer(self):
        if self._timer and self._timer.is_alive():
            self._timer.cancel()
            self._timer = None

    def stop(self):
        """스케줄러 중지"""
        self._cancel_timer()
        self.session.close()


# 글로벌 인스턴스 (app.py에서 사용)
payment_checker = PaymentChecker()
