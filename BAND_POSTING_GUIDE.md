# 네이버 밴드 자동 포스팅 가이드

이 문서는 `band_poster.py`의 네이버 밴드 자동 포스팅 프로세스를 상세히 설명합니다.
**AI 에이전트(Jarvis 등)가 이 작업을 수행할 때 반드시 이 문서를 따라야 합니다.**

---

## 0. AI 에이전트를 위한 핵심 요약 (반드시 먼저 읽을 것)

### 절대 하지 말 것 (금지사항)
1. **`band_cookies.json`으로 쿠키 주입 시도하지 마세요** — 동작하지 않습니다. secure/httpOnly/SameSite 속성 때문에 밴드가 쿠키 주입을 인정하지 않습니다.
2. **`band_poster.py` 코드를 수정하지 마세요** — 이미 완성된 코드입니다. 코드를 수정하는 대신 기존 CLI 명령어를 그대로 사용하세요.
3. **직접 Selenium 코드를 작성하지 마세요** — `band_poster.py`에 모든 로직이 구현되어 있습니다. `main.py`의 CLI 명령어로 호출하세요.
4. **headless 모드로 로그인하지 마세요** — 로그인은 반드시 `headless=False`(기본값)로 실행해야 합니다.

### 반드시 이해해야 할 것
1. **인증 = Chrome 프로필 디렉토리 방식입니다** — `--user-data-dir=data/chrome_profile/` 옵션으로 Chrome을 실행하면, 로그인 세션이 이 디렉토리에 자동 저장됩니다.
2. **최초 1회 수동 로그인이 필요합니다** — 네이버 OAuth 인증이라 자동화 불가능합니다. 사람이 직접 브라우저에서 로그인해야 합니다.
3. **한번 로그인하면 이후 모든 포스팅은 자동입니다** — Chrome 프로필에 세션이 저장되므로 `band-preview`, `band-post` 등은 자동 실행됩니다.
4. **모든 기능은 `main.py` CLI로 실행합니다** — 직접 Python 코드를 작성할 필요가 없습니다.

### 올바른 작업 순서

```
[1단계] 로그인 상태 확인
    → check_login() 또는 band-preview 시도

[2단계] 로그인 안 되어 있으면
    → venv/bin/python main.py band-login 실행
    → 사용자에게 "브라우저에서 밴드 로그인해주세요" 안내
    → 사용자가 로그인 완료하면 터미널에서 Enter
    → 이 단계 이후 Chrome 프로필에 세션 저장 완료

[3단계] 게시글 작성
    → venv/bin/python main.py band-preview {article_idx}
    → 또는 venv/bin/python main.py band-preview-all
    → 코드가 알아서 로그인 확인 → 밴드 이동 → 글쓰기 → 이미지 첨부 → 게시 완료
```

---

## 1. 전체 아키텍처

```
[DB 상품 데이터] → [band_poster.py] → [Selenium Chrome + 프로필] → [네이버 밴드 글쓰기]
```

- **Selenium + Chrome 프로필** 기반 (API 없음, 순수 브라우저 자동화)
- Chrome 프로필 디렉토리(`data/chrome_profile/`)에 로그인 세션이 저장됨
- 1회 수동 로그인 후 세션 자동 유지 (쿠키 주입 X, 프로필 디렉토리 방식)

---

## 2. 인증 방식 (매우 중요)

### 올바른 방식: Chrome 프로필 디렉토리

```python
options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
# CHROME_PROFILE_DIR = data/chrome_profile/
```

- `--user-data-dir`로 Chrome 프로필 경로를 지정하면, 해당 디렉토리에 쿠키/세션/캐시가 모두 저장됨
- 한번 로그인하면 다음 실행 시에도 로그인 상태가 유지됨
- **`band_cookies.json` 파일로 쿠키를 주입하는 방식은 동작하지 않음** (secure, httpOnly, SameSite 등 속성 문제로 밴드에서 인정 안 함)

### 최초 로그인 절차 (수동, 1회만 필요)

```bash
cd ~/Fruits_final
venv/bin/python main.py band-login
```

실행하면 아래 과정이 **자동으로** 일어납니다:

1. Chrome 브라우저가 `https://band.us` 페이지로 열림 (headless=False, 화면에 보임)
2. 터미널에 ">>> 로그인 완료 후 Enter를 누르세요..." 메시지 출력
3. **여기서 사용자가 직접 브라우저에서 네이버/밴드 계정으로 로그인해야 함**
4. 사용자가 로그인 완료 후 터미널에서 Enter 입력
5. `check_login()` → 현재 URL이 `auth.band.us`나 `login`을 포함하지 않으면 성공
6. Chrome 프로필 디렉토리(`data/chrome_profile/`)에 세션 자동 저장
7. 브라우저 종료

**AI 에이전트의 역할:**
- `band-login` 명령을 실행한다
- 사용자에게 "브라우저에서 밴드 로그인해주세요. 로그인 완료되면 알려주세요." 라고 안내한다
- 사용자가 "로그인 완료"라고 하면 터미널에 Enter를 입력한다 (또는 `input()`이 자동으로 기다리고 있으므로 프로세스의 stdin에 Enter를 보낸다)
- 로그인 성공 메시지 확인 후 다음 단계 진행

### 로그인 확인 로직

```python
def check_login(self):
    self.driver.get("https://band.us")
    time.sleep(3)
    current_url = self.driver.current_url
    # auth.band.us 또는 login이 URL에 있으면 로그인 안 된 상태
    if "auth.band.us" in current_url or "login" in current_url:
        return False
    return True
```

### 세션 만료 시 대처

Chrome 프로필의 세션이 만료되면 다시 `band-login` 실행 필요:
```bash
venv/bin/python main.py band-login
```

**세션 수명:** 보통 수일~수주 유지됨. 밴드에서 강제 로그아웃되거나 Chrome 프로필이 손상되면 만료됨.

---

## 3. 밴드 URL 구조 (중요)

### 밴드 "페이지" vs 밴드 "밴드(그룹)"

| 구분 | URL 형식 | 특징 |
|------|----------|------|
| 밴드 페이지 | `band.us/page/101768540` | 공개 페이지, 관리자만 글쓰기 가능 |
| 밴드 그룹 | `band.us/band/12345678` | 멤버 가입 필요, 멤버 글쓰기 가능 |

현재 설정 (.env):
- **BAND_PREVIEW_URL** = `https://band.us/page/101768540` (테스트용 밴드 페이지)
- **BAND_PRODUCTION_URL** = 미설정 (본 밴드)

### 글쓰기 권한

- 밴드 **페이지**는 **페이지 관리자(운영자)** 계정으로만 글쓰기 가능
- 로그인은 되었지만 글쓰기 영역(`writeWrap`)이 비어있으면(height=0) → 관리자 권한 없는 계정으로 로그인한 것
- 관리자 계정으로 로그인했는지 반드시 확인
- **"로그인은 됐는데 글쓰기가 안 된다" = 99% 관리자 권한 문제**

---

## 4. Selenium 글쓰기 프로세스 (단계별)

> **AI 에이전트 주의: 아래 프로세스는 `band_poster.py`에 이미 전부 구현되어 있습니다.**
> **직접 코드를 작성하지 마세요. `main.py band-preview {article_idx}` 명령 하나로 전체가 실행됩니다.**

### 4.1 WebDriver 초기화

```python
options = Options()
if self.headless:
    options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1200,900")
options.add_argument("--disable-notifications")
options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")  # 핵심!

# ChromeDriverManager로 자동 설치/관리
driver_path = ChromeDriverManager().install()
# IMPORTANT: install()이 반환하는 경로가 chromedriver가 아닐 수 있음
# (예: THIRD_PARTY_NOTICES 파일 경로를 반환하기도 함)
# 그래서 같은 디렉토리의 'chromedriver' 바이너리를 찾는 로직이 있음
```

**주의: `--user-data-dir`로 프로필 경로를 이미 사용 중인 Chrome이 있으면 충돌 발생!**
- 이미 Chrome이 같은 프로필로 열려있으면 Selenium이 실행 실패
- 기존 Chrome 프로세스를 먼저 종료해야 함:
```bash
pkill -f chromedriver
pkill -f "chrome.*chrome_profile"
```

### 4.2 밴드 페이지 이동

```python
self.driver.get(band_url)  # 예: https://band.us/page/101768540
time.sleep(5)  # 페이지 로딩 대기 (5초)
```

### 4.3 글쓰기 레이어 열기

```python
# CSS 선택자: button._btnWritePost
btn = wait.until(EC.element_to_be_clickable(
    (By.CSS_SELECTOR, "button._btnWritePost")
))
btn.click()
time.sleep(2)

# 에디터 로드 대기
editor = wait.until(EC.presence_of_element_located(
    (By.CSS_SELECTOR, "div.contentEditor._richEditor[contenteditable='true']")
))
```

**트러블슈팅:**
- `button._btnWritePost`를 못 찾는 경우:
  1. 로그인 안 됨 → `band-login` 먼저 실행
  2. 관리자 권한 없음 → 밴드 페이지 관리자 계정으로 로그인했는지 확인
  3. 페이지 로딩 미완료 → `time.sleep` 늘리기
  4. 밴드 UI 변경 → 스크린샷 찍어서 현재 DOM 구조 확인

### 4.4 텍스트 입력 (CKEditor API)

밴드는 **CKEditor**를 사용합니다. 일반 `send_keys()`로는 줄바꿈이 제대로 안 됩니다.

```python
# 각 줄을 <p> 태그로 감싸기
lines = content.split('\n')
paragraphs = []
for line in lines:
    escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if escaped.strip():
        paragraphs.append(f"<p>{escaped}</p>")
    else:
        paragraphs.append("<p><br></p>")  # 빈 줄

html = "".join(paragraphs)

# CKEditor setData API 사용 (핵심!)
self.driver.execute_script("""
    var editor = CKEDITOR.instances.editor1;
    if (editor) {
        editor.setData(arguments[0]);
    } else {
        arguments[1].innerHTML = arguments[0];
    }
""", html, editor)
```

**주의:** `CKEDITOR.instances.editor1`이 없으면 fallback으로 `innerHTML` 직접 설정

### 4.5 이미지 첨부

```python
# hidden file input 찾기
file_input = self.driver.find_element(
    By.CSS_SELECTOR, "input[name='attachment'][accept='image/*']"
)
# 여러 이미지를 \n으로 구분하여 전달
abs_paths = [os.path.abspath(p) for p in image_paths]
file_input.send_keys("\n".join(abs_paths))
time.sleep(2 + len(abs_paths))  # 이미지 수에 비례해서 대기

# "첨부하기" 버튼 클릭
attach_btn = wait.until(EC.element_to_be_clickable(
    (By.XPATH, "//button[contains(text(), '첨부하기')]")
))
attach_btn.click()
time.sleep(3)
```

**이미지 규칙:**
- main 이미지 제외 (detail 첫 장과 중복)
- detail 이미지만 업로드
- 이미지 경로: `data/images/{article_idx}_detail_{index}.{ext}`

### 4.6 게시 버튼 클릭

```python
# CSS 선택자: button._btnSubmitPost
btn = wait.until(EC.element_to_be_clickable(
    (By.CSS_SELECTOR, "button._btnSubmitPost")
))
btn.click()
time.sleep(3)

# 게시 후 URL 캡처
post_url = self.driver.current_url
```

---

## 5. 콘텐츠 포맷

게시물 텍스트 구조 (`format_product_content` 메서드가 자동 생성):
```
바로 구매하기: {SHOPPING_MALL_URL}/product/{article_idx}

────────────────────

{상품명}

가격: 12,000원 (20% 할인!)
배송비: 무료배송
재고: 50개

{상품 설명 전문}
  * 카카오 오픈채팅 URL: gF7nJ96h → sNgjJoBb 로 자동 교체됨

────────────────────

바로 구매하기: {SHOPPING_MALL_URL}/product/{article_idx}
```

---

## 6. CLI 명령어 정리

> **모든 명령어는 프로젝트 루트(`~/Fruits_final`)에서 실행해야 합니다.**

```bash
cd ~/Fruits_final

# ── 로그인 (최초 1회 또는 세션 만료 시) ──
venv/bin/python main.py band-login
# → 브라우저가 열림 → 사용자가 수동 로그인 → Enter → 세션 저장

# ── 미게시 상품 리스트 확인 ──
venv/bin/python main.py band-new                    # 전체
venv/bin/python main.py band-new --category A       # 과일만

# ── 단일 상품 테스트 밴드에 미리보기 게시 ──
venv/bin/python main.py band-preview 42563
# → 로그인 확인 → 밴드 페이지 이동 → 글쓰기 → 이미지 첨부 → 게시 → URL 저장

# ── 미게시 전체 테스트 밴드에 미리보기 게시 ──
venv/bin/python main.py band-preview-all
venv/bin/python main.py band-preview-all --category A

# ── 승인 → 본 밴드에 게시 (BAND_PRODUCTION_URL 필요) ──
venv/bin/python main.py band-confirm 42563

# ── 단일 상품 직접 지정 밴드에 게시 ──
venv/bin/python main.py band-post 42563 --band-url https://band.us/band/xxxxx
```

---

## 7. DB 추적 필드 (Product 모델)

| 필드 | 용도 |
|------|------|
| `band_posted_at` | 본 밴드 게시 시각 |
| `band_post_url` | 본 밴드 게시물 URL |
| `band_preview_posted_at` | 테스트 밴드 미리보기 게시 시각 |
| `band_preview_url` | 테스트 밴드 미리보기 URL |

미게시 상품 = `is_active=True AND band_posted_at=NULL`

---

## 8. Incremental 포스팅 플로우

권장 순서:
```
1. band-new        → 미게시 상품 리스트 확인
2. band-preview    → 테스트 밴드에 개별 미리보기 (검수용)
3. (사람이 검수)    → 테스트 밴드에서 게시물 확인
4. band-confirm    → 본 밴드에 게시 (승인된 상품만)
```

또는 일괄:
```
1. band-new            → 미게시 상품 확인
2. band-preview-all    → 테스트 밴드에 전체 미리보기
3. (사람이 검수)        → 전체 확인
4. band-confirm        → 개별 승인 게시
```

---

## 9. 자주 발생하는 문제와 해결

### 문제 1: "로그인이 필요합니다"
- **원인**: Chrome 프로필의 세션 만료 또는 프로필 디렉토리가 비어있음
- **해결**: `venv/bin/python main.py band-login` 실행 후 사용자에게 수동 로그인 요청
- **AI 에이전트 주의**: 쿠키 주입이나 코드 수정으로 해결하려 하지 마세요. band-login만 실행하면 됩니다.

### 문제 2: 글쓰기 버튼(`_btnWritePost`)을 찾을 수 없음
- **원인 A**: 로그인 안 됨 → 해결: `band-login` 실행
- **원인 B**: 관리자 권한 없음 → 해결: 밴드 페이지 관리자 계정으로 로그인
- **원인 C**: headless 모드 → 해결: `headless=False`로 테스트 (기본값이 False)
- **판단법**: `check_login()`이 True를 반환하는데 글쓰기 버튼이 없다면 → 100% 관리자 권한 문제

### 문제 3: 쿠키 주입 시도
- **이 프로젝트에서 쿠키 주입은 사용하지 않습니다**
- `band_cookies.json`은 레거시 백업 파일이지 런타임에 사용하지 않음
- `add_cookie()`, `_load_cookies()` 등의 코드를 추가하지 마세요
- 반드시 `--user-data-dir` Chrome 프로필 방식만 사용

### 문제 4: Chrome 프로필 충돌
- **원인**: 동일한 `data/chrome_profile/` 경로로 다른 Chrome/chromedriver가 이미 실행 중
- **해결**: 기존 프로세스 종료 후 재실행
```bash
pkill -f chromedriver
pkill -f "chrome.*chrome_profile"
```

### 문제 5: `writeWrap`이 height=0, innerHTML 비어있음
- **원인**: 밴드 페이지 관리자 권한이 없는 계정으로 로그인됨
- **해결**: 밴드 앱/웹에서 해당 페이지의 관리자로 등록된 계정으로 `band-login` 재실행
- 확인법: 브라우저에서 직접 해당 밴드 페이지 들어가서 글쓰기 UI가 보이는지 확인

### 문제 6: ChromeDriverManager 경로 문제
- `ChromeDriverManager().install()`이 `chromedriver` 대신 다른 파일(예: THIRD_PARTY_NOTICES) 경로를 반환할 수 있음
- 코드에 이미 보정 로직 있음: 같은 디렉토리에서 `chromedriver` 바이너리를 찾음
- Mac에서 chromedriver 실행 권한: `os.chmod(driver_path, ... | stat.S_IEXEC)`

### 문제 7: band-login에서 input() 대기 중일 때
- `main.py band-login`은 `input(">>> 로그인 완료 후 Enter를 누르세요... ")`에서 블로킹됨
- AI 에이전트가 이 명령을 실행하면 프로세스가 Enter 입력을 기다리며 멈춤
- 사용자가 로그인 완료했다고 알려주면 해당 프로세스의 stdin에 Enter를 보내야 함
- 또는 타임아웃 후 프로세스를 종료하고 새로 `band-preview`를 실행해도 됨 (Chrome 프로필에 세션은 이미 저장되었으므로)

---

## 10. AI 에이전트 실전 시나리오

### 시나리오 A: 처음부터 전체 플로우 실행

```bash
# 1. 로그인 상태 확인 (band-new는 DB만 조회하므로 로그인 불필요)
cd ~/Fruits_final
venv/bin/python main.py band-new

# 2. 테스트 게시 시도 (로그인 필요)
venv/bin/python main.py band-preview 42563

# 만약 "로그인이 필요합니다" 출력되면:
# 3. 로그인 실행
venv/bin/python main.py band-login
# → 사용자에게 "브라우저에서 밴드 로그인해주세요" 안내
# → 사용자 로그인 완료 후 Enter
# → "로그인 세션이 Chrome 프로필에 저장되었습니다" 확인

# 4. 다시 테스트 게시
venv/bin/python main.py band-preview 42563
# → 성공 시 "게시물 작성 완료! URL: https://band.us/..." 출력
```

### 시나리오 B: 이미 로그인된 상태에서 게시

```bash
cd ~/Fruits_final

# 미게시 상품 확인
venv/bin/python main.py band-new

# 원하는 상품 게시 (article_idx 지정)
venv/bin/python main.py band-preview 42563

# 또는 전체 미게시 상품 일괄 게시
venv/bin/python main.py band-preview-all
```

### 시나리오 C: 세션 만료 확인 후 재로그인

```bash
# 게시 시도 → 실패
venv/bin/python main.py band-preview 42563
# 출력: "로그인이 필요합니다. band-login을 먼저 실행하세요."

# 기존 Chrome 프로세스 정리
pkill -f chromedriver 2>/dev/null
pkill -f "chrome.*chrome_profile" 2>/dev/null

# 재로그인
venv/bin/python main.py band-login
# → 사용자에게 로그인 요청 → Enter → 완료

# 다시 게시
venv/bin/python main.py band-preview 42563
```

---

## 11. 파일 구조

```
Fruits_final/
├── band_poster.py          # 밴드 포스팅 모듈 (수정 금지, 그대로 사용)
├── main.py                 # CLI 진입점 (band-login, band-post 등 명령어)
├── config.py               # BAND_PREVIEW_URL, BAND_PRODUCTION_URL 설정
├── models.py               # Product 모델 (band_posted_at 등 필드)
├── data/
│   ├── chrome_profile/     # Chrome 프로필 (로그인 세션 저장) ← .gitignore
│   ├── band_cookies.json   # 레거시 백업 (사용하지 않음) ← .gitignore
│   ├── images/             # 상품 이미지 (밴드에 첨부) ← .gitignore
│   └── products.db         # SQLite DB ← .gitignore
└── .env                    # BAND_PREVIEW_URL, BAND_PRODUCTION_URL ← .gitignore
```

---

## 12. CSS 선택자 요약 (밴드 페이지 기준)

| 요소 | 선택자 |
|------|--------|
| 글쓰기 버튼 | `button._btnWritePost` |
| 에디터 영역 | `div.contentEditor._richEditor[contenteditable='true']` |
| 이미지 입력 | `input[name='attachment'][accept='image/*']` |
| 첨부하기 버튼 | `//button[contains(text(), '첨부하기')]` (XPath) |
| 게시 버튼 | `button._btnSubmitPost` |
| 글쓰기 영역 래퍼 | `div.writeWrap[data-uiselector="postWriteRegion"]` |

**밴드가 UI를 업데이트하면 이 선택자들이 변경될 수 있음.** 실패 시 스크린샷(`data/images/band_error_screenshot.png`)을 확인하고 현재 DOM 구조를 파악해야 함.
