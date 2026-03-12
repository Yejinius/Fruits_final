"""
네이버 밴드 자동 포스팅 (Selenium)
- 상시 실행 Chrome (remote debugging port) 방식으로 세션 유지
- DB 상품 정보로 홍보 게시물 + 이미지 첨부
- 자동 네이버 로그인 + SMS 인증 (imsg CLI)
"""
import json
import re
import time
import os
import stat
import subprocess
from pathlib import Path

import requests as http_requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import UnexpectedAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager

from config import BAND_PREVIEW_URL, BAND_PRODUCTION_URL, SHOPPING_MALL_URL, IMAGES_DIR, DATA_DIR, SELLER_KAKAO_URL, OUR_KAKAO_URL
from models import get_session, Product, Category, init_db, log_event

# Chrome 프로필 저장 경로 (로그인 세션 유지)
CHROME_PROFILE_DIR = DATA_DIR / "chrome_profile"
REMOTE_DEBUG_PORT = 9222

# 네이버 자격증명 파일 (.secrets/ — git에서 제외)
NAVER_CREDENTIALS_FILE = DATA_DIR.parent / ".secrets" / "naver_credentials.json"

# imsg CLI 경로 (OpenClaw Mac에서 SMS 읽기용)
IMSG_BIN = "/opt/homebrew/bin/imsg"


def get_product_url(article_idx):
    """상품 구매 페이지 URL 생성 (SHOPPING_MALL_URL은 config.py에서 관리)"""
    return f"{SHOPPING_MALL_URL}/product/{article_idx}"


def is_chrome_running():
    """Remote debugging Chrome이 실행 중인지 확인"""
    try:
        resp = http_requests.get(f'http://127.0.0.1:{REMOTE_DEBUG_PORT}/json/version', timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def start_persistent_chrome():
    """Chrome을 remote debugging 모드로 상시 실행 (로그인 세션 유지용)"""
    if is_chrome_running():
        print("  Chrome이 이미 실행 중입니다.")
        return True

    CHROME_PROFILE_DIR.mkdir(exist_ok=True)

    # macOS Chrome 경로
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    chrome_bin = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_bin = p
            break

    if not chrome_bin:
        print("  Chrome을 찾을 수 없습니다.")
        return False

    cmd = [
        chrome_bin,
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        f"--remote-debugging-port={REMOTE_DEBUG_PORT}",
        "--window-size=1200,900",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-notifications",
    ]

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Chrome 시작 대기
    for _ in range(10):
        time.sleep(1)
        if is_chrome_running():
            print(f"  Chrome 시작 완료 (port {REMOTE_DEBUG_PORT})")
            return True

    print("  Chrome 시작 실패")
    return False


class BandPoster:
    BAND_HOME = "https://band.us"

    def __init__(self, headless=False):
        self.driver = None
        self.headless = headless
        self._attached = False  # 기존 Chrome에 연결했는지 여부

    def _init_driver(self):
        """Chrome WebDriver 초기화 — 실행 중인 Chrome에 연결 또는 새로 시작"""
        # 1. 실행 중인 Chrome에 연결 시도
        if is_chrome_running():
            try:
                options = Options()
                options.add_experimental_option("debuggerAddress", f"127.0.0.1:{REMOTE_DEBUG_PORT}")

                driver_path = ChromeDriverManager().install()
                if os.path.basename(driver_path) != "chromedriver":
                    driver_dir = os.path.dirname(driver_path)
                    correct_path = os.path.join(driver_dir, "chromedriver")
                    if os.path.exists(correct_path):
                        driver_path = correct_path
                os.chmod(driver_path, os.stat(driver_path).st_mode | stat.S_IEXEC)

                service = Service(driver_path)
                self.driver = webdriver.Chrome(service=service, options=options)
                self.driver.implicitly_wait(5)
                self._attached = True
                print("  기존 Chrome에 연결됨 (persistent mode)")
                return
            except Exception as e:
                print(f"  기존 Chrome 연결 실패: {e}")

        # 2. 새 Chrome 시작 (fallback — login 등에서 사용)
        CHROME_PROFILE_DIR.mkdir(exist_ok=True)
        options = Options()
        if self.headless:
            options.add_argument("--window-position=-9999,-9999")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1200,900")
        options.add_argument("--disable-notifications")
        options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
        options.add_argument(f"--remote-debugging-port={REMOTE_DEBUG_PORT}")
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2
        })

        driver_path = ChromeDriverManager().install()
        if os.path.basename(driver_path) != "chromedriver":
            driver_dir = os.path.dirname(driver_path)
            correct_path = os.path.join(driver_dir, "chromedriver")
            if os.path.exists(correct_path):
                driver_path = correct_path

        os.chmod(driver_path, os.stat(driver_path).st_mode | stat.S_IEXEC)

        service = Service(driver_path)
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.implicitly_wait(5)
        self._attached = False
        print("  새 Chrome 시작됨")

    def close(self):
        """브라우저 연결 해제 (persistent Chrome은 종료하지 않음)"""
        if self.driver:
            if self._attached:
                # 기존 Chrome에 연결한 경우: 드라이버만 종료, Chrome은 유지
                try:
                    self.driver.service.stop()
                except Exception:
                    pass
            else:
                self.driver.quit()
            self.driver = None

    # ── 로그인 ──────────────────────────────────────────

    COOKIE_FILE = DATA_DIR / "band_cookies.json"

    def _save_cookies(self):
        """CDP로 모든 도메인 쿠키를 JSON 파일로 저장 (네이버 SSO 포함)"""
        result = self.driver.execute_cdp_cmd('Network.getAllCookies', {})
        cookies = result.get('cookies', [])
        with open(self.COOKIE_FILE, 'w') as f:
            json.dump(cookies, f)
        domains = set(c.get('domain', '') for c in cookies)
        print(f"  쿠키 저장 완료 ({len(cookies)}개, 도메인: {len(domains)}개 → {self.COOKIE_FILE})")

    def _load_cookies(self):
        """CDP로 저장된 쿠키를 모든 도메인에 로드"""
        if not self.COOKIE_FILE.exists():
            return False
        try:
            with open(self.COOKIE_FILE, 'r') as f:
                cookies = json.load(f)
            # CDP setCookies는 도메인 무관하게 모든 쿠키를 한 번에 설정
            self.driver.execute_cdp_cmd('Network.setCookies', {'cookies': cookies})
            domains = set(c.get('domain', '') for c in cookies)
            print(f"  쿠키 로드 완료 ({len(cookies)}개, 도메인: {len(domains)}개)")
            return True
        except Exception as e:
            print(f"  쿠키 로드 실패: {e}")
            return False

    def login(self):
        """수동 로그인 — Chrome을 persistent 모드로 시작하고 로그인 대기"""
        # persistent Chrome 시작 (이미 실행 중이면 연결만)
        if not is_chrome_running():
            start_persistent_chrome()
            time.sleep(2)

        self._init_driver()

        print("\n" + "=" * 50)
        print("네이버 밴드 로그인")
        print("=" * 50)

        self.driver.get(self.BAND_HOME)
        time.sleep(2)

        print("\n브라우저에서 네이버/밴드 계정으로 로그인해주세요.")
        print("(Chrome은 상시 실행 모드로 유지됩니다)\n")

        # 로그인 대기 (input 또는 폴링)
        test_url = BAND_PREVIEW_URL or self.BAND_HOME
        try:
            input(">>> 로그인 완료 후 Enter를 누르세요... ")
        except EOFError:
            # SSH 환경: 유저가 Chrome에서 직접 로그인+밴드 페이지 이동할 때까지 대기
            print(f">>> 자동 대기 모드 (최대 10분)")
            print(f"  1. Chrome에서 로그인 버튼을 클릭하세요")
            print(f"  2. 네이버 로그인 완료 후 {test_url} 로 이동하세요")
            print(f"  3. 글쓰기 버튼이 보이면 자동 감지됩니다\n")
            for i in range(120):  # 5초 × 120 = 10분
                time.sleep(5)
                try:
                    self.driver.find_element(By.CSS_SELECTOR, "button._btnWritePost")
                    print(f"\n  로그인+글쓰기 권한 확인! ({(i+1)*5}초)")
                    break
                except Exception:
                    if (i+1) % 6 == 0:
                        print(f"  대기 중... ({(i+1)*5}초) URL: {self.driver.current_url[:60]}")
            else:
                print("\n  10분 타임아웃.")

        # 로그인 상태 최종 확인
        self.driver.get(test_url)
        time.sleep(5)
        try:
            self.driver.find_element(By.CSS_SELECTOR, "button._btnWritePost")
            print("\n  로그인 성공! Chrome이 상시 실행 모드로 유지됩니다.")
            print("  이제 band-post 명령으로 게시물을 올릴 수 있습니다.")
        except Exception:
            print("  글쓰기 권한이 없습니다. 밴드 페이지 관리자 계정으로 로그인했는지 확인하세요.")

        # Chrome은 종료하지 않음 (persistent 모드)
        self.close()

    def check_login(self, band_url=None):
        """로그인 상태 확인 — 실패 시 자동 로그인 시도"""
        # persistent Chrome이 아닌 경우에만 쿠키 파일 로드
        if not self._attached and self.COOKIE_FILE.exists():
            self._load_cookies()

        test_url = band_url or BAND_PREVIEW_URL or self.BAND_HOME
        self.driver.get(test_url)
        time.sleep(5)
        self._dismiss_alert()

        current_url = self.driver.current_url
        needs_login = False

        if "auth.band.us" in current_url or "login" in current_url:
            needs_login = True
        else:
            try:
                self.driver.find_element(By.CSS_SELECTOR, "button._btnWritePost, a.uButtonWrite")
                print("  로그인 상태 확인 OK")
                return True
            except Exception:
                page_source = self.driver.page_source
                if "로그인" in page_source or "회원가입" in page_source:
                    needs_login = True
                else:
                    print("  로그인 상태 확인 OK (글쓰기 버튼 미발견, 페이지 로드 지연 가능)")
                    return True

        if needs_login:
            print("  세션 만료 감지 → 자동 로그인 시도...")
            if self._auto_login():
                # 로그인 성공 후 밴드 페이지 재확인
                self.driver.get(test_url)
                time.sleep(5)
                self._dismiss_alert()
                try:
                    self.driver.find_element(By.CSS_SELECTOR, "button._btnWritePost, a.uButtonWrite")
                    print("  자동 로그인 성공! 글쓰기 권한 확인 OK")
                    self._save_cookies()
                    return True
                except Exception:
                    print("  자동 로그인 후 글쓰기 권한 미확인")
                    return False
            else:
                print("  자동 로그인 실패. 수동 band-login이 필요합니다.")
                self._send_login_failure_alert()
                return False

    # ── 자동 로그인 ──────────────────────────────────────

    @staticmethod
    def _load_naver_credentials():
        """저장된 네이버 자격증명 로드"""
        if not NAVER_CREDENTIALS_FILE.exists():
            print("  네이버 자격증명 파일 없음:", NAVER_CREDENTIALS_FILE)
            return None, None
        try:
            with open(NAVER_CREDENTIALS_FILE) as f:
                creds = json.load(f)
            return creds.get("id"), creds.get("pw")
        except Exception as e:
            print(f"  자격증명 로드 실패: {e}")
            return None, None

    @staticmethod
    def _read_sms_code(timeout=120):
        """imsg CLI로 최근 SMS에서 네이버 인증번호 추출 (최대 timeout초 대기)"""
        if not os.path.exists(IMSG_BIN):
            print(f"  imsg 미설치: {IMSG_BIN}")
            return None

        start = time.time()
        checked_ids = set()
        print(f"  SMS 인증번호 대기 중 (최대 {timeout}초)...")

        while time.time() - start < timeout:
            try:
                # 최근 채팅 목록에서 네이버 관련 번호 찾기
                result = subprocess.run(
                    [IMSG_BIN, "chats", "--limit", "30", "--json"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0:
                    time.sleep(5)
                    continue

                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        chat = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    chat_id = chat.get("id")
                    identifier = chat.get("identifier", "")
                    # 네이버 인증 문자 발신번호: 1588-3820, 15883820, NAVER 등
                    if not any(x in identifier for x in ["1588", "3820", "NAVER", "naver"]):
                        continue

                    # 이 채팅의 최근 메시지 확인
                    hist = subprocess.run(
                        [IMSG_BIN, "history", "--chat-id", str(chat_id), "--limit", "3", "--json"],
                        capture_output=True, text=True, timeout=10
                    )
                    if hist.returncode != 0:
                        continue

                    for msg_line in hist.stdout.strip().split("\n"):
                        if not msg_line.strip():
                            continue
                        try:
                            msg = json.loads(msg_line)
                        except json.JSONDecodeError:
                            continue

                        msg_id = msg.get("id", 0)
                        if msg_id in checked_ids:
                            continue
                        checked_ids.add(msg_id)

                        text = msg.get("text", "")
                        # 인증번호 패턴: 6자리 숫자
                        match = re.search(r'인증번호[^\d]*(\d{6})', text)
                        if not match:
                            match = re.search(r'(\d{6})', text)
                        if match:
                            code = match.group(1)
                            # 최근 3분 이내 메시지만 유효
                            msg_date = msg.get("date", "")
                            print(f"  SMS 인증번호 수신: {code}")
                            return code

            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                print(f"  SMS 읽기 오류: {e}")

            time.sleep(5)

        print("  SMS 인증번호 대기 타임아웃")
        return None

    def _auto_login(self):
        """네이버 자동 로그인 (저장된 ID/PW + SMS 인증)"""
        naver_id, naver_pw = self._load_naver_credentials()
        if not naver_id or not naver_pw:
            return False

        try:
            print("  네이버 로그인 페이지 이동...")
            self.driver.get("https://nid.naver.com/nidlogin.login")
            time.sleep(3)

            # "로그인 상태 유지" 체크박스
            try:
                keep_login = self.driver.find_element(By.CSS_SELECTOR, "#keep, .keep_check, label[for='keep']")
                if not keep_login.is_selected():
                    keep_login.click()
                    print("  '로그인 상태 유지' 체크")
                    time.sleep(0.5)
            except Exception:
                # 체크박스를 못 찾아도 계속 진행
                pass

            # ID/PW 입력 (클립보드 방식 — 캡차 회피)
            id_field = self.driver.find_element(By.CSS_SELECTOR, "#id")
            pw_field = self.driver.find_element(By.CSS_SELECTOR, "#pw")

            # JavaScript로 직접 값 설정 (send_keys 대신 — 봇 탐지 회피)
            self.driver.execute_script("""
                var el = arguments[0];
                el.focus();
                el.value = arguments[1];
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            """, id_field, naver_id)
            time.sleep(0.5)

            self.driver.execute_script("""
                var el = arguments[0];
                el.focus();
                el.value = arguments[1];
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            """, pw_field, naver_pw)
            time.sleep(0.5)

            # 로그인 버튼 클릭
            login_btn = self.driver.find_element(By.CSS_SELECTOR, "#log\\.login, .btn_login, button[type='submit']")
            login_btn.click()
            print("  로그인 버튼 클릭")
            time.sleep(5)

            current_url = self.driver.current_url

            # 캡차 감지
            if "captcha" in current_url.lower() or "보안문자" in self.driver.page_source:
                print("  ⚠️ 캡차 감지됨 — 자동 로그인 불가")
                self._send_login_failure_alert("캡차가 필요합니다. 수동 로그인 필요.")
                return False

            # SMS 인증 화면 감지
            page_source = self.driver.page_source
            if "인증번호" in page_source or "본인확인" in page_source or "deviceConfirm" in current_url:
                print("  SMS 인증 요청 감지")

                # 인증번호 요청 버튼 클릭 (있다면)
                try:
                    send_btn = self.driver.find_element(
                        By.XPATH, "//button[contains(text(), '인증번호') or contains(text(), '전송')]"
                    )
                    send_btn.click()
                    print("  인증번호 전송 버튼 클릭")
                    time.sleep(3)
                except Exception:
                    pass

                # imsg로 SMS 인증번호 읽기
                code = self._read_sms_code(timeout=120)
                if not code:
                    self._send_login_failure_alert("SMS 인증번호를 수신하지 못했습니다.")
                    return False

                # 인증번호 입력
                try:
                    code_input = self.driver.find_element(
                        By.CSS_SELECTOR, "input[type='tel'], input[type='number'], input.input_text, #otp"
                    )
                    code_input.clear()
                    code_input.send_keys(code)
                    time.sleep(0.5)

                    # 확인 버튼 클릭
                    confirm_btn = self.driver.find_element(
                        By.XPATH, "//button[contains(text(), '확인') or contains(text(), '인증')]"
                    )
                    confirm_btn.click()
                    print("  인증번호 입력 완료")
                    time.sleep(5)
                except Exception as e:
                    print(f"  인증번호 입력 실패: {e}")
                    return False

            # 로그인 성공 확인
            current_url = self.driver.current_url
            if "nid.naver.com" not in current_url or "login" not in current_url:
                print("  네이버 로그인 성공!")

                # 밴드로 이동하여 세션 연동 확인
                self.driver.get("https://auth.band.us/login_page?next_url=https://band.us")
                time.sleep(3)

                # "네이버로 로그인" 버튼 클릭
                try:
                    naver_login_btn = self.driver.find_element(
                        By.CSS_SELECTOR, "a.uBtn.-naver, a[href*='naver'], .naverLogin"
                    )
                    naver_login_btn.click()
                    print("  밴드 → 네이버 SSO 연동 중...")
                    time.sleep(5)
                except Exception:
                    # 이미 로그인되어 있으면 자동 리다이렉트됨
                    pass

                return True
            else:
                print("  네이버 로그인 실패 (로그인 페이지 유지)")
                return False

        except Exception as e:
            print(f"  자동 로그인 오류: {e}")
            return False

    @staticmethod
    def _send_login_failure_alert(detail=""):
        """로그인 실패 시 텔레그램 알림 발송"""
        try:
            from telegram_bot import send_alert
            msg = "🔑 밴드 자동 로그인 실패"
            if detail:
                msg += f"\n{detail}"
            msg += "\n수동 band-login이 필요합니다."
            send_alert(msg)
        except Exception:
            pass

    # ── 콘텐츠 생성 ──────────────────────────────────────

    @staticmethod
    def format_product_content(product):
        """상품 정보로 홍보 게시물 텍스트 생성"""
        buy_url = get_product_url(product.article_idx)
        lines = []

        # ── 상단 구매 링크 ──
        lines.append(f"바로 구매하기: {buy_url}")
        lines.append("")
        lines.append("─" * 20)
        lines.append("")

        # ── 상품명 ──
        lines.append(f"{product.name}")
        lines.append("")

        # 가격
        if product.price:
            price_str = f"{product.price:,}원"
            if product.original_price and product.original_price > product.price:
                discount = int((1 - product.price / product.original_price) * 100)
                price_str += f" ({discount}% 할인!)"
            lines.append(f"가격: {price_str}")

        # 배송비
        if product.delivery_fee is not None:
            if product.delivery_fee == 0:
                lines.append("배송비: 무료배송")
            else:
                lines.append(f"배송비: {product.delivery_fee:,}원")

        # 재고
        if product.stock and product.stock > 0:
            lines.append(f"재고: {product.stock}개")

        lines.append("")

        # 설명 (전체) - 카카오 오픈채팅 URL을 우리 채팅방으로 교체
        if product.description:
            desc = product.description.strip()
            desc = desc.replace(SELLER_KAKAO_URL, OUR_KAKAO_URL)
            lines.append(desc)
            lines.append("")

        # ── 하단 구매 링크 ──
        lines.append("─" * 20)
        lines.append("")
        lines.append(f"바로 구매하기: {buy_url}")

        return "\n".join(lines)

    def _get_product_images(self, product):
        """상품의 로컬 이미지 경로 목록 반환 (상세 이미지만, 인덱스 0은 메인 이미지와 중복이므로 제외)"""
        images = []

        # 상세 이미지 사용 (인덱스 0 = 메인 이미지와 동일하므로 스킵)
        if product.detail_images:
            try:
                detail_urls = json.loads(product.detail_images)
            except (json.JSONDecodeError, TypeError):
                detail_urls = []

            for i, url in enumerate(detail_urls):
                if i == 0:
                    continue  # 메인 이미지 중복 방지
                img = self._find_local_image(product.article_idx, "detail", i)
                if not img:
                    img = self._download_image(url, product.article_idx, "detail", i)
                if img:
                    images.append(img)

        # 마지막 이미지 높이 4000px 초과 시 YoungFreshMall 홍보 이미지로 교체
        if images:
            try:
                from PIL import Image
                from config import TAIL_IMAGE_PATH
                with Image.open(images[-1]) as img_check:
                    if img_check.height > 4000:
                        print(f"    마지막 이미지 높이 {img_check.height}px → YF 홍보 이미지로 교체")
                        images[-1] = str(TAIL_IMAGE_PATH)
            except Exception as e:
                print(f"    마지막 이미지 높이 체크 실패: {e}")

        return images

    @staticmethod
    def _find_local_image(article_idx, img_type, order):
        """로컬에 이미 다운로드된 이미지 찾기"""
        for ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            path = IMAGES_DIR / f"{article_idx}_{img_type}_{order}.{ext}"
            if path.exists():
                return str(path)
        return None

    @staticmethod
    def _download_image(url, article_idx, img_type="main", order=0):
        """이미지 URL에서 다운로드"""
        import requests
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                ext = url.rsplit('.', 1)[-1].split('?')[0][:4] or 'jpg'
                path = IMAGES_DIR / f"{article_idx}_{img_type}_{order}.{ext}"
                with open(path, 'wb') as f:
                    f.write(resp.content)
                print(f"    이미지 다운로드: {path.name} ({len(resp.content):,} bytes)")
                return str(path)
        except Exception as e:
            print(f"    이미지 다운로드 실패: {e}")
        return None

    # ── 게시물 작성 ──────────────────────────────────────

    def post_product(self, band_url, article_idx):
        """상품 게시물을 밴드에 작성. 성공 시 게시물 URL 반환, 실패 시 None."""
        init_db()
        session = get_session()
        product = session.query(Product).filter_by(article_idx=article_idx).first()

        if not product:
            print(f"상품 {article_idx}를 찾을 수 없습니다.")
            session.close()
            return None

        if not product.is_active:
            print(f"비활성 상품입니다: {product.name}")
            session.close()
            return None

        print(f"\n게시물 작성 준비:")
        print(f"  상품: {product.name}")
        print(f"  가격: {product.price:,}원")

        content = self.format_product_content(product)
        images = self._get_product_images(product)

        print(f"  이미지: {len(images)}개")
        print(f"\n--- 게시물 미리보기 ---")
        print(content)
        print(f"--- 끝 ---\n")

        post_url = self._write_post(band_url, content, images)
        session.close()
        return post_url

    def _dismiss_alert(self):
        """열려있는 JS alert를 감지하고 dismiss"""
        try:
            alert = self.driver.switch_to.alert
            text = alert.text
            alert.dismiss()
            print(f"    [alert dismissed] {text}")
            return text
        except Exception:
            return None

    def _write_post(self, band_url, content, image_paths=None):
        """밴드에 글쓰기 실행 (Selenium 자동화)"""
        wait = WebDriverWait(self.driver, 15)

        # 1. 밴드 페이지 이동
        print("  밴드 페이지 이동 중...")
        self.driver.get(band_url)
        time.sleep(5)
        self._dismiss_alert()

        print(f"  현재 URL: {self.driver.current_url}")

        try:
            # 2. 글쓰기 레이어 열기
            print("  글쓰기 레이어 열기...")
            editor = self._open_write_layer(wait)

            # 3. CKEditor API로 텍스트 입력 (줄바꿈 + 이모지 정상 처리)
            print("  텍스트 입력 중...")
            self._input_text(editor, content)
            time.sleep(1)

            # 4. 이미지 첨부
            if image_paths:
                print(f"  이미지 첨부 중 ({len(image_paths)}개)...")
                self._attach_images(wait, image_paths)

            # 5. 게시 버튼 클릭
            print("  게시 중...")
            self._click_submit(wait)
            time.sleep(3)

            # alert 체크 (게시 실패 시 "잘못된 요청입니다" 등)
            alert_text = self._dismiss_alert()
            if alert_text:
                log_event('error', 'band', f"게시 후 alert: {alert_text}", detail=f"band_url={band_url}")
                return None

            # 6. 게시 후 URL 캡처 + 쿠키 백업
            post_url = self.driver.current_url
            print(f"  게시물 작성 완료! URL: {post_url}")
            try:
                self._save_cookies()
            except Exception:
                pass
            return post_url

        except UnexpectedAlertPresentException as e:
            alert_text = self._dismiss_alert() or str(e)
            log_event('error', 'band', f"게시물 작성 중 alert: {alert_text}", detail=f"band_url={band_url}")
            print(f"  게시 실패 (alert): {alert_text}")
            return None
        except Exception as e:
            self._dismiss_alert()
            log_event('error', 'band', f"게시물 작성 실패: {e}", detail=f"band_url={band_url}")
            try:
                screenshot_path = IMAGES_DIR / "band_error_screenshot.png"
                self.driver.save_screenshot(str(screenshot_path))
                print(f"  스크린샷 저장: {screenshot_path}")
            except Exception:
                pass
            return None

    def _open_write_layer(self, wait):
        """글쓰기 레이어 열기"""
        btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button._btnWritePost, button._btnPostWrite, button._btnOpenWriteLayer")
        ))
        print(f"    글쓰기 버튼 클릭")
        btn.click()
        time.sleep(2)

        editor = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.contentEditor._richEditor[contenteditable='true']")
        ))
        print(f"    에디터 로드 완료")
        return editor

    def _input_text(self, editor, content):
        """CKEditor에 텍스트 입력 (줄바꿈을 <p> 태그로 변환)"""
        editor.click()
        time.sleep(0.3)

        # 각 줄을 <p> 태그로 감싸기 (CKEditor 방식)
        lines = content.split('\n')
        paragraphs = []
        for line in lines:
            escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if escaped.strip():
                paragraphs.append(f"<p>{escaped}</p>")
            else:
                paragraphs.append("<p><br></p>")

        html = "".join(paragraphs)

        # CKEditor setData API 사용
        result = self.driver.execute_script("""
            var editor = CKEDITOR.instances.editor1;
            if (editor) {
                editor.setData(arguments[0]);
                return 'ckeditor:' + editor.getData().length;
            } else {
                arguments[1].innerHTML = arguments[0];
                return 'innerHTML:' + arguments[1].innerHTML.length;
            }
        """, html, editor)
        print(f"    텍스트 입력 결과: {result}")
        time.sleep(1)

    def _attach_images(self, wait, image_paths):
        """이미지 파일 첨부 (hidden file input → 첨부하기 버튼)"""
        file_input = self.driver.find_element(
            By.CSS_SELECTOR, "input[name='attachment'][accept='image/*']"
        )
        abs_paths = [os.path.abspath(p) for p in image_paths]
        file_input.send_keys("\n".join(abs_paths))
        print(f"    이미지 {len(abs_paths)}개 선택됨")
        time.sleep(2 + len(abs_paths))  # 이미지 수에 비례해서 대기

        # "첨부하기" 버튼 클릭 (사진 올리기 팝업)
        try:
            attach_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(text(), '첨부하기')]")
            ))
            attach_btn.click()
            print(f"    첨부하기 버튼 클릭")
            time.sleep(3)
        except Exception:
            print(f"    첨부하기 버튼을 찾지 못함 (이미 첨부됨?)")

    def _click_submit(self, wait):
        """게시 버튼 클릭"""
        btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button._btnSubmitPost")))
        btn.click()
        print(f"    게시 버튼 클릭 완료")
        return True


# ── CLI 진입점 함수 ──────────────────────────────────

def band_login():
    """밴드 로그인 (Chrome 프로필에 세션 저장)"""
    poster = BandPoster()
    try:
        poster.login()
    except KeyboardInterrupt:
        print("\n로그인 취소됨")
    finally:
        poster.close()


def band_post(article_idx, band_url=None):
    """단일 상품 밴드 포스팅"""
    url = band_url or BAND_PREVIEW_URL
    if not url:
        print("밴드 URL이 설정되지 않았습니다.")
        print("config.py의 BAND_PREVIEW_URL을 설정하거나 --band-url 옵션을 사용하세요.")
        return

    poster = BandPoster()
    try:
        poster._init_driver()
        if not poster.check_login():
            return
        poster.post_product(url, article_idx)
    except KeyboardInterrupt:
        print("\n포스팅 취소됨")
    finally:
        poster.close()


def band_post_category(category_code, band_url=None):
    """카테고리 전체 상품 밴드 포스팅"""
    from config import CATEGORIES
    url = band_url or BAND_PREVIEW_URL
    if not url:
        print("밴드 URL이 설정되지 않았습니다.")
        return

    if category_code not in CATEGORIES:
        print(f"잘못된 카테고리: {category_code}")
        return

    init_db()
    session = get_session()
    cat = session.query(Category).filter_by(code=category_code).first()
    if not cat:
        print(f"카테고리 {category_code}가 DB에 없습니다.")
        session.close()
        return

    products = session.query(Product).filter_by(
        category_id=cat.id, is_active=True
    ).all()

    from config import CATEGORIES as cats
    print(f"\n{cats[category_code]} 카테고리: {len(products)}개 상품")

    poster = BandPoster()
    try:
        poster._init_driver()
        if not poster.check_login():
            session.close()
            return

        for i, product in enumerate(products, 1):
            print(f"\n[{i}/{len(products)}] {product.name}")
            poster.post_product(url, product.article_idx)
            time.sleep(3)

        print(f"\n전체 완료: {len(products)}개 게시물")
    except KeyboardInterrupt:
        print("\n포스팅 중단됨")
    finally:
        poster.close()
        session.close()


# ── Incremental 포스팅 함수 ──────────────────────────

def get_unposted_products(category_code=None):
    """밴드에 아직 게시되지 않은 활성 상품 목록 조회"""
    from sqlalchemy.orm import joinedload

    init_db()
    session = get_session()

    from sqlalchemy import or_
    query = session.query(Product).options(
        joinedload(Product.category)
    ).filter(
        Product.is_active == True,
        Product.band_posted_at == None,
        or_(Product.band_skipped == False, Product.band_skipped == None),
    )

    if category_code:
        cat = session.query(Category).filter_by(code=category_code).first()
        if cat:
            query = query.filter(Product.category_id == cat.id)

    products = query.all()
    # 카테고리 코드 → 이름 순 정렬 (번호 일관성, category도 이 과정에서 로드됨)
    products.sort(key=lambda p: (p.category.code if p.category else 'Z', p.name))
    session.close()
    return products


def band_show_new(category_code=None):
    """밴드 미게시 상품 리스트 출력"""
    from config import CATEGORIES
    products = get_unposted_products(category_code)

    if category_code:
        label = CATEGORIES.get(category_code, category_code)
        print(f"\n[{label}] 밴드 미게시 활성 상품: {len(products)}개")
    else:
        print(f"\n[전체] 밴드 미게시 활성 상품: {len(products)}개")

    if not products:
        print("  모든 상품이 이미 밴드에 게시되었습니다.")
        return products

    print(f"\n{'─' * 60}")
    for i, p in enumerate(products, 1):
        cat_name = ""
        if p.category:
            cat_name = f"[{p.category.name}] "
        price = f"{p.price:,}원" if p.price else "가격미정"
        print(f"  {i:3d}. {cat_name}{p.name[:40]}  ({price}, ID: {p.article_idx})")
    print(f"{'─' * 60}")

    return products


def band_post_preview(article_idx):
    """단일 상품을 테스트 밴드에 미리보기 게시 → preview_url 저장"""
    from datetime import datetime

    url = BAND_PREVIEW_URL
    if not url:
        print("BAND_PREVIEW_URL이 설정되지 않았습니다.")
        return None

    poster = BandPoster()
    try:
        poster._init_driver()
        if not poster.check_login():
            return None

        post_url = poster.post_product(url, article_idx)

        if post_url:
            # DB에 preview 정보 저장
            session = get_session()
            product = session.query(Product).filter_by(article_idx=article_idx).first()
            if product:
                product.band_preview_posted_at = datetime.now()
                product.band_preview_url = post_url
                session.commit()
                log_event('info', 'band', f"미리보기 게시 완료: {product.name}", related_id=str(article_idx))
            session.close()
            print(f"\n  미리보기 URL: {post_url}")
        else:
            log_event('error', 'band', f"미리보기 게시 실패: article_idx={article_idx}", related_id=str(article_idx))

        return post_url

    except KeyboardInterrupt:
        print("\n포스팅 취소됨")
        return None
    finally:
        poster.close()


def band_post_preview_all(category_code=None):
    """미게시 상품 전체를 테스트 밴드에 미리보기 게시"""
    from datetime import datetime

    products = get_unposted_products(category_code)
    if not products:
        print("미게시 상품이 없습니다.")
        return []

    url = BAND_PREVIEW_URL
    if not url:
        print("BAND_PREVIEW_URL이 설정되지 않았습니다.")
        return []

    print(f"\n미게시 상품 {len(products)}개를 테스트 밴드에 게시합니다...")

    results = []
    poster = BandPoster()
    try:
        poster._init_driver()
        if not poster.check_login():
            return []

        for i, product in enumerate(products, 1):
            print(f"\n[{i}/{len(products)}] {product.name}")
            post_url = poster.post_product(url, product.article_idx)

            if post_url:
                session = get_session()
                p = session.query(Product).filter_by(article_idx=product.article_idx).first()
                if p:
                    p.band_preview_posted_at = datetime.now()
                    p.band_preview_url = post_url
                    session.commit()
                session.close()

                results.append({
                    'article_idx': product.article_idx,
                    'name': product.name,
                    'preview_url': post_url
                })
            else:
                log_event('error', 'band', f"미리보기 게시 실패: {product.name} (ID: {product.article_idx})", related_id=str(product.article_idx))

            time.sleep(3)

        failed = len(products) - len(results)
        if failed > 0:
            log_event('warning', 'band', f"미리보기 일괄 게시: {len(results)}/{len(products)}개 성공, {failed}개 실패")
        print(f"\n미리보기 완료: {len(results)}/{len(products)}개 성공")

    except KeyboardInterrupt:
        print("\n포스팅 중단됨")
    finally:
        poster.close()

    return results


def band_post_confirm(article_idx):
    """승인된 상품을 본 밴드에 게시 → band_posted_at 기록"""
    from datetime import datetime

    url = BAND_PRODUCTION_URL
    if not url:
        print("BAND_PRODUCTION_URL이 설정되지 않았습니다.")
        print("config.py에서 본 밴드 URL을 설정하세요.")
        return None

    poster = BandPoster()
    try:
        poster._init_driver()
        if not poster.check_login():
            return None

        post_url = poster.post_product(url, article_idx)

        if post_url:
            session = get_session()
            product = session.query(Product).filter_by(article_idx=article_idx).first()
            if product:
                product.band_posted_at = datetime.now()
                product.band_post_url = post_url
                session.commit()
                log_event('info', 'band', f"본 밴드 게시 완료: {product.name}", related_id=str(article_idx))
            session.close()
            print(f"\n  본 밴드 게시 완료: {post_url}")
        else:
            log_event('error', 'band', f"본 밴드 게시 실패: article_idx={article_idx}", related_id=str(article_idx))

        return post_url

    except KeyboardInterrupt:
        print("\n포스팅 취소됨")
        return None
    finally:
        poster.close()
