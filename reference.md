# Fruits_final 프로젝트 레퍼런스

## 프로젝트 개요
- os79.co.kr 크롤링 → SQLite DB → Young Fresh Mall + 밴드 자동 포스팅 + Admin 주문 자동화
- Python 3.11, Flask, SQLAlchemy, BeautifulSoup, Selenium

## 핵심 파일 경로
- `config.py` - URL, 카테고리(A~F), 밴드 URL, SMS 설정
- `models.py` - Category, Product, Order, OrderItem, CrawlLog, ProductImage
- `crawler.py` - OS79Crawler (크롤링 + Admin 동기화 + 상품 비활성화)
- `main.py` - CLI 진입점 (크롤링, 밴드, 통계)
- `app.py` - Young Fresh Mall (포트 5000, 주문/결제)
- `band_poster.py` - 네이버 밴드 자동 포스팅 (Selenium + Chrome 프로필)
- `order_processor.py` - Admin 주문 자동 등록
- `sms.py` - Aligo SMS 발송 모듈
- `payment_checker.py` - 입금 확인 자동화 (하이브리드 스케줄러)
- `viewer.py` - 크롤링 데이터 뷰어 (포트 5000)
- `admin_visual_test.py` - Admin 테스트 UI (포트 5002)
- `data/products.db` - SQLite DB
- `data/chrome_profile/` - Chrome 프로필 (밴드 로그인 세션)
- `PROJECT_DOCUMENTATION.md` - 전체 문서 (Mermaid 다이어그램 포함)

## 중요 기술 사항

### Admin 사이트 (admin.open79.co.kr)
- 인코딩: EUC-KR (폼 전송 시 반드시 인코딩 필요)
- 로그인: POST /m/include/asp/login_ok.asp (REDACTED_ID / REDACTED_PW)
- js_article.asp 경로: `/include/js/js_article.asp` (로그인 필요)
  - 변수명: j_article_idx, j_cate_idx, j_article_price, j_article_stock 등
  - 값 형식: `j_article_idx[0] = '42611';` (싱글쿼트, 배열 인덱스 기반)

### 상품 비활성화 (이중 검증)
- **조건 1**: os79 웹페이지에 상품 없음 → `deactivate_missing_products()`
- **조건 2**: Admin 드롭다운에 상품 없음 → `sync_admin_data()`
- 비활성 상품 → 쇼핑몰 메인/상세/주문 모두 차단 (is_active 필터)

### 밴드 포스팅
- Selenium + Chrome 프로필 기반 (수동 로그인 1회 → 세션 자동 유지)
- CKEditor `setData()` API로 줄바꿈 처리 (<p> 태그)
- main 이미지 제외 (detail과 중복), detail 이미지만 업로드
- 카카오 URL 교체: gF7nJ96h → sNgjJoBb
- Incremental: band-new → band-preview → band-confirm
- BAND_PREVIEW_URL = 테스트 밴드, BAND_PRODUCTION_URL = 본 밴드 (미설정)

### DB 동작
- **누적+업데이트 구조**: article_idx 기준, 있으면 업데이트, 없으면 생성
- 비활성화된 상품은 DB에 남지만 is_active=False
- Admin 동기화: crawl_all 실행 시 자동으로 js_article.asp 파싱 → DB 저장
- 밴드 추적: band_posted_at, band_post_url, band_preview_posted_at, band_preview_url

### 카테고리 매핑
- 우리 코드(A~F) ≠ Admin 코드(숫자)
- 1:N 관계 (예: 과일(A) → Admin 14, 23, 6, 13, 8, 7, 10)
- Product.admin_category_idx에 자동 저장됨

### 크롤링 명령어
```bash
/Users/ivan/Fruits_final/venv/bin/python main.py all --no-images
```
- venv activate에 permission 문제 있을 수 있음 → 직접 venv/bin/python 경로 사용

### IP 차단 방지 (crawler.py)
- UA 로테이션: 10개 User-Agent 중 매 요청마다 랜덤 선택
- 랜덤 딜레이: REQUEST_DELAY_MIN=1.0 ~ REQUEST_DELAY_MAX=3.0초
- 403/429 감지 시 지수 백오프 (10초~120초) + Referer 헤더

### 품절 안내 프로세스
- 크롤링 후 비활성화된 상품 → status='paid' 주문 조회 → 품절 SMS 발송
- Order.oos_notified_at으로 중복 발송 방지, status→'out_of_stock'
- 안전장치: 50% 이상 비활성화 대상 시 크롤링 오류로 판단 → 비활성화 스킵

### 입금 확인 자동화 (payment_checker.py)
- 하이브리드 스케줄러: 주문 후 10분 뒤 확인, 유휴 시 30분 주기
- Admin 주문 목록(p_order_list.asp)에서 "입금완료" 상태 확인
- 수동 확인도 Admin 입금 상태 검증 필수 (이중 안전장치)
- 상태 플로우: pending → processing → awaiting_payment → paid → out_of_stock

### 주의사항
- source venv/bin/activate가 permission denied 발생할 수 있음 → 직접 경로 사용
- Admin 테스트 데이터의 42092(레드향)은 사이트에서 내려감 (현재 42563/42564)
- 설명 텍스트 추출: detail_content에 HTML 서식 보존 (sanitize_html로 안전 태그만 유지)
- SQLAlchemy 세션 닫기 전 joinedload + 미리 로드 필요 (DetachedInstanceError 방지)

## 리팩토링 TODO (코드 리뷰에서 발견, 대규모 변경 필요)
1. **Admin 로그인 로직 3곳 중복** → 공통 `AdminSession` 헬퍼 필요 (crawler.py, order_processor.py, payment_checker.py)
2. **`get_session()` 매 호출마다 새 엔진 생성** → 싱글톤 패턴 필요 (models.py)
3. **Order 상태값이 raw 문자열** → enum/상수 정의 필요 (pending, processing, awaiting_payment, paid, out_of_stock, failed)
4. **`fetch_admin_mapping`과 `fetch_article_data` 중복** → 공통 유틸리티 필요 (crawler.py, order_processor.py)

## 향후 계획 (Next Steps) — 우선순위 순
1. **OpenClaw 맥으로 프로젝트 이전 + 도메인 + 웹 배포**: 프로젝트를 OpenClaw가 설치된 맥으로 이전 → 도메인 구매 → 웹 퍼블리싱 (외부 접속 가능하게)
2. **텔레그램 봇 + OpenClaw 원격 개발 환경**: 텔레그램 봇 연동 → OpenClaw 통해 원격으로 전체 코드 수정/프로세스 개선 가능한 환경 구성 (이상 상황·구매 상황·event_logs 보고 자동화 포함)
3. **카카오톡 CS 챗봇**: 초기에 kmsg(github.com/channprj/kmsg) + OpenClaw MCP로 프로토타입, 장기적으로 카카오 비즈니스 채널 + 챗봇 API (카카오 i 오픈빌더 또는 카카오톡 채널 API)로 전환
4. **네이버 밴드 자동화 테스트**: 텔레그램 가동 후 preview/production 밴드 구분하여 상품 컨텐츠 자동 게시 플로우 테스트
5. **로그인 시스템**: 관리자 로그인 (대시보드, 주문 관리, 크롤링 제어) + 고객 회원가입/로그인 (주문 내역 조회, 재주문 등)
6. **장바구니 기능**: 로그인 시스템 구현 후 추가 (현재는 비활성)
7. **직접 판매 상품**: 대행 판매 외에 자체 상품 등록/판매 기능 추가
