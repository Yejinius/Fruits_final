"""
Admin 사이트 자동 주문 등록 모듈
- Young Fresh Mall 주문 → Admin(open79) 고객등록 + 주문등록 자동화
"""
import re
import requests
from datetime import datetime
from typing import Optional, Dict, Any

from models import get_session, Order, OrderItem, Product


class AdminOrderProcessor:
    """Admin 사이트에 주문을 자동 등록하는 프로세서"""

    BASE_URL = "http://admin.open79.co.kr"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logged_in = False

    def login(self) -> bool:
        """Admin 사이트 로그인"""
        resp = self.session.post(
            f"{self.BASE_URL}/m/include/asp/login_ok.asp",
            data={"m_id": "REDACTED_ID", "m_passwd": "REDACTED_PW"}
        )
        self.logged_in = "location.replace" in resp.text
        return self.logged_in

    def _post_form(self, path: str, data: Dict[str, str]) -> str:
        """Admin 사이트에 폼 제출 ([]를 인코딩하지 않는 raw body 방식)"""
        import urllib.parse
        url = f"{self.BASE_URL}{path}"
        parts = []
        for key, value in data.items():
            encoded_value = urllib.parse.quote(
                str(value).encode('euc-kr', errors='ignore'), safe='/-'
            )
            parts.append(f"{key}={encoded_value}")
        body = '&'.join(parts)
        resp = self.session.post(
            url, data=body,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        return resp.content.decode('euc-kr', errors='ignore')

    def _get_page(self, path: str) -> str:
        """Admin 페이지 가져오기"""
        url = f"{self.BASE_URL}{path}"
        resp = self.session.get(url)
        return resp.content.decode('euc-kr', errors='ignore')

    def register_customer(self, order: Order) -> Optional[str]:
        """
        Admin에 고객 등록
        Returns: customer_idx (c_goods_idx) or None
        """
        form_data = {
            "c_name": order.customer_name,
            "c_tel1": "",
            "c_tel2": order.customer_phone.replace("-", ""),
            "c_zipcode": order.zipcode or "",
            "c_address": order.address or "",
            "c_address_etc": order.address_detail or "",
            "c_tax_no": order.cash_receipt_no or "",
            "c_bigo": order.memo or ""
        }

        result = self._post_form("/m/customer/p_custom_regist_ok.asp", form_data)

        # 등록 후 고객 목록에서 방금 등록한 고객의 c_goods_idx 찾기
        list_html = self._get_page("/m/customer/p_custom_list.asp")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(list_html, 'html.parser')

        # 첫 번째 고객 행에서 c_goods_idx 추출
        first_row = soup.find('tr', class_='tr_class')
        if first_row:
            order_btn = first_row.find('span', class_='btn_m_white01')
            if order_btn and order_btn.get('onclick'):
                match = re.search(r"c_goods_idx=(\d+)", order_btn.get('onclick'))
                if match:
                    return match.group(1)

        return None

    def fetch_article_data(self) -> Dict[int, Dict[str, str]]:
        """js_article.asp에서 상품별 price, sell_d, sell_s, stock, delivery 데이터 가져오기"""
        resp = self.session.get(f"{self.BASE_URL}/include/js/js_article.asp")
        content = resp.content.decode('euc-kr', errors='ignore')

        raw_data = {}
        patterns = [
            (r"j_article_idx\[(\d+)\]\s*=\s*'(\d+)'", 'article_idx'),
            (r"j_article_price\[(\d+)\]\s*=\s*'(\d+)'", 'price'),
            (r"j_article_sell_d\[(\d+)\]\s*=\s*'(\d+)'", 'sell_d'),
            (r"j_article_sell_s\[(\d+)\]\s*=\s*'(\d+)'", 'sell_s'),
            (r"j_article_stock\[(\d+)\]\s*=\s*'(\d+)'", 'stock'),
            (r"j_article_delivery\[(\d+)\]\s*=\s*'(\d+)'", 'delivery'),
        ]
        for pattern, key in patterns:
            for m in re.finditer(pattern, content):
                i = int(m.group(1))
                raw_data.setdefault(i, {})[key] = m.group(2)

        result = {}
        for item in raw_data.values():
            if 'article_idx' in item:
                aid = int(item['article_idx'])
                result[aid] = {
                    'price': item.get('price', '0'),
                    'sell_d': item.get('sell_d', '0'),
                    'sell_s': item.get('sell_s', '0'),
                    'stock': item.get('stock', '0'),
                    'delivery': item.get('delivery', '0'),
                }
        return result

    def register_order(self, order: Order, customer_idx: str) -> bool:
        """
        Admin에 주문 등록
        수량이 N이면 동일 고객에게 주문서를 N회 등록
        Returns: True if success
        """
        # Admin에서 상품별 sell_d/sell_s/stock 가져오기
        article_data = self.fetch_article_data()

        for item in order.items:
            ad = article_data.get(item.article_idx, {})

            # 수량만큼 반복 등록 (Admin은 건별 등록 방식)
            for i in range(item.quantity):
                form_data = {
                    "g_panmae_gubun": "E",
                    "c_goods_idx": customer_idx,
                    "g_panmae_m_id": "JAEHONG86",
                    "g_goods_bigo": "",
                    "g_goods_bigo1": "",
                    "c_tax_no": order.cash_receipt_no or "",
                    "cate_idx[]": item.admin_category_idx or "",
                    "g_article_idx[]": str(item.article_idx),
                    "g_goods_name[]": item.product_name,
                    "g_goods_cnt[]": "1",
                    "g_goods_price[]": ad.get('price', str(item.price)),
                    "g_goods_sell[]": ad.get('sell_d', '0'),
                    "g_goods_delivery[]": ad.get('delivery', str(item.delivery_fee)),
                    "g_order_type": "입금",
                    "c_input_money[]": str((item.price + item.delivery_fee) * item.quantity),
                    "c_input_name": order.depositor_name or order.customer_name,
                    "g_goods_sell_d[]": ad.get('sell_d', '0'),
                    "g_goods_sell_s[]": ad.get('sell_s', '0'),
                    "g_goods_stock[]": ad.get('stock', '0'),
                }

                self._post_form("/m/customer/p_order_regist_ok.asp", form_data)
                if item.quantity > 1:
                    print(f"  [Admin] 주문 등록 {i+1}/{item.quantity}: {item.product_name}")

        return True

    def process_order(self, order: Order) -> Dict[str, Any]:
        """
        주문 1건을 Admin에 등록하는 전체 프로세스
        1. 로그인
        2. 고객 등록
        3. 주문 등록
        4. DB 상태 업데이트
        """
        db_session = get_session()
        # DB에서 최신 상태 로드
        order = db_session.query(Order).filter_by(id=order.id).first()

        if order.status not in ('pending', 'failed'):
            db_session.close()
            return {'success': False, 'error': f'주문 상태가 {order.status}입니다. pending 또는 failed만 처리 가능'}

        order.status = 'processing'
        db_session.commit()

        try:
            # 1. 로그인
            if not self.logged_in:
                if not self.login():
                    raise Exception("Admin 로그인 실패")

            # 2. 고객 등록
            customer_idx = self.register_customer(order)
            if not customer_idx:
                raise Exception("고객 등록 실패 - customer_idx를 찾을 수 없음")

            order.admin_customer_idx = customer_idx

            # 3. 주문 등록
            self.register_order(order, customer_idx)

            # 4. 성공 처리
            order.status = 'completed'
            order.admin_synced_at = datetime.now()
            order.error_message = None
            db_session.commit()

            result = {
                'success': True,
                'order_number': order.order_number,
                'admin_customer_idx': customer_idx
            }
            print(f"[Order] {order.order_number} → Admin 등록 완료 (customer_idx={customer_idx})")

        except Exception as e:
            order.status = 'failed'
            order.error_message = str(e)
            db_session.commit()
            result = {
                'success': False,
                'order_number': order.order_number,
                'error': str(e)
            }
            print(f"[Order] {order.order_number} → 실패: {e}")

        finally:
            db_session.close()

        return result

    def process_pending_orders(self) -> list:
        """pending 상태인 모든 주문 처리"""
        db_session = get_session()
        pending_orders = db_session.query(Order).filter(
            Order.status.in_(['pending', 'failed'])
        ).all()

        if not pending_orders:
            print("[Order] 처리할 주문이 없습니다")
            db_session.close()
            return []

        print(f"[Order] {len(pending_orders)}건 주문 처리 시작")
        db_session.close()

        # 로그인은 한 번만
        if not self.logged_in:
            self.login()

        results = []
        for order in pending_orders:
            result = self.process_order(order)
            results.append(result)

        return results

    def close(self):
        self.session.close()


def create_order(
    customer_name: str,
    customer_phone: str,
    zipcode: str,
    address: str,
    address_detail: str,
    items: list,
    depositor_name: str = None,
    cash_receipt_no: str = None,
    memo: str = None
) -> Order:
    """
    새 주문 생성 (DB 저장)

    items: [{'article_idx': 42563, 'quantity': 1}, ...]
    """
    db_session = get_session()

    # 주문번호 생성: YF-YYYYMMDD-NNN
    today = datetime.now().strftime('%Y%m%d')
    today_count = db_session.query(Order).filter(
        Order.order_number.like(f'YF-{today}-%')
    ).count()
    order_number = f"YF-{today}-{today_count + 1:03d}"

    order = Order(
        order_number=order_number,
        customer_name=customer_name,
        customer_phone=customer_phone,
        zipcode=zipcode,
        address=address,
        address_detail=address_detail,
        depositor_name=depositor_name or customer_name,
        cash_receipt_no=cash_receipt_no,
        memo=memo,
        status='pending'
    )

    total_amount = 0

    for item_data in items:
        article_idx = item_data['article_idx']
        quantity = item_data.get('quantity', 1)

        # DB에서 상품 정보 조회
        product = db_session.query(Product).filter_by(article_idx=article_idx).first()
        if not product:
            db_session.close()
            raise ValueError(f"상품을 찾을 수 없습니다: article_idx={article_idx}")

        order_item = OrderItem(
            article_idx=article_idx,
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            price=product.price or 0,
            delivery_fee=product.delivery_fee or 0,
            admin_category_idx=product.admin_category_idx
        )
        order.items.append(order_item)
        total_amount += (order_item.price + order_item.delivery_fee) * quantity

    order.total_amount = total_amount

    db_session.add(order)
    db_session.commit()

    print(f"[Order] 주문 생성: {order_number} ({customer_name}, {len(items)}건, {total_amount:,}원)")

    order_id = order.id
    db_session.close()

    # 새 세션으로 다시 로드해서 반환
    db_session = get_session()
    order = db_session.query(Order).filter_by(id=order_id).first()
    db_session.close()

    return order


if __name__ == "__main__":
    # 테스트: 샘플 주문 생성 및 Admin 등록
    print("=" * 60)
    print("주문 처리 테스트")
    print("=" * 60)

    # 1. 주문 생성
    order = create_order(
        customer_name="테스트고객",
        customer_phone="010-1234-5678",
        zipcode="02504",
        address="서울특별시 동대문구 서울시립대로 19",
        address_detail="101동 1002호",
        items=[
            {'article_idx': 42563, 'quantity': 1}
        ],
        depositor_name="테스트고객",
        cash_receipt_no="010-1234-5678",
        memo="테스트 주문입니다"
    )

    print(f"\n생성된 주문: {order.order_number}")
    print(f"상태: {order.status}")
    print(f"금액: {order.total_amount:,}원")

    # 2. Admin 등록 (실행 전 확인)
    confirm = input("\nAdmin에 등록하시겠습니까? (y/N): ")
    if confirm.lower() == 'y':
        processor = AdminOrderProcessor()
        try:
            result = processor.process_order(order)
            print(f"\n결과: {result}")
        finally:
            processor.close()
    else:
        print("Admin 등록을 건너뜁니다.")
