# Fruits_final 프로젝트 문서

## 프로젝트 개요

**목적**: os79.co.kr 사이트에서 과일/농산물 상품 데이터를 크롤링하고, Young Fresh Mall 쇼핑몰을 운영하며, 네이버 밴드 자동 홍보 포스팅 및 admin.open79.co.kr 주문 자동 등록까지 처리하는 통합 시스템

**핵심 기능**:
1. **크롤러** - os79.co.kr에서 상품 데이터 수집 + Admin 드롭다운 동기화
2. **쇼핑몰** - Young Fresh Mall 프론트엔드 (주문/결제)
3. **밴드 포스팅** - 네이버 밴드 자동 게시물 작성 (Selenium)
4. **주문 자동화** - Admin 사이트에 고객등록 + 주문등록 자동화
5. **SMS 알림** - Aligo API 통한 주문/입금 확인 문자 발송

**기술 스택**: Python 3.11, Flask, SQLAlchemy, BeautifulSoup, Selenium, SQLite

---

## 시스템 아키텍처 (Mermaid Diagrams)

### 1. 전체 시스템 구조

```mermaid
graph TB
    subgraph "External Sites"
        OS79[os79.co.kr<br/>상품 소스 사이트]
        ADMIN[admin.open79.co.kr<br/>관리자 사이트]
        BAND[band.us<br/>네이버 밴드]
        ALIGO[Aligo SMS API]
    end

    subgraph "Crawling & Sync"
        CRAWLER[OS79Crawler<br/>crawler.py]
        MAIN[CLI<br/>main.py]
    end

    subgraph "Database"
        DB[(SQLite DB<br/>products.db)]
        IMAGES[/Images Folder<br/>data/images/]
    end

    subgraph "Shopping Mall"
        MALL[Young Fresh Mall<br/>app.py :5000]
        ORDER[OrderProcessor<br/>order_processor.py]
        SMS[SMS Module<br/>sms.py]
    end

    subgraph "Band Posting"
        POSTER[BandPoster<br/>band_poster.py<br/>Selenium + Chrome]
    end

    subgraph "Admin Test UI"
        ADMINTEST[Admin Visual Test<br/>admin_visual_test.py :5002]
    end

    OS79 -->|HTTP GET<br/>상품 크롤링| CRAWLER
    ADMIN -->|js_article.asp<br/>매핑 데이터| CRAWLER
    CRAWLER -->|파싱 & 저장| DB
    CRAWLER -->|이미지 다운로드| IMAGES
    MAIN -->|실행| CRAWLER
    MAIN -->|실행| POSTER

    DB -->|상품 데이터| MALL
    DB -->|상품 데이터| POSTER

    MALL -->|주문 생성| ORDER
    ORDER -->|자동 등록<br/>EUC-KR| ADMIN
    MALL -->|주문 SMS| SMS
    SMS -->|API| ALIGO

    POSTER -->|Selenium<br/>자동 글쓰기| BAND
    POSTER -->|게시물 URL 저장| DB

    ADMINTEST -->|HTTP POST<br/>EUC-KR| ADMIN

    style OS79 fill:#e1f5ff
    style ADMIN fill:#ffe1e1
    style BAND fill:#e8f5e9
    style DB fill:#f0f0f0
    style CRAWLER fill:#d4edda
    style POSTER fill:#fff3cd
    style MALL fill:#e3f2fd
    style ORDER fill:#fce4ec
```

### 2. 크롤링 + 상품 비활성화 플로우

```mermaid
flowchart TD
    START([python main.py all]) --> INIT[DB 초기화 + 카테고리 초기화]
    INIT --> RECORD_TIME[크롤링 시작 시간 기록<br/>crawl_started_at]

    RECORD_TIME --> LOOP1{각 카테고리<br/>A~F 반복}

    LOOP1 -->|카테고리 코드| LIST[상품 목록 조회<br/>goods_list.asp?s_article_gubun=X]
    LIST --> PARSE[HTML 파싱<br/>article_idx 추출]

    PARSE --> LOOP2{각 상품 반복}
    LOOP2 --> DETAIL[상품 상세 조회<br/>goods_view.asp?article_idx=N]
    DETAIL --> EXTRACT[데이터 추출<br/>이름/가격/재고/설명/이미지/옵션]

    EXTRACT --> CHECK{DB에<br/>기존 상품?}
    CHECK -->|YES| UPDATE[업데이트<br/>is_active=True<br/>last_seen_at=now]
    CHECK -->|NO| INSERT[새 상품 생성<br/>is_active=True<br/>last_seen_at=now]

    UPDATE --> NEXT[다음 상품]
    INSERT --> NEXT
    NEXT --> LOOP2

    LOOP2 -->|카테고리 완료| LOOP1

    LOOP1 -->|전체 완료| DEACT1[비활성화 1단계<br/>os79에서 미발견 상품<br/>deactivate_missing_products]

    DEACT1 --> ADMIN_SYNC[Admin 동기화<br/>fetch_admin_mapping]
    ADMIN_SYNC --> DEACT2[비활성화 2단계<br/>Admin 드롭다운에 없는 상품<br/>sync_admin_data]

    DEACT2 --> END([크롤링 완료<br/>비활성 상품 = 쇼핑몰 자동 숨김])

    style START fill:#d4edda
    style END fill:#d4edda
    style DEACT1 fill:#f8d7da
    style DEACT2 fill:#f8d7da
    style UPDATE fill:#cfe2ff
    style INSERT fill:#e8f5e9
```

### 3. 상품 비활성화 기준 (이중 검증)

```mermaid
graph TB
    subgraph "비활성화 조건 (OR)"
        COND1[조건 1: os79 웹페이지에<br/>상품이 없음<br/>deactivate_missing_products]
        COND2[조건 2: Admin 드롭다운에<br/>상품이 없음<br/>sync_admin_data]
    end

    COND1 --> DEACT[is_active = False]
    COND2 --> DEACT

    DEACT --> EFFECT1[쇼핑몰 메인 목록에서 숨김]
    DEACT --> EFFECT2[상품 상세 페이지 404]
    DEACT --> EFFECT3[주문 페이지 접근 차단]

    EFFECT1 --> SAFE[CS 이슈 방지<br/>판매 종료 상품 주문 불가]
    EFFECT2 --> SAFE
    EFFECT3 --> SAFE

    style DEACT fill:#f8d7da
    style SAFE fill:#d4edda
```

### 4. 밴드 포스팅 플로우

```mermaid
sequenceDiagram
    participant CLI as main.py CLI
    participant BP as BandPoster<br/>(Selenium)
    participant DB as SQLite DB
    participant CHROME as Chrome<br/>(프로필 세션)
    participant BAND as band.us

    Note over CLI: 첫 실행 시 로그인 필요
    CLI->>BP: band-login
    BP->>CHROME: 브라우저 열기<br/>(Chrome 프로필)
    CHROME->>BAND: band.us 접속
    Note over CHROME: 사용자가 수동 로그인<br/>(세션 Chrome 프로필에 저장)

    Note over CLI: 게시물 작성
    CLI->>BP: band-post <article_idx>
    BP->>DB: 상품 정보 조회
    DB-->>BP: Product 데이터
    BP->>BP: 홍보 텍스트 생성<br/>(format_product_content)
    BP->>BP: 이미지 준비<br/>(detail만, main 제외)

    BP->>CHROME: 밴드 페이지 이동
    CHROME->>BAND: GET band_url

    BP->>CHROME: 글쓰기 버튼 클릭
    BP->>CHROME: CKEditor setData<br/>(<p> 태그로 줄바꿈)
    BP->>CHROME: 이미지 첨부<br/>(input[type=file])
    BP->>CHROME: 게시 버튼 클릭

    CHROME->>BAND: 게시물 등록
    BAND-->>CHROME: 게시 완료 (URL)
    CHROME-->>BP: current_url 캡처
    BP-->>CLI: post_url 반환
```

### 5. Incremental 밴드 포스팅 워크플로우

```mermaid
flowchart TD
    subgraph "Phase 1: 크롤링"
        CRAWL[python main.py all --no-images<br/>전체 상품 크롤링]
        CRAWL --> DB_UPDATE[DB 업데이트<br/>신규 상품 추가<br/>기존 상품 갱신<br/>사라진 상품 비활성화]
    end

    subgraph "Phase 2: 신규 상품 확인"
        CHECK_NEW[python main.py band-new<br/>미게시 상품 조회]
        CHECK_NEW --> FILTER[필터 조건:<br/>is_active = True<br/>band_posted_at = NULL]
        FILTER --> LIST[미게시 상품 목록 출력]
    end

    subgraph "Phase 3: 테스트 밴드 미리보기"
        PREVIEW[python main.py band-preview article_idx<br/>or band-preview-all]
        PREVIEW --> TEST_BAND[테스트 밴드에 게시]
        TEST_BAND --> SAVE_PREVIEW[DB 저장:<br/>band_preview_posted_at<br/>band_preview_url]
    end

    subgraph "Phase 4: 승인 → 본 밴드 게시"
        CONFIRM[python main.py band-confirm article_idx]
        CONFIRM --> PROD_BAND[본 밴드에 게시<br/>BAND_PRODUCTION_URL]
        PROD_BAND --> SAVE_PROD[DB 저장:<br/>band_posted_at<br/>band_post_url]
    end

    DB_UPDATE --> CHECK_NEW
    LIST --> PREVIEW
    SAVE_PREVIEW -->|텔레그램으로<br/>승인 요청 예정| CONFIRM

    style CRAWL fill:#d4edda
    style TEST_BAND fill:#fff3cd
    style PROD_BAND fill:#e3f2fd
    style SAVE_PROD fill:#d4edda
```

### 6. 주문 처리 플로우

```mermaid
sequenceDiagram
    participant CUST as 고객
    participant MALL as Young Fresh Mall<br/>(app.py)
    participant DB as Database
    participant PROC as AdminOrderProcessor<br/>(order_processor.py)
    participant ADMIN as admin.open79.co.kr
    participant SMS as Aligo SMS

    CUST->>MALL: 상품 선택 & 주문 제출
    MALL->>MALL: is_active 검증<br/>(비활성 상품 차단)
    MALL->>DB: 주문 생성<br/>(Order + OrderItem)
    DB-->>MALL: 주문번호 (YF-YYYYMMDD-NNN)

    MALL->>SMS: 주문 접수 SMS 발송
    SMS-->>CUST: 주문 접수 안내 문자

    MALL->>PROC: process_order(order)

    PROC->>ADMIN: 1. 로그인<br/>POST /login_ok.asp
    ADMIN-->>PROC: Session Cookie

    PROC->>ADMIN: 2. 고객 등록<br/>POST /p_custom_regist_ok.asp
    ADMIN-->>PROC: customer_idx

    PROC->>ADMIN: 3. js_article.asp 조회<br/>(sell_d, sell_s, stock 등)
    ADMIN-->>PROC: 상품별 Admin 데이터

    PROC->>ADMIN: 4. 주문 등록<br/>POST /p_order_regist_ok.asp<br/>(수량 N이면 N회 반복)
    ADMIN-->>PROC: 등록 완료

    PROC->>DB: 상태 업데이트<br/>status=completed<br/>admin_synced_at=now

    Note over PROC: 실패 시 status=failed<br/>error_message 기록
```

### 7. 데이터베이스 스키마

```mermaid
erDiagram
    Category ||--o{ Product : has
    Product ||--o{ OrderItem : "ordered as"
    Order ||--o{ OrderItem : contains

    Category {
        int id PK
        string code UK "A, B, C, D, E, F"
        string name "과일, 고구마 등"
        datetime created_at
    }

    Product {
        int id PK
        int article_idx UK "os79 상품 ID"
        string name "상품명"
        int price "가격"
        int original_price "할인 전 가격"
        text description "상세 설명 (줄바꿈 보존)"
        string origin "원산지"
        int stock "재고"
        int delivery_fee "배송비"
        boolean is_available "판매 가능 여부"
        string main_image_url "메인 이미지 URL"
        string main_image_local "로컬 이미지 경로"
        text detail_images "JSON 배열 (상세 이미지 URL)"
        text detail_content "JSON 배열 (텍스트+이미지)"
        text options "JSON 배열 (옵션 선택지)"
        int category_id FK
        string source_url "os79 원본 URL"
        string admin_category_idx "Admin 카테고리 코드"
        int admin_price "Admin 판매가"
        int admin_stock "Admin 재고"
        int admin_delivery_fee "Admin 배송비"
        datetime admin_synced_at "Admin 동기화 시간"
        boolean is_active "활성 상태"
        datetime last_seen_at "마지막 크롤링 발견"
        datetime band_posted_at "본 밴드 게시 시간"
        string band_post_url "본 밴드 게시물 URL"
        datetime band_preview_posted_at "테스트 밴드 미리보기"
        string band_preview_url "테스트 밴드 URL"
        datetime crawled_at
        datetime updated_at
    }

    Order {
        int id PK
        string order_number UK "YF-YYYYMMDD-NNN"
        string customer_name "받으실 분"
        string customer_phone "휴대폰"
        string zipcode "우편번호"
        string address "기본주소"
        string address_detail "상세주소"
        string depositor_name "입금자명"
        string cash_receipt_no "현금영수증"
        int total_amount "총 결제금액"
        text memo "배송 메모"
        string status "pending/processing/completed/failed"
        text error_message "실패 시 에러"
        string admin_customer_idx "Admin 고객 ID"
        datetime admin_synced_at "Admin 등록 시간"
        datetime created_at
        datetime updated_at
    }

    OrderItem {
        int id PK
        int order_id FK
        int product_id FK
        int article_idx "상품 ID"
        string product_name "상품명"
        int quantity "수량"
        int price "단가"
        int delivery_fee "배송비"
        string admin_category_idx "Admin 카테고리"
    }

    CrawlLog {
        int id PK
        string category_code "A~F"
        string status "running/completed/failed"
        int total_products
        int success_count
        int fail_count
        datetime started_at
        datetime finished_at
        text error_message
    }

    ProductImage {
        int id PK
        int product_id FK
        string image_url "원본 URL"
        string local_path "로컬 경로"
        string image_type "main/detail"
        int order "이미지 순서"
    }
```

### 8. 카테고리 매핑 (자동 동기화)

```mermaid
graph LR
    subgraph "우리 시스템 (DB)"
        A[A: 과일]
        B[B: 고구마/야채]
        C[C: 수산]
        D[D: 축산]
        E[E: 쌀/잡곡]
        F[F: 건어물/기타]
    end

    subgraph "Admin 시스템 (자동 매핑)"
        A5[5: 고구마/야채]
        A6[6: 감/배/포도]
        A7[7]
        A8[8]
        A10[10]
        A13[13: 참외/귤/포도/유자]
        A14[14]
        A23[23]
    end

    subgraph "js_article.asp (자동 파싱)"
        JS[전체 상품 데이터<br/>article_idx → cate_idx 매핑<br/>price, stock, delivery]
    end

    A -.->|1:N 매핑| A6
    A -.->|1:N 매핑| A13
    A -.->|1:N 매핑| A14
    A -.->|1:N 매핑| A23
    A -.->|1:N 매핑| A7
    A -.->|1:N 매핑| A8
    A -.->|1:N 매핑| A10
    B -.->|매핑| A5

    JS -->|자동 파싱<br/>crawl_all 시 실행| A5
    JS -->|자동 파싱| A6
    JS -->|자동 파싱| A13

    style A fill:#d4edda
    style B fill:#d4edda
    style JS fill:#fff3cd
```

---

## 파일 구조

```
Fruits_final/
├── config.py              # 설정 (URL, 카테고리, 밴드 URL, SMS 키)
├── models.py              # SQLAlchemy 모델 (Category, Product, Order, OrderItem, CrawlLog)
├── crawler.py             # 크롤러 + Admin 동기화 + 상품 비활성화
├── main.py                # CLI 진입점 (크롤링, 밴드, 통계)
├── app.py                 # Young Fresh Mall 쇼핑몰 (포트 5000)
├── band_poster.py         # 네이버 밴드 자동 포스팅 (Selenium)
├── order_processor.py     # Admin 주문 자동 등록
├── sms.py                 # Aligo SMS 발송 모듈
├── viewer.py              # 크롤링 데이터 뷰어 (포트 5000)
├── admin_visual_test.py   # Admin 시각적 테스트 (포트 5002)
├── admin_test.py          # Admin HTTP 테스트 (CLI)
├── admin_test_web.py      # Admin 웹 테스트 (초기)
├── DIAGRAMS_VIEWER.html   # Mermaid 차트 브라우저 뷰어
└── data/
    ├── products.db        # SQLite 데이터베이스
    ├── images/            # 상품 이미지
    └── chrome_profile/    # Chrome 프로필 (밴드 로그인 세션)
```

---

## 1. 설정 (config.py)

### 크롤링 대상
```python
BASE_URL = "https://os79.co.kr"
GOODS_LIST_URL = f"{BASE_URL}/board_order/goods_list.asp"
GOODS_VIEW_URL = f"{BASE_URL}/board_order/goods_view.asp"
```

### 카테고리 코드
```python
CATEGORIES = {
    "A": "과일",
    "B": "고구마, 야채 BEST",
    "C": "수산",
    "D": "축산",
    "E": "쌀, 잡곡",
    "F": "건어물, 기타",
}
```

### 밴드 설정
```python
BAND_PREVIEW_URL = "https://band.us/page/101768540"  # 테스트/미리보기용 밴드
BAND_PRODUCTION_URL = ""                               # 본 밴드 (실제 운영용, 나중에 설정)
SHOPPING_MALL_URL = "http://localhost:5000"             # 쇼핑몰 링크 (게시물에 포함)
```

### SMS 설정
```python
ALIGO_API_KEY = ""       # Aligo API Key
ALIGO_USER_ID = ""       # Aligo 사용자 ID
ALIGO_SENDER = ""        # 발신 번호 (사전 등록 필요)
```

### 기타
- `REQUEST_DELAY`: 1.0초 (요청 간 대기)
- `REQUEST_TIMEOUT`: 30초
- `MAX_RETRIES`: 3회

---

## 2. 크롤러 (crawler.py)

### OS79Crawler 클래스

#### `crawl_all(download_images=True)`
전체 크롤링 + 비활성화 + Admin 동기화를 한 번에 실행:

1. DB 초기화 + 카테고리 초기화
2. `crawl_started_at` 기록
3. 각 카테고리(A~F) 순회 → `crawl_category()` 호출
4. **비활성화 1단계**: `deactivate_missing_products(crawl_started_at)` — os79 페이지에서 사라진 상품
5. **비활성화 2단계**: `fetch_admin_mapping()` → `sync_admin_data()` — Admin 드롭다운에서 사라진 상품

#### `get_product_detail(article_idx)`
상품 상세 정보 크롤링:
- 상품명: `#txt_article_name`
- 가격: `#txt_article_price`
- 메인 이미지: `.viewImg` background-image
- 재고: `#article_stock`
- 배송비: `#txt_article_delivery`
- 설명: `.vw_content` → **HTML→텍스트 변환 (줄바꿈 보존)**
- 옵션: `#goods_idx` select

#### 설명 텍스트 추출 (줄바꿈 보존)
```python
# HTML → 텍스트 변환 (원본 줄바꿈/공백 보존)
desc_html = str(detail_section)
desc_text = re.sub(r'<img[^>]*/?>', '', desc_html)        # 이미지 제거
desc_text = re.sub(r'<br\s*/?>', '\n', desc_text)         # <br> → 줄바꿈
desc_text = re.sub(r'</(p|div|li|h[1-6])>', '\n', desc_text)  # 블록 태그 경계
desc_text = re.sub(r'<[^>]+>', '', desc_text)             # 나머지 태그 제거
desc_text = html.unescape(desc_text)                      # HTML 엔티티 디코드
desc_text = '\n'.join(line.strip() for line in desc_text.split('\n'))
desc_text = re.sub(r'\n{4,}', '\n\n\n', desc_text)       # 과도한 빈 줄 정리
```

#### `save_product(product_data, category)`
**누적+업데이트 구조**:
- `article_idx` 기준으로 기존 상품 확인
- 있으면 → 업데이트 (`is_active=True`, `last_seen_at=now`)
- 없으면 → 새로 생성
- 삭제는 하지 않음 (비활성화만)

#### `deactivate_missing_products(crawl_started_at)`
os79 웹페이지에서 사라진 상품 비활성화:
- `last_seen_at < crawl_started_at` 인 활성 상품 → `is_active = False`

#### `fetch_admin_mapping()` → `sync_admin_data(mappings)`
Admin 드롭다운 기반 동기화:
1. Admin 로그인 → `js_article.asp` 파싱 (EUC-KR)
2. JavaScript 배열에서 `j_article_idx`, `j_cate_idx`, `j_article_price`, `j_article_stock`, `j_article_delivery` 추출
3. DB 상품에 `admin_category_idx`, `admin_price`, `admin_stock`, `admin_delivery_fee` 업데이트
4. **DB에 활성인데 Admin에 없는 상품 → `is_active = False`**

---

## 3. 밴드 포스팅 (band_poster.py)

### BandPoster 클래스

**Selenium 기반 자동 글쓰기**:
- Chrome 프로필 디렉토리(`data/chrome_profile/`)로 로그인 세션 유지
- 한 번 `band-login`으로 수동 로그인하면 이후 자동

#### 게시물 작성 과정
1. Chrome 프로필로 브라우저 초기화
2. 밴드 페이지 이동
3. `button._btnWritePost` 클릭 → 글쓰기 레이어 열기
4. **CKEditor `setData()` API**로 텍스트 입력 (각 줄을 `<p>` 태그로 감싸서 줄바꿈 처리)
5. `input[name='attachment'][accept='image/*']`에 이미지 파일 경로 전달
6. "첨부하기" 버튼 클릭
7. `button._btnSubmitPost` 클릭 → 게시
8. **`driver.current_url` 캡처 → 게시물 URL 반환**

#### 이미지 처리
- **main 이미지 제외** (detail 첫 장과 동일하므로 중복 방지)
- detail 이미지만 업로드
- 로컬에 없으면 URL에서 자동 다운로드

#### 카카오 오픈채팅 URL 교체
게시물 작성 시 상품 설명의 카카오 URL 자동 교체:
- `https://open.kakao.com/o/gF7nJ96h` → `https://open.kakao.com/o/sNgjJoBb`

### Incremental 포스팅 함수

#### `get_unposted_products(category_code=None)`
미게시 활성 상품 조회:
```python
Product.is_active == True AND Product.band_posted_at == None
```

#### `band_show_new(category_code=None)`
미게시 상품 리스트 출력 (카테고리 필터 가능)

#### `band_post_preview(article_idx)`
테스트 밴드(`BAND_PREVIEW_URL`)에 미리보기 게시:
- 게시 성공 시 `band_preview_posted_at`, `band_preview_url` DB 저장

#### `band_post_preview_all(category_code=None)`
미게시 전체 상품을 테스트 밴드에 일괄 미리보기 게시

#### `band_post_confirm(article_idx)`
승인된 상품을 본 밴드(`BAND_PRODUCTION_URL`)에 게시:
- 게시 성공 시 `band_posted_at`, `band_post_url` DB 저장

---

## 4. 쇼핑몰 (app.py)

### Young Fresh Mall - 포트 5000

**주요 라우트**:

| 경로 | 설명 |
|------|------|
| `/` | 메인 페이지 (전체 상품) |
| `/category/<code>` | 카테고리별 상품 |
| `/search?q=` | 상품 검색 |
| `/product/<article_idx>` | 상품 상세 |
| `/order/<article_idx>` | 주문 페이지 |
| `/order/submit` | 주문 제출 (POST) |

### is_active 필터 (핵심 안전장치)

모든 상품 조회에 `is_active` 필터 적용:

- **메인 목록**: `Product.is_active == True` 필터
- **검색**: `Product.is_active == True` 필터
- **상품 상세**: `not product.is_active` → 404
- **주문 페이지**: `not product.is_active` → "판매 종료된 상품입니다." 404

> **중요**: 비활성 상품은 쇼핑몰 어디에서도 접근 불가. 판매 종료/재고 없는 상품 주문 차단.

---

## 5. 주문 자동화 (order_processor.py)

### AdminOrderProcessor 클래스

Young Fresh Mall 주문 → Admin 사이트 자동 등록:

1. **로그인**: `POST /m/include/asp/login_ok.asp` (환경변수 ADMIN_ID/ADMIN_PW 사용)
2. **고객 등록**: `POST /m/customer/p_custom_regist_ok.asp` → `customer_idx` 확보
3. **상품 데이터 조회**: `js_article.asp`에서 `sell_d`, `sell_s`, `stock` 등 가져오기
4. **주문 등록**: `POST /m/customer/p_order_regist_ok.asp`
   - 수량 N이면 동일 고객에게 N회 반복 등록 (Admin 건별 등록 방식)

### 폼 데이터 인코딩
- Admin 사이트는 **EUC-KR** 사용
- `[]` 를 인코딩하지 않는 raw body 방식 (`urllib.parse.quote`로 직접 인코딩)

### 주문번호 체계
`YF-YYYYMMDD-NNN` (예: YF-20260303-001)

### 주문 상태
`pending` → `processing` → `completed` (또는 `failed`)

---

## 6. SMS 알림 (sms.py)

### Aligo SMS

- **주문 접수 SMS**: 주문 생성 시 고객에게 발송
- **입금 확인 SMS**: 입금 확인 시 고객에게 발송
- 메시지 길이에 따라 SMS/LMS 자동 결정 (90바이트 기준)
- API 키 미설정 시 발송 건너뜀 (에러 없음)

---

## 7. Admin 테스트 UI (admin_visual_test.py)

포트 5002에서 Admin 사이트 연동 테스트:

```
Step 1: 로그인
Step 2: 고객 등록 → 결과 확인 (iframe)
Step 3: 주문서 작성 → JavaScript로 품목 자동 선택
Step 4: 주문 목록 확인 (iframe)
```

---

## 8. CLI 명령어 (main.py)

### 크롤링
```bash
# 전체 크롤링 (이미지 제외)
python main.py all --no-images

# 특정 카테고리만
python main.py category A

# 단일 상품 테스트
python main.py single 42563

# DB 통계
python main.py stats
```

### 밴드 포스팅
```bash
# 밴드 로그인 (최초 1회)
python main.py band-login

# 단일 상품 포스팅 (테스트 밴드)
python main.py band-post 40474

# 카테고리 전체 포스팅
python main.py band-post-category A
```

### Incremental 밴드 포스팅
```bash
# 미게시 상품 리스트
python main.py band-new
python main.py band-new --category A

# 테스트 밴드 미리보기
python main.py band-preview 40474
python main.py band-preview-all
python main.py band-preview-all --category A

# 승인 → 본 밴드 게시
python main.py band-confirm 40474
```

### 참고
```bash
# venv activate 대신 직접 경로 사용 (permission 문제)
/Users/ivan/PycharmProjects/Fruits_final/venv/bin/python main.py all --no-images
```

---

## 9. 트러블슈팅

### EUC-KR 인코딩
- **원인**: Admin 사이트가 EUC-KR 사용
- **해결**: `post_form()`에서 데이터를 EUC-KR로 인코딩, `[]`는 raw body로 처리

### 설명 텍스트 줄바꿈 손실
- **원인**: `get_text(strip=True)`가 모든 공백/줄바꿈 제거
- **해결**: Regex 기반 HTML→텍스트 변환 (`<br>` → `\n`, 블록태그 경계 → `\n`)

### 밴드 이미지 중복
- **원인**: main 이미지 = detail 첫 장 (동일 파일)
- **해결**: `_get_product_images()`에서 main 제외, detail만 업로드

### DetachedInstanceError
- **원인**: SQLAlchemy 세션 닫은 후 lazy-loaded 관계 접근
- **해결**: `joinedload(Product.category)` + 세션 닫기 전 미리 로드

### venv activate Permission Denied
- **해결**: `venv/bin/python` 직접 경로 사용

---

## 10. 로그인 정보

### Admin 사이트
- URL: http://admin.open79.co.kr
- ID: 환경변수 ADMIN_ID
- PW: 환경변수 ADMIN_PW

### 네이버 밴드
- Chrome 프로필(`data/chrome_profile/`)에 세션 저장
- 최초 `band-login`으로 수동 로그인 필요

---

## 11. 향후 계획

### 아키텍처 (OpenClaw 통합)
- **OpenClaw**: 메인 컨트롤러 (텔레그램 승인, 크롤링 스케줄링)
- **Cloudflare Tunnel**: 쇼핑몰 퍼블릭 접근용
- **Tailscale**: OpenClaw ↔ 로컬 서버 비공개 통신용
- **Cron**: 주기적 크롤링 + 밴드 포스팅 자동화

```mermaid
graph TB
    subgraph "Public Internet"
        CUSTOMER[고객<br/>쇼핑몰 접속]
        CF[Cloudflare Tunnel<br/>도메인: youngfresh.kr]
    end

    subgraph "Tailscale Network (Private)"
        OPENCLAW[OpenClaw<br/>메인 컨트롤러]
        SERVER[로컬 서버<br/>Flask + Crawler + Band]
        TELEGRAM[텔레그램 봇<br/>승인/알림]
    end

    CUSTOMER -->|HTTPS| CF
    CF -->|Tunnel| SERVER

    OPENCLAW -->|Tailscale API| SERVER
    OPENCLAW <-->|알림/승인| TELEGRAM

    OPENCLAW -->|크롤링 명령| SERVER
    OPENCLAW -->|밴드 포스팅 명령| SERVER
    OPENCLAW -->|쇼핑몰 수정| SERVER

    style CF fill:#fff3cd
    style OPENCLAW fill:#e3f2fd
    style CUSTOMER fill:#d4edda
```

### 텔레그램 승인 플로우 (예정)
1. 크롤링 → 신규 상품 감지
2. 테스트 밴드에 미리보기 게시
3. 텔레그램으로 "이 상품 본 밴드에 올릴까요?" 승인 요청
4. 승인 시 `band-confirm` 실행
5. 거부 시 스킵

### 나머지 TODO
- `BAND_PRODUCTION_URL` 설정 (본 밴드 URL)
- Aligo SMS API 키 설정
- 168개 전체 상품 re-crawl (새 설명 포맷 적용)
- Cloudflare Tunnel + Tailscale 설정
- OpenClaw + 텔레그램 봇 연동

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2025-01-20 | 초기 크롤러 및 프론트엔드 구현 |
| 2025-01-21 | Admin 연동 테스트 구현 |
| 2025-01-26 | EUC-KR 인코딩 수정, 전체 크롤링 실행 (211개 상품) |
| 2026-03-02 | 최신 크롤링 (168개 활성 상품) |
| 2026-03-02 | Admin 동기화 (js_article.asp 자동 파싱) 구현 |
| 2026-03-02 | 상품 비활성화 로직 구현 (os79 페이지 + Admin 드롭다운 이중 검증) |
| 2026-03-02 | Young Fresh Mall 쇼핑몰 구현 (주문/결제 포함) |
| 2026-03-02 | Admin 주문 자동 등록 (order_processor.py) 구현 |
| 2026-03-02 | Aligo SMS 모듈 (sms.py) 구현 |
| 2026-03-02 | 네이버 밴드 자동 포스팅 (Selenium) 구현 |
| 2026-03-03 | 밴드 이미지 중복 수정 (main 제외, detail만 업로드) |
| 2026-03-03 | 설명 텍스트 줄바꿈 보존 개선 (regex 기반 HTML→텍스트) |
| 2026-03-03 | 카카오 오픈채팅 URL 교체 로직 추가 |
| 2026-03-03 | app.py is_active 필터 추가 (비활성 상품 주문 차단) |
| 2026-03-03 | 밴드 포스팅 추적 필드 4개 추가 (band_posted_at 등) |
| 2026-03-03 | Admin 드롭다운 비활성화 로직 추가 |
| 2026-03-03 | Incremental 밴드 포스팅 워크플로우 구현 (band-new/preview/confirm) |
