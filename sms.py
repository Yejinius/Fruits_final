"""
Aligo SMS 발송 모듈
- 주문 접수 시 고객에게 SMS 발송
- 입금 확인 시 고객에게 SMS 발송
"""
import re
import requests
from config import ALIGO_API_KEY, ALIGO_USER_ID, ALIGO_SENDER
from models import log_event


SMS_FOOTER = "(본 문자는 회신/유선연락이 불가능한 번호이오니, 카카오 오픈채팅(https://open.kakao.com/o/sNgjJoBb)으로 문의 주세요."


class AligoSMS:
    """Aligo 문자 발송 클래스"""

    API_URL = "https://apis.aligo.in/send/"

    def __init__(self):
        self.api_key = ALIGO_API_KEY
        self.user_id = ALIGO_USER_ID
        self.sender = ALIGO_SENDER

    def is_configured(self) -> bool:
        """API 키가 설정되어 있는지 확인"""
        return bool(self.api_key and self.user_id and self.sender)

    def send(self, receiver: str, msg: str, title: str = None) -> dict:
        """
        SMS/LMS 발송

        Args:
            receiver: 수신 번호 (01012345678 또는 010-1234-5678)
            msg: 메시지 내용 (90바이트 이하: SMS, 초과: LMS)
            title: LMS 제목 (LMS일 때만 사용)

        Returns:
            {'success': True/False, 'message': '...', 'response': {...}}
        """
        if not self.is_configured():
            print("[SMS] Aligo API 키가 설정되지 않았습니다. config.py를 확인하세요.")
            return {'success': False, 'message': 'API 키 미설정'}

        # 전화번호 하이픈 제거 + 유효성 검증
        receiver = receiver.replace("-", "")
        if not re.match(r'^01[016789]\d{7,8}$', receiver):
            log_event('warning', 'sms', f"잘못된 전화번호 형식: {receiver}")
            return {'success': False, 'message': f'잘못된 전화번호 형식: {receiver}'}

        # 메시지 길이에 따라 SMS/LMS 자동 결정
        msg_bytes = len(msg.encode('euc-kr', errors='ignore'))
        msg_type = "SMS" if msg_bytes <= 90 else "LMS"

        data = {
            "key": self.api_key,
            "user_id": self.user_id,
            "sender": self.sender,
            "receiver": receiver,
            "msg": msg,
            "msg_type": msg_type,
        }

        if msg_type == "LMS" and title:
            data["title"] = title

        try:
            resp = requests.post(self.API_URL, data=data, timeout=10)
            result = resp.json()

            success = result.get("result_code") == "1"
            if success:
                log_event('info', 'sms', f"SMS 발송 성공: {msg_type} → {receiver}")
            else:
                log_event('error', 'sms', f"SMS 발송 실패: {msg_type} → {receiver} - {result.get('message', '')}", detail=str(result))

            return {
                'success': success,
                'message': result.get('message', ''),
                'response': result,
            }
        except Exception as e:
            log_event('error', 'sms', f"SMS 발송 예외: {receiver} - {e}", detail=str(e))
            return {'success': False, 'message': str(e)}


# === 메시지 템플릿 ===

def build_order_received_msg(order) -> str:
    """주문 접수 완료 메시지"""
    items_text = ", ".join(
        f"{item.product_name} x {item.quantity}" for item in order.items
    )
    return (
        f"[Young Fresh Mall] 주문 접수 안내\n"
        f"\n"
        f"주문번호: {order.order_number}\n"
        f"상품: {items_text}\n"
        f"결제금액: {order.total_amount:,}원\n"
        f"\n"
        f"입금 확인 후 바로 발송해 드리겠습니다.\n"
        f"감사합니다.\n"
        f"\n"
        f"{SMS_FOOTER}"
    )


def build_payment_confirmed_msg(order) -> str:
    """입금 확인 완료 메시지"""
    items_text = ", ".join(
        f"{item.product_name} x {item.quantity}" for item in order.items
    )
    return (
        f"[Young Fresh Mall] 입금 확인 안내\n"
        f"\n"
        f"주문번호: {order.order_number}\n"
        f"상품: {items_text}\n"
        f"\n"
        f"입금이 확인되었습니다.\n"
        f"빠르게 발송 준비하겠습니다.\n"
        f"감사합니다.\n"
        f"\n"
        f"{SMS_FOOTER}"
    )


# === 발송 함수 ===

def send_order_received_sms(order) -> dict:
    """주문 접수 시 SMS 발송"""
    sms = AligoSMS()
    msg = build_order_received_msg(order)
    return sms.send(order.customer_phone, msg, title="주문 접수 안내")


def send_payment_confirmed_sms(order) -> dict:
    """입금 확인 시 SMS 발송"""
    sms = AligoSMS()
    msg = build_payment_confirmed_msg(order)
    return sms.send(order.customer_phone, msg, title="입금 확인 안내")


def build_out_of_stock_msg(order, unavailable_items: list) -> str:
    """품절 안내 메시지"""
    items_text = ", ".join(unavailable_items)
    return (
        f"[Young Fresh Mall] 품절 안내\n"
        f"\n"
        f"주문번호: {order.order_number}\n"
        f"품절 상품: {items_text}\n"
        f"\n"
        f"죄송합니다. 위 상품이 품절되어\n"
        f"주문 처리가 어렵게 되었습니다.\n"
        f"환불 안내를 위해 곧 연락드리겠습니다.\n"
        f"불편을 드려 죄송합니다.\n"
        f"\n"
        f"{SMS_FOOTER}"
    )


def send_out_of_stock_sms(order, unavailable_items: list) -> dict:
    """품절 안내 SMS 발송"""
    sms = AligoSMS()
    msg = build_out_of_stock_msg(order, unavailable_items)
    return sms.send(order.customer_phone, msg, title="품절 안내")
