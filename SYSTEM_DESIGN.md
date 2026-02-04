# Young Fresh Mall - 주문 관리 시스템 설계 계획서

## 1. 프로젝트 개요

### 1.1 목표
- 프론트엔드 쇼핑몰에서 고객 주문을 접수
- admin.open79.co.kr 관리 시스템과 자동 연동
- 주문 처리 전 과정의 자동화

### 1.2 전체 플로우
```
[고객] → [Young Fresh Mall] → [주문 DB] → [자동화 시스템] → [Admin 사이트]
                                              ↓
                                    [주문 확인 및 DB 업데이트]
```

---

## 2. Admin 사이트 분석 결과

### 2.1 로그인
- **URL**: `http://admin.open79.co.kr/m/include/asp/login_ok.asp`
- **Method**: POST
- **필드**: `m_id`, `m_passwd`
- **인증 방식**: 쿠키 기반 세션 (`m%5Fid1`, `ASPSESSIONID*`)

### 2.2 고객 등록
- **폼 URL**: `http://admin.open79.co.kr/m/customer/p_custom_regist.asp`
- **처리 URL**: `http://admin.open79.co.kr/m/customer/p_custom_regist_ok.asp`
- **Method**: POST
- **필드**:
  | 필드명 | 설명 | 필수 |
  |--------|------|------|
  | c_name | 고객명 | O |
  | c_tel1 | 전화번호 | X |
  | c_tel2 | 휴대폰 | O |
  | c_zipcode | 우편번호 | X |
  | c_address | 기본주소 | X |
  | c_address_etc | 상세주소 | X |
  | c_tax_no | 현금영수증 번호 | X |
  | c_bigo | 기타 내용 | X |

### 2.3 주문서 작성
- **폼 URL**: `http://admin.open79.co.kr/m/customer/p_order_regist.asp`
- **처리 URL**: `http://admin.open79.co.kr/m/customer/p_order_regist_ok.asp`
- **Method**: POST
- **필드**:
  | 필드명 | 설명 |
  |--------|------|
  | c_goods_idx | 고객 ID (고객등록 후 반환값) |
  | g_panmae_gubun | 판매구분 (E = 오픈파트너) |
  | g_panmae_m_id | 판매자 ID |
  | cate_idx[] | 카테고리 번호 |
  | g_article_idx[] | 상품 번호 |
  | g_goods_cnt[] | 주문 수량 |
  | g_goods_sell[] | 판매가격 |
  | g_goods_delivery[] | 택배비 |
  | g_order_type | 결제방법 (입금/카드) |
  | c_input_money[] | 고객 입금액 |
  | c_input_name | 입금자명 |
  | c_tax_no | 현금영수증 번호 |
  | g_goods_bigo | 배송 메세지 |
  | g_goods_bigo1 | 비고사항 |

### 2.4 주문 목록 조회
- **URL**: `http://admin.open79.co.kr/m/customer/p_order_list.asp`
- **검색 파라미터**: `search_key`, `search_txt`, `s_date_start`, `s_date_end`

### 2.5 주문 상세 조회
- **URL**: `http://admin.open79.co.kr/m/customer/p_order_view.asp?g_goods_idx={주문번호}`

### 2.6 카테고리 매핑 (Admin 사이트 기준)
```
5  = 1. 고구마/감자/야채/옥수수
6  = 2. 사과/배/토마토
13 = 3. 참외/귤종류/포도종류/유자
7  = 4. 감/대추/밤/복숭아/딸기
8  = 5. (경매)수입과일
14 = 6. (직거래)수입과일
10 = 7. 수박/멜론/키위/백향과/모과
9  = 8. 블루베리/자두/살구/매실
15 = 10. 쌀/잡곡
16 = 11. (직거래)밤/땅콩/피데기/건어
17 = 12. 생선 종류
18 = 13. 조개종류/조개살종류
20 = 14. 오징어,문어/낙지/쭈꾸미
21 = 15. 육류
23 = 16. 직거래 농가 과일,야채
24 = 17. 굴비상품
34 = 18. 새우/대게/꽃게
26 = 19. 갈치,고등어
27 = 20. 장어
33 = 21. 전복/김/개불/멍게/해삼
29 = 22. 노가리/멸치/꼴뚜기
30 = 23. 유정란
31 = 24. (직거래)기타상품
```

---

## 3. 자동화 방법 비교

### 3.1 방법 1: HTTP 직접 요청 (requests 라이브러리) ✅ **권장**

**장점:**
- 빠른 실행 속도 (브라우저 렌더링 불필요)
- 낮은 리소스 사용량
- 서버 부하 최소화
- 배포 및 유지보수 용이
- 헤드리스 브라우저 불필요

**단점:**
- JavaScript 동적 콘텐츠 처리 불가
- 세션 관리 직접 구현 필요

**적용 가능성 분석:**
- ✅ 로그인: 단순 POST 요청 (JS 검증 없음)
- ✅ 고객 등록: 단순 폼 제출
- ⚠️ 주문서 작성: 품목 선택 시 Ajax 호출 있음 (별도 처리 필요)
- ✅ 주문 조회: 단순 GET 요청

### 3.2 방법 2: Selenium

**장점:**
- JavaScript 완전 지원
- 실제 브라우저와 동일한 동작

**단점:**
- 느린 실행 속도
- 높은 리소스 사용량
- 브라우저 드라이버 의존성
- 안정성 이슈 (타임아웃, 요소 찾기 실패 등)

### 3.3 방법 3: Playwright/Puppeteer

**장점:**
- Selenium보다 안정적
- 현대적인 API

**단점:**
- 여전히 브라우저 기반 (느림)
- 추가 의존성

### 3.4 결론: HTTP 직접 요청 + Ajax 분석

Admin 사이트 분석 결과, 대부분의 작업이 **단순 폼 제출**로 처리됩니다.
주문서 작성 시 품목 선택의 Ajax 호출만 별도로 분석하여 처리하면 됩니다.

**Selenium이 필요하지 않은 이유:**
1. 로그인 폼이 JavaScript 암호화 없이 평문 전송
2. 고객 등록이 단순 POST 제출
3. 주문서 작성의 품목 드롭다운도 Ajax URL 직접 호출 가능
4. 모든 페이지가 서버 렌더링 (SSR) 방식

---

## 4. 데이터베이스 설계

### 4.1 주문 DB (새로 생성)

```python
# models_order.py

class Customer(Base):
    """고객 정보"""
    __tablename__ = 'customers'

    id = Column(Integer, primary_key=True)
    depositor_name = Column(String(50))      # 입금자 이름
    recipient_name = Column(String(50))      # 받으실 분 이름
    phone = Column(String(20))               # 휴대폰 번호
    zipcode = Column(String(10))             # 우편번호
    address = Column(String(200))            # 기본주소
    address_detail = Column(String(100))     # 상세주소
    cash_receipt_no = Column(String(20))     # 현금영수증 번호
    memo = Column(Text)                      # 기타 요청사항
    admin_customer_idx = Column(Integer)     # Admin 사이트 고객 ID
    created_at = Column(DateTime)

class Order(Base):
    """주문 정보"""
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'))
    product_article_idx = Column(Integer)    # 크롤링 DB의 상품 ID
    product_name = Column(String(200))       # 상품명
    category_code = Column(String(10))       # 카테고리 코드
    option_name = Column(String(200))        # 선택한 옵션명
    price = Column(Integer)                  # 상품 가격
    delivery_fee = Column(Integer)           # 택배비
    quantity = Column(Integer, default=1)    # 수량
    total_amount = Column(Integer)           # 총액 (가격 + 택배비)

    # 주문 상태
    status = Column(String(20), default='pending')
    # pending: 주문접수, customer_registered: 고객등록완료,
    # order_registered: 주문등록완료, verified: 검증완료

    # Admin 연동 정보
    admin_order_idx = Column(Integer)        # Admin 사이트 주문 ID
    admin_registered_at = Column(DateTime)   # Admin 등록 시각
    admin_verified_at = Column(DateTime)     # Admin 검증 시각

    # Admin에서 가져온 정보
    admin_order_status = Column(String(50))  # 주문상태
    admin_payment_status = Column(String(50)) # 입금상태
    admin_settlement = Column(Integer)        # 정산금액

    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    customer = relationship('Customer', backref='orders')
```

### 4.2 크롤링 DB와 주문 DB 연동
- 상품 선택 시 크롤링 DB의 `article_idx`를 참조
- 카테고리 매핑 테이블로 Admin 사이트 카테고리 ID와 연결

---

## 5. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                     Young Fresh Mall                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Frontend   │    │   Backend    │    │   Database   │      │
│  │   (Flask)    │───→│   (Flask)    │───→│   (SQLite)   │      │
│  │              │    │              │    │              │      │
│  │  - 상품목록   │    │  - 주문접수   │    │  - products  │      │
│  │  - 상품상세   │    │  - 고객등록   │    │  - orders    │      │
│  │  - 주문폼     │    │  - API       │    │  - customers │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                              │                                   │
│                              ▼                                   │
│                    ┌──────────────────┐                         │
│                    │  Admin Connector │                         │
│                    │                  │                         │
│                    │  - 로그인 관리    │                         │
│                    │  - 고객 등록      │                         │
│                    │  - 주문 등록      │                         │
│                    │  - 주문 조회/검증 │                         │
│                    └────────┬─────────┘                         │
│                             │                                    │
└─────────────────────────────┼────────────────────────────────────┘
                              │ HTTP Requests
                              ▼
                    ┌──────────────────┐
                    │ admin.open79.co.kr│
                    │                  │
                    │  (External Site) │
                    └──────────────────┘
```

---

## 6. 구현 계획

### Step 1: 주문서 받기 (프론트엔드)

**구현 내용:**
1. 상품 상세 페이지에 "구매하기" 버튼 추가
2. 주문 폼 모달 구현:
   - 입금자 이름
   - 받으실 분 이름
   - 휴대폰 번호 (###-####-#### 형식, 입력 시 자동 포맷팅)
   - 주소 (Daum Postcode Service 연동)
   - 현금영수증 번호 (###-####-#### 형식)
   - 기타 요청사항 (textarea)
3. 폼 검증 (프론트엔드 + 백엔드)
4. 주문 DB에 저장

**파일:**
- `app.py`: 주문 API 엔드포인트 추가
- `models_order.py`: 주문/고객 모델
- `templates/order_form.html`: 주문 폼 (inline template)

### Step 2: Admin 고객 등록 자동화

**구현 내용:**
1. `AdminConnector` 클래스 생성
2. 로그인 세션 관리 (쿠키 저장/재사용)
3. 고객 등록 API 호출
4. 등록된 고객 ID (`c_goods_idx`) 추출 및 저장

**파일:**
- `admin_connector.py`

**코드 예시:**
```python
class AdminConnector:
    BASE_URL = "http://admin.open79.co.kr"

    def __init__(self, user_id, password):
        self.session = requests.Session()
        self.user_id = user_id
        self.password = password
        self.logged_in = False

    def login(self):
        """Admin 사이트 로그인"""
        resp = self.session.post(
            f"{self.BASE_URL}/m/include/asp/login_ok.asp",
            data={"m_id": self.user_id, "m_passwd": self.password}
        )
        self.logged_in = "location.replace" in resp.text
        return self.logged_in

    def register_customer(self, customer_data):
        """고객 등록"""
        if not self.logged_in:
            self.login()

        resp = self.session.post(
            f"{self.BASE_URL}/m/customer/p_custom_regist_ok.asp",
            data={
                "c_name": customer_data["name"],
                "c_tel2": customer_data["phone"],
                "c_zipcode": customer_data["zipcode"],
                "c_address": customer_data["address"],
                "c_address_etc": customer_data["address_detail"],
                "c_tax_no": customer_data["cash_receipt_no"],
                "c_bigo": customer_data["memo"]
            }
        )
        # 등록된 고객 ID 추출 로직
        return self._extract_customer_idx(resp)
```

### Step 3: Admin 주문 등록 자동화

**구현 내용:**
1. 품목 카테고리 매핑
2. Ajax 호출로 상품 목록 가져오기
3. 주문서 등록

**추가 분석 필요:**
- 품목 선택 Ajax URL 확인
- 상품별 article_idx 매핑

### Step 4: 주문 검증 및 DB 업데이트

**구현 내용:**
1. 주문 목록 페이지 크롤링
2. 고객명/상품명으로 주문 검색
3. 주문 상세 페이지에서 정보 추출
4. 주문 DB 업데이트

---

## 7. 보안 고려사항

### 7.1 자격 증명 관리
```python
# config.py 또는 환경 변수
ADMIN_CREDENTIALS = {
    "id": os.environ.get("ADMIN_ID", "REDACTED_ID"),
    "password": os.environ.get("ADMIN_PW", "REDACTED_PW")
}
```

### 7.2 입력 검증
- 휴대폰 번호 형식 검증
- 현금영수증 번호 형식 검증
- XSS/SQL Injection 방지

### 7.3 에러 처리
- Admin 사이트 접속 실패 시 재시도 로직
- 세션 만료 시 자동 재로그인
- 모든 작업 로깅

---

## 8. 향후 확장 계획

1. **관리자 대시보드**: 주문 현황 모니터링
2. **알림 시스템**: 새 주문 시 SMS/이메일 알림
3. **배치 처리**: 여러 주문 일괄 등록
4. **배송 추적 연동**: 운송장 번호 자동 업데이트

---

## 9. 개발 일정 (예상)

| 단계 | 내용 |
|------|------|
| 1 | DB 모델 생성 및 주문 폼 UI |
| 2 | 주문 접수 API 구현 |
| 3 | AdminConnector 기본 구현 (로그인, 고객등록) |
| 4 | 주문 등록 자동화 |
| 5 | 주문 검증 및 동기화 |
| 6 | 테스트 및 버그 수정 |

---

## 10. 결론

**HTTP 직접 요청 방식**을 사용하여 Admin 사이트 연동을 구현하는 것이 최선의 방법입니다.

**이유:**
1. Admin 사이트가 구식 ASP 기반으로 단순한 폼 제출 방식 사용
2. JavaScript 암호화나 복잡한 클라이언트 로직 없음
3. Selenium 대비 10배 이상 빠른 실행 속도
4. 서버 리소스 최소화
5. 안정적인 운영 가능

다음 단계로 각 Step을 순차적으로 구현하면 됩니다.
