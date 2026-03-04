"""
Aligo SMS 발송 모듈
- 주문 접수 시 고객에게 SMS 발송
- 입금 확인 시 고객에게 SMS 발송
"""
import requests
from config import ALIGO_API_KEY, ALIGO_USER_ID, ALIGO_SENDER


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

        # 전화번호 하이픈 제거
        receiver = receiver.replace("-", "")

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
            print(f"[SMS] {msg_type} → {receiver} | {'성공' if success else '실패'}: {result.get('message', '')}")

            return {
                'success': success,
                'message': result.get('message', ''),
                'response': result,
            }
        except Exception as e:
            print(f"[SMS] 발송 실패: {e}")
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
        f"감사합니다."
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
        f"감사합니다."
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
