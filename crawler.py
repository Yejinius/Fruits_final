"""
OS79.co.kr 크롤러 핵심 로직
"""
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from typing import Optional, Dict, List, Any
from tqdm import tqdm

from config import (
    BASE_URL, GOODS_LIST_URL, GOODS_VIEW_URL,
    CATEGORIES, HEADERS, REQUEST_DELAY, REQUEST_TIMEOUT, MAX_RETRIES, IMAGES_DIR
)
from models import (
    init_db, get_session,
    Category, Product, ProductImage, CrawlLog
)


class OS79Crawler:
    """OS79 사이트 크롤러"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.db_session = None

    def _request(self, url: str, retries: int = MAX_RETRIES) -> Optional[requests.Response]:
        """HTTP 요청 with 재시도 로직"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                # 인코딩 처리 (EUC-KR 사이트)
                response.encoding = response.apparent_encoding or 'euc-kr'
                return response
            except requests.RequestException as e:
                print(f"[Attempt {attempt + 1}/{retries}] Request failed: {url} - {e}")
                if attempt < retries - 1:
                    time.sleep(REQUEST_DELAY * 2)
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
            # 텍스트와 이미지를 순서대로 추출
            detail_content = []
            detail_images = []

            def extract_content(element):
                """재귀적으로 텍스트와 이미지 추출"""
                for child in element.children:
                    if child.name == 'img':
                        img_src = child.get('src', '')
                        if img_src:
                            full_url = urljoin(BASE_URL, img_src)
                            detail_content.append({'type': 'image', 'url': full_url})
                            if full_url not in detail_images:
                                detail_images.append(full_url)
                    elif child.name is not None:
                        # 하위 요소 재귀 탐색 (br 포함 모든 태그)
                        extract_content(child)
                    else:
                        # 텍스트 노드
                        text = str(child).strip()
                        if text:
                            # 이전 항목이 텍스트면 합치기
                            if detail_content and detail_content[-1]['type'] == 'text':
                                detail_content[-1]['content'] += '\n' + text
                            else:
                                detail_content.append({'type': 'text', 'content': text})

            extract_content(detail_section)

            # 빈 텍스트 제거 및 정리
            detail_content = [
                item for item in detail_content
                if item['type'] == 'image' or (item['type'] == 'text' and item['content'].strip())
            ]

            product['detail_content'] = detail_content
            product['detail_images'] = detail_images
            # description은 전체 텍스트만 추출
            product['description'] = detail_section.get_text(separator='\n', strip=True)[:5000]

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
            existing.updated_at = datetime.now()
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
                category=category
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
                time.sleep(REQUEST_DELAY)

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
                    print(f"Error processing product {item['article_idx']}: {e}")
                    results['fail'] += 1

            # 로그 완료
            log.success_count = results['success']
            log.fail_count = results['fail']
            log.finished_at = datetime.now()
            log.status = 'completed'

        except Exception as e:
            log.status = 'failed'
            log.error_message = str(e)
            raise

        finally:
            self.db_session.commit()

        return results

    def crawl_all(self, download_images: bool = True) -> Dict[str, Dict[str, int]]:
        """모든 카테고리 크롤링"""
        # DB 초기화
        init_db()
        self.db_session = get_session()
        self.init_categories()

        all_results = {}
        for code in CATEGORIES.keys():
            print(f"\n{'='*50}")
            print(f"Starting category: {CATEGORIES[code]} ({code})")
            print(f"{'='*50}")

            results = self.crawl_category(code, download_images)
            all_results[code] = results

            print(f"\nCategory {code} completed: {results['success']} success, {results['fail']} fail")

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
