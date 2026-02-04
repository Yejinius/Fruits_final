"""
Admin 사이트 연동 테스트 스크립트
각 단계별로 실행하며 결과를 확인합니다.
"""
import requests
from bs4 import BeautifulSoup

class AdminTester:
    BASE_URL = "http://admin.open79.co.kr"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logged_in = False
        self.cookies_info = {}

    def step1_login(self, user_id, password):
        """Step 1: 로그인 테스트"""
        print("\n" + "="*60)
        print("STEP 1: 로그인 테스트")
        print("="*60)
        print(f"\n[요청 정보]")
        print(f"  URL: {self.BASE_URL}/m/include/asp/login_ok.asp")
        print(f"  Method: POST")
        print(f"  Data: m_id={user_id}, m_passwd=****")

        resp = self.session.post(
            f"{self.BASE_URL}/m/include/asp/login_ok.asp",
            data={"m_id": user_id, "m_passwd": password}
        )

        print(f"\n[응답 정보]")
        print(f"  Status Code: {resp.status_code}")
        print(f"  Response Length: {len(resp.text)} bytes")
        print(f"  Response Content: {resp.text[:200]}")

        # 쿠키 확인
        print(f"\n[설정된 쿠키]")
        for cookie in self.session.cookies:
            print(f"  {cookie.name} = {cookie.value[:30]}..." if len(cookie.value) > 30 else f"  {cookie.name} = {cookie.value}")
            self.cookies_info[cookie.name] = cookie.value

        # 로그인 성공 여부 확인
        if "location.replace" in resp.text and "/m/default.asp" in resp.text:
            self.logged_in = True
            print(f"\n[결과] ✅ 로그인 성공!")
        else:
            print(f"\n[결과] ❌ 로그인 실패")

        return self.logged_in

    def step2_verify_login(self):
        """Step 2: 로그인 상태 확인 (메인 페이지 접근)"""
        print("\n" + "="*60)
        print("STEP 2: 로그인 상태 확인")
        print("="*60)
        print(f"\n[요청 정보]")
        print(f"  URL: {self.BASE_URL}/m/default.asp")
        print(f"  Method: GET")

        resp = self.session.get(f"{self.BASE_URL}/m/default.asp")

        print(f"\n[응답 정보]")
        print(f"  Status Code: {resp.status_code}")
        print(f"  Response Length: {len(resp.text)} bytes")

        # 로그인된 사용자 이름 찾기
        soup = BeautifulSoup(resp.content, 'html.parser')
        user_info = soup.find('span', style=lambda x: x and 'color:blue' in x)

        if user_info:
            print(f"\n[결과] ✅ 로그인 확인됨: {user_info.text}")
            return True
        else:
            # 로그인 페이지로 리다이렉트 되었는지 확인
            if "login" in resp.text.lower():
                print(f"\n[결과] ❌ 로그인 페이지로 리다이렉트됨")
            else:
                print(f"\n[결과] ⚠️ 상태 확인 불가")
            return False

    def step3_get_customer_list(self):
        """Step 3: 고객 목록 조회"""
        print("\n" + "="*60)
        print("STEP 3: 고객 목록 조회")
        print("="*60)
        print(f"\n[요청 정보]")
        print(f"  URL: {self.BASE_URL}/m/customer/p_custom_list.asp")
        print(f"  Method: GET")

        resp = self.session.get(f"{self.BASE_URL}/m/customer/p_custom_list.asp")
        content = resp.content.decode('euc-kr', errors='ignore')

        print(f"\n[응답 정보]")
        print(f"  Status Code: {resp.status_code}")
        print(f"  Response Length: {len(content)} bytes")

        # 고객 목록 파싱
        soup = BeautifulSoup(content, 'html.parser')
        rows = soup.find_all('tr', class_='tr_class')

        print(f"\n[고객 목록] (최근 5명)")
        print("-" * 50)
        for i, row in enumerate(rows[:5]):
            cells = row.find_all('td')
            if len(cells) >= 4:
                no = cells[0].text.strip()
                name_link = cells[1].find('a')
                name = name_link.text.strip() if name_link else cells[1].text.strip()
                phone = cells[2].text.strip()
                address = cells[3].text.strip()[:30] + "..."
                print(f"  {i+1}. [{no}] {name} | {phone} | {address}")

        print(f"\n[결과] ✅ 총 {len(rows)}명의 고객 조회됨")
        return len(rows) > 0

    def step4_get_customer_form(self):
        """Step 4: 고객 등록 폼 확인"""
        print("\n" + "="*60)
        print("STEP 4: 고객 등록 폼 구조 확인")
        print("="*60)
        print(f"\n[요청 정보]")
        print(f"  URL: {self.BASE_URL}/m/customer/p_custom_regist.asp")
        print(f"  Method: GET")

        resp = self.session.get(f"{self.BASE_URL}/m/customer/p_custom_regist.asp")
        content = resp.content.decode('euc-kr', errors='ignore')

        print(f"\n[응답 정보]")
        print(f"  Status Code: {resp.status_code}")

        # 폼 필드 파싱
        soup = BeautifulSoup(content, 'html.parser')
        form = soup.find('form', id='frm_custom')

        if form:
            print(f"\n[폼 정보]")
            print(f"  Action: {form.get('action')}")
            print(f"  Method: {form.get('method')}")

            print(f"\n[입력 필드]")
            inputs = form.find_all('input')
            for inp in inputs:
                name = inp.get('name', '')
                type_ = inp.get('type', 'text')
                if name and type_ != 'hidden':
                    print(f"  - {name} (type: {type_})")

            textareas = form.find_all('textarea')
            for ta in textareas:
                name = ta.get('name', '')
                if name:
                    print(f"  - {name} (type: textarea)")

            print(f"\n[결과] ✅ 고객 등록 폼 구조 확인 완료")
            return True
        else:
            print(f"\n[결과] ❌ 폼을 찾을 수 없음")
            return False

    def step5_get_order_list(self):
        """Step 5: 주문 목록 조회"""
        print("\n" + "="*60)
        print("STEP 5: 주문 목록 조회")
        print("="*60)
        print(f"\n[요청 정보]")
        print(f"  URL: {self.BASE_URL}/m/customer/p_order_list.asp")
        print(f"  Method: GET")

        resp = self.session.get(f"{self.BASE_URL}/m/customer/p_order_list.asp")
        content = resp.content.decode('euc-kr', errors='ignore')

        print(f"\n[응답 정보]")
        print(f"  Status Code: {resp.status_code}")

        # 주문 목록 파싱
        soup = BeautifulSoup(content, 'html.parser')
        rows = soup.find_all('tr', class_='tr_class')

        print(f"\n[주문 목록] (최근 5건)")
        print("-" * 60)
        for i, row in enumerate(rows[:5]):
            cells = row.find_all('td')
            if len(cells) >= 4:
                name_link = cells[0].find('a')
                name = name_link.text.strip() if name_link else cells[0].text.strip()
                product_cell = cells[1]
                product_text = product_cell.get_text(separator=' | ', strip=True)[:50]
                qty = cells[2].text.strip()
                total = cells[3].text.strip()
                print(f"  {i+1}. {name} | 수량:{qty} | 합계:{total}")
                print(f"     상품: {product_text}...")

        print(f"\n[결과] ✅ 총 {len(rows)}건의 주문 조회됨")
        return len(rows) > 0

    def step6_get_order_detail(self, order_idx):
        """Step 6: 주문 상세 조회"""
        print("\n" + "="*60)
        print(f"STEP 6: 주문 상세 조회 (주문번호: {order_idx})")
        print("="*60)
        print(f"\n[요청 정보]")
        print(f"  URL: {self.BASE_URL}/m/customer/p_order_view.asp?g_goods_idx={order_idx}")
        print(f"  Method: GET")

        resp = self.session.get(f"{self.BASE_URL}/m/customer/p_order_view.asp?g_goods_idx={order_idx}")
        content = resp.content.decode('euc-kr', errors='ignore')

        print(f"\n[응답 정보]")
        print(f"  Status Code: {resp.status_code}")

        # 주문 상세 파싱
        soup = BeautifulSoup(content, 'html.parser')
        table = soup.find('table', class_='table_css')

        if table:
            print(f"\n[주문 상세 정보]")
            print("-" * 50)
            rows = table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    label = th.text.strip()
                    value = td.text.strip()[:50]
                    if label and value:
                        print(f"  {label}: {value}")

            print(f"\n[결과] ✅ 주문 상세 조회 완료")
            return True
        else:
            print(f"\n[결과] ❌ 주문 정보를 찾을 수 없음")
            return False


def main():
    """메인 테스트 함수"""
    tester = AdminTester()

    print("\n" + "="*60)
    print("  Admin 사이트 연동 테스트")
    print("  HTTP Request 방식으로 각 단계를 테스트합니다.")
    print("="*60)

    # 여기서 각 단계를 개별적으로 실행할 수 있습니다
    return tester


if __name__ == "__main__":
    tester = main()
