"""
OS79.co.kr 크롤러 핵심 로직
"""
import re
import json
import time
import html as html_mod
import random
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import joinedload
from urllib.parse import urljoin, urlparse
from datetime import datetime
from typing import Optional, Dict, List, Any, Set
from tqdm import tqdm

from config import (
    BASE_URL, GOODS_LIST_URL, GOODS_VIEW_URL,
    CATEGORIES, HEADERS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
    REQUEST_TIMEOUT, MAX_RETRIES, IMAGES_DIR,
    USER_AGENTS, BLOCK_BACKOFF_BASE, BLOCK_BACKOFF_MAX,
    ADMIN_BASE_URL, ADMIN_ID, ADMIN_PW
)
from models import (
    init_db, get_session,
    Category, Product, ProductImage, CrawlLog, Order, OrderItem, log_event
)
from sms import send_out_of_stock_sms

# HTML 서식 보존용 화이트리스트 (XSS 방지)
ALLOWED_TAGS = {'b', 'strong', 'em', 'i', 'u', 'br', 'p', 'div', 'span',
                'font', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'ul', 'ol', 'li', 'a', 'sub', 'sup', 'hr', 'table',
                'tr', 'td', 'th', 'thead', 'tbody'}
ALLOWED_ATTRS = {'href', 'target', 'color', 'size', 'face'}


def sanitize_html(html_str: str) -> tuple:
    """위험한 태그 제거, 서식 태그만 유지. (sanitized_html, plain_text) 반환"""
    s = BeautifulSoup(html_str, 'html.parser')
    for tag in s.find_all(['script', 'style', 'iframe', 'object', 'embed']):
        tag.decompose()
    for tag in s.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            attrs = dict(tag.attrs)
            for attr in attrs:
                if attr not in ALLOWED_ATTRS:
                    del tag[attr]
            # href에서 javascript: 프로토콜 차단
            if 'href' in tag.attrs:
                href = tag['href'].strip().lower()
                if href.startswith('javascript:') or href.startswith('data:'):
                    del tag['href']
    cleaned = str(s)
    plain = s.get_text(strip=True)
    return cleaned, plain


class OS79Crawler:
    """OS79 사이트 크롤러"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.db_session = None

    _REFERER = BASE_URL + "/"

    def _rotate_headers(self):
        """요청마다 User-Agent 랜덤 선택 + Referer 설정"""
        self.session.headers['User-Agent'] = random.choice(USER_AGENTS)
        self.session.headers['Referer'] = self._REFERER

    def _random_delay(self):
        """랜덤 딜레이로 요청 간격 자연스럽게"""
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        time.sleep(delay)

    def _request(self, url: str, retries: int = MAX_RETRIES) -> Optional[requests.Response]:
        """HTTP 요청 with UA 로테이션, 재시도, 403/429 백오프"""
        for attempt in range(retries):
            try:
                self._rotate_headers()
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)

                # IP 차단/속도 제한 감지
                if response.status_code in (403, 429):
                    backoff = min(BLOCK_BACKOFF_BASE * (2 ** attempt), BLOCK_BACKOFF_MAX)
                    backoff += random.uniform(0, backoff * 0.5)
                    log_event('warning', 'crawl',
                        f"차단 감지 ({response.status_code}): {url} - {backoff:.0f}초 대기 (시도 {attempt+1}/{retries})")
                    time.sleep(backoff)
                    continue

                response.raise_for_status()
                # 인코딩 처리 (EUC-KR 사이트)
                response.encoding = response.apparent_encoding or 'euc-kr'
                return response
            except requests.RequestException as e:
                print(f"[Attempt {attempt + 1}/{retries}] Request failed: {url} - {e}")
                if attempt < retries - 1:
                    backoff = REQUEST_DELAY_MAX * (2 ** attempt)
                    time.sleep(backoff)
        return None

    def get_product_list(self, category_code: str) -> List[Dict[str, Any]]:
        """특정 카테고리의 상품 목록 가져오기"""
        url = f"{GOODS_LIST_URL}?s_article_gubun={category_code}"
        print(f"\n[Category {category_code}] Fetching: {url}")

        response = self._request(url)
        if not response:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        products = []

        # 상품 링크 찾기 (goods_view.asp?article_idx=XXXXX 패턴)
        links = soup.find_all('a', href=re.compile(r'goods_view\.asp\?article_idx=\d+'))

        seen_ids = set()
        for link in links:
            href = link.get('href', '')
            match = re.search(r'article_idx=(\d+)', href)
            if match:
                article_idx = int(match.group(1))
                if article_idx not in seen_ids:
                    seen_ids.add(article_idx)
                    # 상품명 추출 시도
                    name = link.get_text(strip=True)
                    if not name:
                        # 상위 요소에서 찾기
                        parent = link.find_parent('li') or link.find_parent('div')
                        if parent:
                            name = parent.get_text(strip=True)[:100]

                    products.append({
                        'article_idx': article_idx,
                        'name_preview': name,
                        'url': urljoin(BASE_URL, f"/board_order/goods_view.asp?article_idx={article_idx}")
                    })

        print(f"[Category {category_code}] Found {len(products)} products")
        return products

    def get_product_detail(self, article_idx: int) -> Optional[Dict[str, Any]]:
        """상품 상세 정보 가져오기"""
        url = f"{GOODS_VIEW_URL}?article_idx={article_idx}"

        response = self._request(url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        product = {'article_idx': article_idx, 'source_url': url}

        # 1. 상품명
        name_elem = soup.find(id='txt_article_name') or soup.find(class_='viewTit')
        if name_elem:
            product['name'] = name_elem.get_text(strip=True)
        else:
            # 타이틀에서 추출
            title = soup.find('title')
            product['name'] = title.get_text(strip=True) if title else f"상품_{article_idx}"

        # 2. 가격
        price_elem = soup.find(id='txt_article_price')
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price_match = re.search(r'[\d,]+', price_text)
            if price_match:
                product['price'] = int(price_match.group().replace(',', ''))

        # 3. 메인 이미지
        # viewImg 클래스의 background-image 스타일에서 추출
        view_img = soup.find(class_='viewImg')
        if view_img:
            style = view_img.get('style', '')
            img_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
            if img_match:
                product['main_image_url'] = urljoin(BASE_URL, img_match.group(1))

        # img 태그에서도 시도
        if 'main_image_url' not in product:
            main_img = soup.find('img', {'src': re.compile(r'/admin/file_data/')})
            if main_img:
                product['main_image_url'] = urljoin(BASE_URL, main_img['src'])

        # 4. 재고
        stock_elem = soup.find(id='article_stock') or soup.find(id='txt_article_stock')
        if stock_elem:
            stock_text = stock_elem.get('value', '') or stock_elem.get_text(strip=True)
            stock_match = re.search(r'\d+', stock_text)
            if stock_match:
                product['stock'] = int(stock_match.group())

        # 5. 배송비
        delivery_elem = soup.find(id='txt_article_delivery')
        if delivery_elem:
            delivery_text = delivery_elem.get_text(strip=True)
            delivery_match = re.search(r'[\d,]+', delivery_text)
            if delivery_match:
                product['delivery_fee'] = int(delivery_match.group().replace(',', ''))

        # 6. 상품 설명 (상세 영역의 텍스트 및 이미지 - 순서 유지)
        # vw_content 클래스에서 상세 콘텐츠 찾기
        detail_section = soup.find(class_='vw_content')

        # 폴백: 다른 가능한 선택자들
        if not detail_section:
            detail_section = soup.find(class_='productDetail') or soup.find(class_='goods_view')

        if detail_section:
            # 텍스트와 이미지를 순서대로 추출 (HTML 서식 보존)
            detail_content = []
            detail_images = []

            def _append_text(text):
                """텍스트를 detail_content에 추가 (연속 텍스트는 병합)"""
                if detail_content and detail_content[-1]['type'] == 'text':
                    detail_content[-1]['content'] += text
                else:
                    detail_content.append({'type': 'text', 'content': text})

            def extract_content(element):
                """재귀적으로 텍스트와 이미지 추출 (HTML 서식 보존)"""
                for child in element.children:
                    if child.name == 'img':
                        img_src = child.get('src', '')
                        if img_src:
                            full_url = urljoin(BASE_URL, img_src)
                            detail_content.append({'type': 'image', 'url': full_url})
                            if full_url not in detail_images:
                                detail_images.append(full_url)
                    elif child.name == 'br':
                        # <br> 태그 → 줄바꿈 보존
                        _append_text('\n')
                        # html.parser가 <br> 안에 후속 콘텐츠를 넣는 경우 재귀 탐색
                        if list(child.children):
                            extract_content(child)
                    elif child.name is not None:
                        # 이미지가 포함된 요소는 재귀 탐색
                        if child.find('img'):
                            extract_content(child)
                        else:
                            # 이미지 없는 요소 → HTML 서식 보존하여 캡처
                            cleaned, plain = sanitize_html(str(child))
                            if plain:
                                _append_text(cleaned)
                    else:
                        # 텍스트 노드
                        text = str(child).strip()
                        if text:
                            _append_text(text)

            extract_content(detail_section)

            # 빈 텍스트 제거 및 정리 + 원판매자 카카오 URL → 우리 URL 교체
            SELLER_KAKAO_URL = "https://open.kakao.com/o/gF7nJ96h"
            OUR_KAKAO_URL = "https://open.kakao.com/o/sNgjJoBb"
            for item in detail_content:
                if item['type'] == 'text':
                    item['content'] = item['content'].replace(SELLER_KAKAO_URL, OUR_KAKAO_URL)
            detail_content = [
                item for item in detail_content
                if item['type'] == 'image' or (item['type'] == 'text' and item['content'].strip())
            ]

            product['detail_content'] = detail_content
            product['detail_images'] = detail_images
            # description: HTML → 텍스트 (원본 줄바꿈/공백 보존)
            desc_html = str(detail_section)
            desc_text = re.sub(r'<img[^>]*/?>', '', desc_html)        # 이미지 제거
            desc_text = re.sub(r'<br\s*/?>', '\n', desc_text)         # <br> → 줄바꿈
            desc_text = re.sub(r'</(p|div|li|h[1-6])>', '\n', desc_text)  # 블록 태그 경계
            desc_text = re.sub(r'<[^>]+>', '', desc_text)             # 나머지 태그 제거
            desc_text = html_mod.unescape(desc_text)                  # HTML 엔티티 디코드
            desc_text = '\n'.join(line.strip() for line in desc_text.split('\n'))
            desc_text = re.sub(r'\n{4,}', '\n\n\n', desc_text)       # 과도한 빈 줄 정리
            desc_text = desc_text.replace(SELLER_KAKAO_URL, OUR_KAKAO_URL)  # 원판매자 → 우리 카카오 URL 교체
            product['description'] = desc_text.strip()[:5000]

        # 7. 옵션 정보
        option_select = soup.find('select', id='goods_idx')
        if option_select:
            options = []
            for option in option_select.find_all('option'):
                opt_text = option.get_text(strip=True)
                opt_value = option.get('value', '')
                if opt_value:
                    options.append({'value': opt_value, 'text': opt_text})
            product['options'] = options

        return product

    def download_image(self, url: str, article_idx: int, image_type: str = 'main', order: int = 0) -> Optional[str]:
        """이미지 다운로드 및 로컬 저장"""
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()

            # 파일 확장자 추출
            parsed_url = urlparse(url)
            ext = parsed_url.path.split('.')[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                ext = 'jpg'

            # 파일명 생성
            filename = f"{article_idx}_{image_type}_{order}.{ext}"
            filepath = IMAGES_DIR / filename

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return str(filepath)

        except Exception as e:
            print(f"Image download failed: {url} - {e}")
            return None

    def save_product(self, product_data: Dict[str, Any], category: Category) -> Optional[Product]:
        """상품 정보를 데이터베이스에 저장"""
        if not self.db_session:
            self.db_session = get_session()

        now = datetime.now()

        # 기존 상품 확인
        existing = self.db_session.query(Product).filter_by(
            article_idx=product_data['article_idx']
        ).first()

        if existing:
            # 업데이트
            existing.name = product_data.get('name', existing.name)
            existing.price = product_data.get('price', existing.price)
            existing.stock = product_data.get('stock', existing.stock)
            existing.delivery_fee = product_data.get('delivery_fee', existing.delivery_fee)
            existing.description = product_data.get('description', existing.description)
            existing.main_image_url = product_data.get('main_image_url', existing.main_image_url)
            existing.main_image_local = product_data.get('main_image_local', existing.main_image_local)
            existing.detail_images = json.dumps(product_data.get('detail_images', []), ensure_ascii=False)
            existing.detail_content = json.dumps(product_data.get('detail_content', []), ensure_ascii=False)
            existing.options = json.dumps(product_data.get('options', []), ensure_ascii=False)
            existing.updated_at = now
            existing.is_active = True
            existing.last_seen_at = now
            product = existing
        else:
            # 새로 생성
            product = Product(
                article_idx=product_data['article_idx'],
                name=product_data.get('name', ''),
                price=product_data.get('price', 0),
                stock=product_data.get('stock', 0),
                delivery_fee=product_data.get('delivery_fee', 0),
                description=product_data.get('description', ''),
                main_image_url=product_data.get('main_image_url', ''),
                main_image_local=product_data.get('main_image_local', ''),
                detail_images=json.dumps(product_data.get('detail_images', []), ensure_ascii=False),
                detail_content=json.dumps(product_data.get('detail_content', []), ensure_ascii=False),
                options=json.dumps(product_data.get('options', []), ensure_ascii=False),
                source_url=product_data.get('source_url', ''),
                category=category,
                is_active=True,
                last_seen_at=now
            )
            self.db_session.add(product)

        self.db_session.commit()
        return product

    def init_categories(self):
        """카테고리 초기화"""
        if not self.db_session:
            self.db_session = get_session()

        for code, name in CATEGORIES.items():
            existing = self.db_session.query(Category).filter_by(code=code).first()
            if not existing:
                category = Category(code=code, name=name)
                self.db_session.add(category)

        self.db_session.commit()
        print("Categories initialized")

    def crawl_category(self, category_code: str, download_images: bool = True) -> Dict[str, int]:
        """특정 카테고리 전체 크롤링"""
        if not self.db_session:
            self.db_session = get_session()

        category = self.db_session.query(Category).filter_by(code=category_code).first()
        if not category:
            print(f"Category {category_code} not found!")
            return {'success': 0, 'fail': 0}

        # 크롤링 로그 시작
        log = CrawlLog(category_code=category_code, status='running')
        self.db_session.add(log)
        self.db_session.commit()

        results = {'success': 0, 'fail': 0}

        try:
            # 상품 목록 가져오기
            product_list = self.get_product_list(category_code)
            log.total_products = len(product_list)

            # 각 상품 상세 정보 크롤링
            for item in tqdm(product_list, desc=f"Crawling {category.name}"):
                self._random_delay()

                try:
                    product_data = self.get_product_detail(item['article_idx'])
                    if not product_data:
                        results['fail'] += 1
                        continue

                    # 이미지 다운로드
                    if download_images and product_data.get('main_image_url'):
                        local_path = self.download_image(
                            product_data['main_image_url'],
                            product_data['article_idx'],
                            'main'
                        )
                        if local_path:
                            product_data['main_image_local'] = local_path

                        # 상세 이미지도 다운로드
                        for i, img_url in enumerate(product_data.get('detail_images', [])):
                            self.download_image(
                                img_url,
                                product_data['article_idx'],
                                'detail',
                                i
                            )

                    # DB 저장
                    self.save_product(product_data, category)
                    results['success'] += 1

                except Exception as e:
                    log_event('warning', 'crawl', f"상품 {item['article_idx']} 크롤링 실패: {e}", related_id=str(item['article_idx']))
                    results['fail'] += 1

            # 로그 완료
            log.success_count = results['success']
            log.fail_count = results['fail']
            log.finished_at = datetime.now()
            log.status = 'completed'

        except Exception as e:
            log.status = 'failed'
            log.error_message = str(e)
            log_event('error', 'crawl', f"카테고리 {category_code} 크롤링 실패: {e}")
            raise

        finally:
            self.db_session.commit()

        return results

    def fetch_admin_mapping(self) -> Dict[int, Dict[str, Any]]:
        """Admin js_article.asp에서 상품 매핑 데이터 가져오기"""
        print("\n[Admin Sync] Fetching js_article.asp...")

        # Admin 로그인
        admin_session = requests.Session()
        admin_session.headers.update({'User-Agent': 'Mozilla/5.0'})
        login_resp = admin_session.post(
            f"{ADMIN_BASE_URL}/m/include/asp/login_ok.asp",
            data={"m_id": ADMIN_ID, "m_passwd": ADMIN_PW}
        )
        if login_resp.status_code != 200:
            log_event('error', 'admin_sync', f"Admin 로그인 실패: HTTP {login_resp.status_code}")
            raise Exception(f"Admin 로그인 실패: HTTP {login_resp.status_code}")

        # js_article.asp 가져오기
        resp = admin_session.get(f"{ADMIN_BASE_URL}/include/js/js_article.asp")
        if resp.status_code != 200:
            log_event('error', 'admin_sync', f"js_article.asp 조회 실패: HTTP {resp.status_code}")
            raise Exception(f"js_article.asp 조회 실패: HTTP {resp.status_code}")
        content = resp.content.decode('euc-kr', errors='ignore')

        # JavaScript 배열 파싱
        idx_pattern = r"j_article_idx\[(\d+)\]\s*=\s*'(\d+)'"
        cate_pattern = r"j_cate_idx\[(\d+)\]\s*=\s*'(\d+)'"
        price_pattern = r"j_article_price\[(\d+)\]\s*=\s*'(\d+)'"
        stock_pattern = r"j_article_stock\[(\d+)\]\s*=\s*'(\d+)'"
        delivery_pattern = r"j_article_delivery\[(\d+)\]\s*=\s*'(\d+)'"
        sell_d_pattern = r"j_article_sell_d\[(\d+)\]\s*=\s*'(\d+)'"
        sell_s_pattern = r"j_article_sell_s\[(\d+)\]\s*=\s*'(\d+)'"

        # 인덱스별로 데이터 수집
        raw_data = {}
        for pattern, key in [
            (idx_pattern, 'article_idx'),
            (cate_pattern, 'cate_idx'),
            (price_pattern, 'price'),
            (stock_pattern, 'stock'),
            (delivery_pattern, 'delivery'),
            (sell_d_pattern, 'sell_d'),
            (sell_s_pattern, 'sell_s'),
        ]:
            for m in re.finditer(pattern, content):
                i = int(m.group(1))
                raw_data.setdefault(i, {})[key] = m.group(2)

        # article_idx 기준으로 변환
        mappings = {}
        for item in raw_data.values():
            if 'article_idx' in item:
                aid = int(item['article_idx'])
                mappings[aid] = {
                    'admin_category_idx': item.get('cate_idx'),
                    'admin_price': int(item['price']) if 'price' in item else None,
                    'admin_stock': int(item['stock']) if 'stock' in item else None,
                    'admin_delivery_fee': int(item['delivery']) if 'delivery' in item else None,
                }

        admin_session.close()
        print(f"[Admin Sync] {len(mappings)} products fetched from Admin")
        return mappings

    def sync_admin_data(self, mappings: Dict[int, Dict[str, Any]]) -> Dict[str, int]:
        """Admin 매핑 데이터를 DB에 저장 + Admin에 없는 상품 비활성화"""
        if not self.db_session:
            self.db_session = get_session()

        synced = 0
        not_found = 0
        admin_deactivated = 0
        now = datetime.now()

        # 1. Admin에 있는 상품 동기화
        for article_idx, admin_data in mappings.items():
            product = self.db_session.query(Product).filter_by(
                article_idx=article_idx
            ).first()

            if product:
                product.admin_category_idx = admin_data.get('admin_category_idx')
                product.admin_price = admin_data.get('admin_price')
                product.admin_stock = admin_data.get('admin_stock')
                product.admin_delivery_fee = admin_data.get('admin_delivery_fee')
                product.admin_synced_at = now
                synced += 1
            else:
                not_found += 1

        # 2. DB에 활성인데 Admin 드롭다운에 없는 상품 → 비활성화
        admin_article_ids = set(mappings.keys())
        active_products = self.db_session.query(Product).filter(
            Product.is_active == True
        ).all()

        admin_deactivated_ids = []
        for product in active_products:
            if product.article_idx not in admin_article_ids:
                product.is_active = False
                admin_deactivated += 1
                admin_deactivated_ids.append(product.article_idx)
                print(f"  [Admin] 비활성화: {product.article_idx} - {product.name[:30]}")

        self.db_session.commit()

        log_msg = f"Admin 동기화 완료: {synced}개 동기화, {not_found}개 DB 미발견, {admin_deactivated}개 비활성화"
        if admin_deactivated > 0:
            log_event('warning', 'admin_sync', log_msg)
        else:
            log_event('info', 'admin_sync', log_msg)
        return {'synced': synced, 'not_found': not_found, 'admin_deactivated': admin_deactivated, 'admin_deactivated_ids': admin_deactivated_ids}

    def deactivate_missing_products(self, crawl_started_at: datetime) -> Dict[str, Any]:
        """이번 크롤링에서 발견되지 않은 상품을 비활성화 (안전장치 포함)"""
        if not self.db_session:
            self.db_session = get_session()

        # last_seen_at이 이번 크롤링 시작 시간보다 이전인 활성 상품 = 사라진 상품
        stale_products = self.db_session.query(Product).filter(
            Product.is_active == True,
            (Product.last_seen_at == None) | (Product.last_seen_at < crawl_started_at)
        ).all()

        # 안전장치: 50% 이상 비활성화 대상이면 크롤링 오류 가능성 → 스킵
        total_active = self.db_session.query(Product).filter(Product.is_active == True).count()
        if total_active > 0 and len(stale_products) > total_active * 0.5:
            log_event('error', 'crawl',
                f"비활성화 스킵: {len(stale_products)}/{total_active}개 대상 (50% 초과) — 크롤링 오류 또는 IP 차단 가능성")
            return {'deactivated': 0, 'deactivated_ids': [], 'skipped_safety': True}

        deactivated = 0
        deactivated_ids = []
        for product in stale_products:
            product.is_active = False
            deactivated += 1
            deactivated_ids.append(product.article_idx)

        self.db_session.commit()
        if deactivated > 0:
            log_event('warning', 'crawl', f"os79 미발견으로 {deactivated}개 상품 비활성화")
        else:
            log_event('info', 'crawl', "비활성화 대상 상품 없음 (모든 상품 정상)")
        return {'deactivated': deactivated, 'deactivated_ids': deactivated_ids}

    def notify_out_of_stock_orders(self, deactivated_article_ids: Set[int]) -> Dict[str, int]:
        """비활성화된 상품을 포함한 미결제 주문에 품절 SMS 발송

        입금 완료(paid) 이후 단계는 이미 처리된 주문이므로 제외.
        processing(주문 확인), awaiting_payment(입금 대기) 단계만 대상.
        """
        if not deactivated_article_ids:
            return {'notified': 0, 'skipped': 0}

        if not self.db_session:
            self.db_session = get_session()

        # 미결제 단계 + 품절 미통보 + 비활성화 상품 포함 주문 조회
        affected_orders = (
            self.db_session.query(Order)
            .options(joinedload(Order.items))
            .join(OrderItem)
            .filter(
                Order.status.in_(['processing', 'awaiting_payment']),
                Order.oos_notified_at == None,
                OrderItem.article_idx.in_(deactivated_article_ids)
            )
            .all()
        )

        notified = 0
        skipped = 0

        for order in affected_orders:
            unavailable_items = [
                item.product_name
                for item in order.items
                if item.article_idx in deactivated_article_ids
            ]

            if not unavailable_items:
                skipped += 1
                continue

            try:
                result = send_out_of_stock_sms(order, unavailable_items)
                if result.get('success'):
                    order.oos_notified_at = datetime.now()
                    order.status = 'out_of_stock'
                    self.db_session.commit()
                    notified += 1
                    log_event('info', 'sms',
                        f"품절 SMS 발송: {order.order_number} - 품절상품: {', '.join(unavailable_items)}",
                        related_id=order.order_number)
                else:
                    log_event('error', 'sms',
                        f"품절 SMS 발송 실패: {order.order_number} - {result.get('message', '')}",
                        related_id=order.order_number)
                    skipped += 1
            except Exception as e:
                log_event('error', 'sms',
                    f"품절 SMS 예외: {order.order_number} - {e}",
                    related_id=order.order_number)
                skipped += 1

        if notified > 0:
            log_event('warning', 'crawl', f"품절 알림 발송: {notified}건 발송, {skipped}건 스킵")

        return {'notified': notified, 'skipped': skipped}

    def crawl_all(self, download_images: bool = True) -> Dict[str, Dict[str, int]]:
        """모든 카테고리 크롤링"""
        # DB 초기화
        init_db()
        self.db_session = get_session()
        self.init_categories()

        crawl_started_at = datetime.now()
        all_results = {}

        for code in CATEGORIES.keys():
            print(f"\n{'='*50}")
            print(f"Starting category: {CATEGORIES[code]} ({code})")
            print(f"{'='*50}")

            results = self.crawl_category(code, download_images)
            all_results[code] = results

            print(f"\nCategory {code} completed: {results['success']} success, {results['fail']} fail")

        # 사라진 상품 비활성화
        deactivate_result = self.deactivate_missing_products(crawl_started_at)
        all_results['deactivated'] = deactivate_result
        all_deactivated_ids = set(deactivate_result.get('deactivated_ids', []))

        # Admin 데이터 동기화
        try:
            admin_mappings = self.fetch_admin_mapping()
            sync_result = self.sync_admin_data(admin_mappings)
            all_results['admin_sync'] = sync_result
            all_deactivated_ids.update(sync_result.get('admin_deactivated_ids', []))
        except Exception as e:
            log_event('error', 'admin_sync', f"Admin 동기화 실패: {e}", detail=str(e))
            all_results['admin_sync'] = {'error': str(e)}

        # 품절 안내 SMS 발송 (입금 완료 주문 대상)
        if all_deactivated_ids:
            oos_result = self.notify_out_of_stock_orders(all_deactivated_ids)
            all_results['oos_notifications'] = oos_result

        # 텔레그램 크롤링 완료 알림
        try:
            from telegram_bot import send_message
            total_success = sum(r.get('success', 0) for c, r in all_results.items() if c in CATEGORIES)
            total_fail = sum(r.get('fail', 0) for c, r in all_results.items() if c in CATEGORIES)
            deactivated = len(all_deactivated_ids)
            elapsed = (datetime.now() - crawl_started_at).total_seconds()
            msg = f"[크롤링 완료] {total_success}개 성공"
            if total_fail:
                msg += f", {total_fail}개 실패"
            if deactivated:
                msg += f", {deactivated}개 비활성화"
            msg += f" ({elapsed:.0f}초)"
            send_message(msg)
        except Exception:
            pass

        return all_results

    def close(self):
        """리소스 정리"""
        if self.db_session:
            self.db_session.close()
        self.session.close()


if __name__ == "__main__":
    # 테스트: 과일 카테고리만 크롤링
    crawler = OS79Crawler()
    try:
        init_db()
        crawler.db_session = get_session()
        crawler.init_categories()

        # 단일 상품 테스트
        print("\n[Test] Single product crawl:")
        product = crawler.get_product_detail(42009)
        if product:
            print(f"Name: {product.get('name')}")
            print(f"Price: {product.get('price')}")
            print(f"Image: {product.get('main_image_url')}")
    finally:
        crawler.close()
