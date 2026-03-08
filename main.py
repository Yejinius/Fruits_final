"""
OS79 크롤러 메인 실행 파일
"""
import argparse
from crawler import OS79Crawler
from models import init_db, get_session, Product, Category
from config import CATEGORIES, BAND_PREVIEW_URL, BAND_PRODUCTION_URL


def show_stats():
    """현재 DB 통계 출력"""
    session = get_session()

    print("\n" + "=" * 50)
    print("📊 현재 데이터베이스 현황")
    print("=" * 50)

    total = session.query(Product).count()
    print(f"\n총 상품 수: {total}개")

    print("\n카테고리별 상품 수:")
    for code, name in CATEGORIES.items():
        category = session.query(Category).filter_by(code=code).first()
        if category:
            count = session.query(Product).filter_by(category_id=category.id).count()
            print(f"  - {name}: {count}개")

    session.close()


def crawl_single(article_idx: int):
    """단일 상품 크롤링"""
    crawler = OS79Crawler()
    try:
        init_db()
        crawler.db_session = get_session()
        crawler.init_categories()

        print(f"\n상품 {article_idx} 크롤링 중...")
        product = crawler.get_product_detail(article_idx)

        if product:
            print(f"\n✅ 크롤링 성공!")
            print(f"  상품명: {product.get('name')}")
            print(f"  가격: {product.get('price', 0):,}원")
            print(f"  재고: {product.get('stock', 0)}개")
            print(f"  배송비: {product.get('delivery_fee', 0):,}원")
            print(f"  이미지: {product.get('main_image_url', 'N/A')}")
            print(f"  옵션: {len(product.get('options', []))}개")
        else:
            print(f"❌ 상품을 찾을 수 없습니다.")

    finally:
        crawler.close()


def crawl_category(code: str, download_images: bool = True):
    """특정 카테고리 크롤링"""
    if code not in CATEGORIES:
        print(f"❌ 잘못된 카테고리 코드: {code}")
        print(f"사용 가능한 코드: {', '.join(CATEGORIES.keys())}")
        return

    crawler = OS79Crawler()
    try:
        init_db()
        crawler.db_session = get_session()
        crawler.init_categories()

        print(f"\n카테고리 '{CATEGORIES[code]}' 크롤링 시작...")
        results = crawler.crawl_category(code, download_images)

        print(f"\n✅ 완료!")
        print(f"  성공: {results['success']}개")
        print(f"  실패: {results['fail']}개")

    finally:
        crawler.close()


def crawl_all(download_images: bool = True):
    """전체 카테고리 크롤링"""
    crawler = OS79Crawler()
    try:
        print("\n🚀 전체 상품 크롤링 시작!")
        print("=" * 50)

        results = crawler.crawl_all(download_images)

        print("\n" + "=" * 50)
        print("📊 최종 결과")
        print("=" * 50)

        total_success = 0
        total_fail = 0

        for code, result in results.items():
            if code in CATEGORIES:
                print(f"  {CATEGORIES[code]}: 성공 {result['success']}, 실패 {result['fail']}")
                total_success += result['success']
                total_fail += result['fail']

        print(f"\n총계: 성공 {total_success}개, 실패 {total_fail}개")

    finally:
        crawler.close()


def main():
    parser = argparse.ArgumentParser(description='OS79.co.kr 상품 크롤러')

    subparsers = parser.add_subparsers(dest='command', help='실행할 명령')

    # 전체 크롤링
    all_parser = subparsers.add_parser('all', help='모든 카테고리 크롤링')
    all_parser.add_argument('--no-images', action='store_true', help='이미지 다운로드 건너뛰기')

    # 카테고리 크롤링
    cat_parser = subparsers.add_parser('category', help='특정 카테고리 크롤링')
    cat_parser.add_argument('code', help=f'카테고리 코드 ({", ".join(CATEGORIES.keys())})')
    cat_parser.add_argument('--no-images', action='store_true', help='이미지 다운로드 건너뛰기')

    # 단일 상품 크롤링
    single_parser = subparsers.add_parser('single', help='단일 상품 크롤링 (테스트용)')
    single_parser.add_argument('article_idx', type=int, help='상품 ID')

    # 통계 보기
    subparsers.add_parser('stats', help='현재 DB 통계 보기')

    # 밴드 Chrome 시작 (상시 실행)
    subparsers.add_parser('band-chrome', help='밴드용 Chrome 상시 실행 시작')

    # 밴드 로그인
    subparsers.add_parser('band-login', help='네이버 밴드 로그인 (Chrome 상시 실행 모드)')

    # 밴드 포스팅
    band_post_parser = subparsers.add_parser('band-post', help='밴드에 상품 게시물 올리기')
    band_post_parser.add_argument('article_idx', type=int, help='상품 ID')
    band_post_parser.add_argument('--band-url', help='밴드 URL (미지정 시 config.py 사용)')

    # 밴드 카테고리 전체 포스팅
    band_cat_parser = subparsers.add_parser('band-post-category', help='카테고리 전체 상품 밴드 포스팅')
    band_cat_parser.add_argument('code', help=f'카테고리 코드 ({", ".join(CATEGORIES.keys())})')
    band_cat_parser.add_argument('--band-url', help='밴드 URL (미지정 시 config.py 사용)')

    # ── Incremental 밴드 포스팅 ──
    # 미게시 상품 리스트
    band_new_parser = subparsers.add_parser('band-new', help='밴드 미게시 상품 리스트')
    band_new_parser.add_argument('--category', help=f'카테고리 필터 ({", ".join(CATEGORIES.keys())})')

    # 단일 상품 테스트 밴드 미리보기
    band_preview_parser = subparsers.add_parser('band-preview', help='테스트 밴드에 미리보기 게시')
    band_preview_parser.add_argument('article_idx', type=int, help='상품 ID')

    # 미게시 전체 테스트 밴드 미리보기
    band_preview_all_parser = subparsers.add_parser('band-preview-all', help='미게시 전체 상품 테스트 밴드 미리보기')
    band_preview_all_parser.add_argument('--category', help=f'카테고리 필터 ({", ".join(CATEGORIES.keys())})')

    # 승인 → 본 밴드 게시
    band_confirm_parser = subparsers.add_parser('band-confirm', help='승인된 상품 본 밴드에 게시')
    band_confirm_parser.add_argument('article_idx', type=int, help='상품 ID')

    # ── Telegram Bot ──
    subparsers.add_parser('bot', help='텔레그램 봇 서버 실행')
    subparsers.add_parser('bot-test', help='텔레그램 테스트 알림 전송')

    args = parser.parse_args()

    if args.command == 'all':
        crawl_all(download_images=not args.no_images)
    elif args.command == 'category':
        crawl_category(args.code, download_images=not args.no_images)
    elif args.command == 'single':
        crawl_single(args.article_idx)
    elif args.command == 'stats':
        init_db()
        show_stats()
    elif args.command == 'band-chrome':
        from band_poster import start_persistent_chrome
        start_persistent_chrome()
    elif args.command == 'band-login':
        from band_poster import band_login
        band_login()
    elif args.command == 'band-post':
        from band_poster import band_post
        band_post(args.article_idx, band_url=getattr(args, 'band_url', None))
    elif args.command == 'band-post-category':
        from band_poster import band_post_category
        band_post_category(args.code, band_url=getattr(args, 'band_url', None))
    elif args.command == 'band-new':
        from band_poster import band_show_new
        band_show_new(category_code=getattr(args, 'category', None))
    elif args.command == 'band-preview':
        from band_poster import band_post_preview
        band_post_preview(args.article_idx)
    elif args.command == 'band-preview-all':
        from band_poster import band_post_preview_all
        band_post_preview_all(category_code=getattr(args, 'category', None))
    elif args.command == 'band-confirm':
        from band_poster import band_post_confirm
        band_post_confirm(args.article_idx)
    elif args.command == 'bot':
        from telegram_bot import TelegramBotServer
        print("YoungfreshBot 시작 (Ctrl+C로 종료)")
        bot = TelegramBotServer()
        try:
            bot.start()
        except KeyboardInterrupt:
            print("\n봇 종료")
    elif args.command == 'bot-test':
        from telegram_bot import send_test_alert
        send_test_alert()
    else:
        parser.print_help()
        print("\n카테고리 코드:")
        for code, name in CATEGORIES.items():
            print(f"  {code}: {name}")


if __name__ == "__main__":
    main()
