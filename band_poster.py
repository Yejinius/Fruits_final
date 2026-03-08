"""
네이버 밴드 자동 포스팅 (Selenium)
- Chrome 프로필 디렉토리로 로그인 세션 유지
- DB 상품 정보로 홍보 게시물 + 이미지 첨부
"""
import json
import time
import os
import stat
from pathlib import Path

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


def get_product_url(article_idx):
    """상품 구매 페이지 URL 생성 (SHOPPING_MALL_URL은 config.py에서 관리)"""
    return f"{SHOPPING_MALL_URL}/product/{article_idx}"


class BandPoster:
    BAND_HOME = "https://band.us"

    def __init__(self, headless=False):
        self.driver = None
        self.headless = headless

    def _init_driver(self):
        """Chrome WebDriver 초기화 (프로필 디렉토리로 세션 유지)"""
        CHROME_PROFILE_DIR.mkdir(exist_ok=True)

        options = Options()
        if self.headless:
            # headless에서 Chrome 프로필 쿠키 호환 문제로 GUI 모드 사용 + 창 최소화
            options.add_argument("--window-position=-9999,-9999")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1200,900")
        options.add_argument("--disable-notifications")
        options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
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

    def close(self):
        """브라우저 종료"""
        if self.driver:
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
        """수동 로그인 (쿠키를 JSON 파일로 저장)"""
        self._init_driver()

        print("\n" + "=" * 50)
        print("네이버 밴드 로그인")
        print("=" * 50)

        self.driver.get(self.BAND_HOME)
        time.sleep(2)

        print("\n브라우저에서 네이버/밴드 계정으로 로그인해주세요.")
        print("로그인이 완료되면 밴드 메인 페이지가 보일 것입니다.")
        print("(쿠키가 파일로 저장되어 headless에서도 사용 가능)\n")

        # 로그인 대기 (input 또는 폴링)
        try:
            input(">>> 로그인 완료 후 Enter를 누르세요... ")
        except EOFError:
            # SSH 환경: 유저가 Chrome에서 직접 로그인+밴드 페이지 이동할 때까지 대기
            # 페이지를 강제 이동하지 않고, 현재 URL/상태만 확인
            test_url = BAND_PREVIEW_URL or self.BAND_HOME
            print(f">>> 자동 대기 모드 (최대 5분)")
            print(f"  1. Chrome에서 로그인 버튼을 클릭하세요")
            print(f"  2. 네이버 로그인 완료 후 {test_url} 로 이동하세요")
            print(f"  3. 글쓰기 버튼이 보이면 자동 감지됩니다\n")
            for i in range(60):  # 5초 × 60 = 5분
                time.sleep(5)
                try:
                    # 현재 페이지에 글쓰기 버튼이 있는지만 확인 (페이지 이동 안 함)
                    self.driver.find_element(By.CSS_SELECTOR, "button._btnWritePost")
                    print(f"\n  로그인+글쓰기 권한 확인! ({(i+1)*5}초)")
                    break
                except Exception:
                    if (i+1) % 6 == 0:  # 30초마다 상태 출력
                        print(f"  대기 중... ({(i+1)*5}초) URL: {self.driver.current_url[:60]}")
            else:
                print("\n  5분 타임아웃.")

        # 로그인 상태 최종 확인 — 밴드 페이지에서 글쓰기 버튼
        test_url = BAND_PREVIEW_URL or self.BAND_HOME
        self.driver.get(test_url)
        time.sleep(5)
        try:
            self.driver.find_element(By.CSS_SELECTOR, "button._btnWritePost")
            self._save_cookies()
            print("\n  로그인 세션이 저장되었습니다.")
            print("  이제 band-post 명령으로 게시물을 올릴 수 있습니다.")
        except Exception:
            print("  글쓰기 권한이 없습니다. 밴드 페이지 관리자 계정으로 로그인했는지 확인하세요.")

        self.close()

    def check_login(self, band_url=None):
        """로그인 상태 확인 (쿠키 로드 → 밴드 페이지 접근 검증)"""
        # 저장된 쿠키 로드
        if self.COOKIE_FILE.exists():
            self._load_cookies()

        test_url = band_url or BAND_PREVIEW_URL or self.BAND_HOME
        self.driver.get(test_url)
        time.sleep(5)

        current_url = self.driver.current_url
        if "auth.band.us" in current_url or "login" in current_url:
            print("  로그인이 필요합니다. band-login을 먼저 실행하세요.")
            return False

        # 글쓰기 버튼 존재 확인
        try:
            self.driver.find_element(By.CSS_SELECTOR, "button._btnWritePost, a.uButtonWrite")
            print("  로그인 상태 확인 OK")
            return True
        except Exception:
            page_source = self.driver.page_source
            if "로그인" in page_source or "회원가입" in page_source:
                print("  세션이 만료되었습니다. band-login을 다시 실행하세요.")
                return False
            print("  로그인 상태 확인 OK (글쓰기 버튼 미발견, 페이지 로드 지연 가능)")
            return True

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

            # 6. 게시 후 URL 캡처
            post_url = self.driver.current_url
            print(f"  게시물 작성 완료! URL: {post_url}")
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
        btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button._btnWritePost")))
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

    query = session.query(Product).options(
        joinedload(Product.category)
    ).filter(
        Product.is_active == True,
        Product.band_posted_at == None
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
