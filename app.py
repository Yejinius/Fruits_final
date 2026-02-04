"""
Young Fresh Mall - 과일 공동구매 쇼핑몰
"""
import json
from flask import Flask, render_template_string, request
from sqlalchemy.orm import joinedload
from models import get_session, Product, Category
from config import CATEGORIES

app = Flask(__name__)

# 공통 스타일
COMMON_STYLES = """
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
        --primary: #2E7D32;
        --primary-light: #4CAF50;
        --primary-dark: #1B5E20;
        --accent: #FF6B35;
        --text-dark: #333;
        --text-light: #666;
        --text-muted: #999;
        --bg-white: #fff;
        --bg-light: #f8f9fa;
        --bg-gray: #f0f0f0;
        --border: #e0e0e0;
        --shadow: 0 2px 8px rgba(0,0,0,0.08);
        --shadow-hover: 0 4px 16px rgba(0,0,0,0.12);
        --radius: 12px;
        --radius-sm: 8px;
    }

    body {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: var(--bg-light);
        color: var(--text-dark);
        line-height: 1.6;
    }

    a { text-decoration: none; color: inherit; }

    .container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 0 20px;
    }

    /* Header */
    .header {
        background: var(--bg-white);
        border-bottom: 1px solid var(--border);
        position: sticky;
        top: 0;
        z-index: 100;
    }

    .header-top {
        padding: 15px 0;
        text-align: center;
        border-bottom: 1px solid var(--border);
    }

    .logo {
        font-size: 28px;
        font-weight: 800;
        color: var(--primary);
        letter-spacing: -1px;
    }

    .logo span { color: var(--accent); }

    .tagline {
        font-size: 13px;
        color: var(--text-light);
        margin-top: 4px;
    }

    /* Navigation */
    .nav {
        background: var(--bg-white);
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }

    .nav::-webkit-scrollbar { display: none; }

    .nav-list {
        display: flex;
        justify-content: center;
        list-style: none;
        gap: 5px;
        padding: 10px 0;
    }

    .nav-item a {
        display: block;
        padding: 10px 20px;
        font-size: 15px;
        font-weight: 500;
        color: var(--text-dark);
        border-radius: var(--radius-sm);
        transition: all 0.2s;
        white-space: nowrap;
    }

    .nav-item a:hover {
        background: var(--bg-light);
        color: var(--primary);
    }

    .nav-item a.active {
        background: var(--primary);
        color: white;
    }

    /* Hero Banner */
    .hero {
        background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
        color: white;
        padding: 40px 20px;
        text-align: center;
    }

    .hero h2 {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 15px;
    }

    .hero-features {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 15px;
        margin-top: 20px;
    }

    .hero-feature {
        background: rgba(255,255,255,0.15);
        padding: 12px 20px;
        border-radius: 50px;
        font-size: 13px;
        backdrop-filter: blur(10px);
    }

    /* Product Grid */
    .section-title {
        font-size: 20px;
        font-weight: 700;
        padding: 30px 0 20px;
        color: var(--text-dark);
    }

    .product-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 20px;
        padding-bottom: 40px;
    }

    .product-card {
        background: var(--bg-white);
        border-radius: var(--radius);
        overflow: hidden;
        box-shadow: var(--shadow);
        transition: all 0.3s;
        cursor: pointer;
    }

    .product-card:hover {
        transform: translateY(-5px);
        box-shadow: var(--shadow-hover);
    }

    .product-image {
        position: relative;
        padding-top: 100%;
        background: var(--bg-gray);
        overflow: hidden;
    }

    .product-image img {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
        transition: transform 0.3s;
    }

    .product-card:hover .product-image img {
        transform: scale(1.05);
    }

    .product-badge {
        position: absolute;
        top: 10px;
        left: 10px;
        background: var(--accent);
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
    }

    .product-info {
        padding: 15px;
    }

    .product-category {
        font-size: 12px;
        color: var(--primary);
        font-weight: 500;
        margin-bottom: 5px;
    }

    .product-name {
        font-size: 15px;
        font-weight: 600;
        color: var(--text-dark);
        margin-bottom: 8px;
        line-height: 1.4;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }

    .product-price {
        font-size: 20px;
        font-weight: 700;
        color: var(--text-dark);
    }

    .product-price .won {
        font-size: 14px;
        font-weight: 500;
    }

    .product-meta {
        display: flex;
        gap: 10px;
        margin-top: 10px;
        font-size: 12px;
        color: var(--text-muted);
    }

    .product-meta span {
        display: flex;
        align-items: center;
        gap: 3px;
    }

    /* Footer */
    .footer {
        background: var(--bg-white);
        border-top: 1px solid var(--border);
        padding: 30px 20px;
        text-align: center;
        color: var(--text-light);
        font-size: 13px;
    }

    /* Responsive */
    @media (max-width: 768px) {
        .logo { font-size: 22px; }
        .tagline { font-size: 11px; }
        .hero { padding: 30px 15px; }
        .hero h2 { font-size: 18px; }
        .hero-feature { font-size: 12px; padding: 10px 15px; }
        .nav-list { justify-content: flex-start; padding: 10px 15px; }
        .nav-item a { padding: 8px 15px; font-size: 14px; }
        .product-grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
        .product-info { padding: 12px; }
        .product-name { font-size: 13px; }
        .product-price { font-size: 16px; }
        .section-title { font-size: 18px; padding: 20px 0 15px; }
    }

    @media (max-width: 480px) {
        .product-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .hero-features { flex-direction: column; align-items: center; }
    }
</style>
"""

# 메인 페이지 템플릿
MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Young Fresh Mall - 실시간 경매상품 과일공동구매</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    """ + COMMON_STYLES + """
</head>
<body>
    <header class="header">
        <div class="header-top">
            <a href="/" class="logo">Young<span>Fresh</span>Mall</a>
            <p class="tagline">실시간 경매상품 과일공동구매 (이제 과일 비싸게 사지 마세요!)</p>
        </div>
        <nav class="nav">
            <ul class="nav-list">
                <li class="nav-item"><a href="/" {% if not category %}class="active"{% endif %}>전체</a></li>
                {% for code, name in categories.items() %}
                <li class="nav-item">
                    <a href="/category/{{ code }}" {% if category == code %}class="active"{% endif %}>{{ name }}</a>
                </li>
                {% endfor %}
            </ul>
        </nav>
    </header>

    {% if not category %}
    <section class="hero">
        <div class="container">
            <h2>데이터가 증명한 과일, 복불복은 이제 그만!</h2>
            <div class="hero-features">
                <div class="hero-feature">🚚 오후 5시 이전 주문 시 당일 발송</div>
                <div class="hero-feature">📊 평균 당도까지 공개하는 투명한 정보</div>
                <div class="hero-feature">✅ 생산자 확인 + 당도 확인 = 실패 없는 과일</div>
            </div>
        </div>
    </section>
    {% endif %}

    <main class="container">
        <h3 class="section-title">
            {% if category %}
                {{ categories.get(category, '전체') }}
                <span style="font-weight:400; font-size:14px; color:#999;">({{ products|length }}개)</span>
            {% else %}
                오늘의 추천 상품
                <span style="font-weight:400; font-size:14px; color:#999;">({{ products|length }}개)</span>
            {% endif %}
        </h3>

        <div class="product-grid">
            {% for product in products %}
            <a href="/product/{{ product.article_idx }}" class="product-card">
                <div class="product-image">
                    {% if product.main_image_url %}
                    <img src="{{ product.main_image_url }}" alt="{{ product.name }}" loading="lazy">
                    {% endif %}
                    {% if product.stock and product.stock > 0 and product.stock < 50 %}
                    <div class="product-badge">품절임박</div>
                    {% endif %}
                </div>
                <div class="product-info">
                    <p class="product-category">{{ product.category.name if product.category else '' }}</p>
                    <h4 class="product-name">{{ product.name }}</h4>
                    <p class="product-price">{{ "{:,}".format(product.price or 0) }}<span class="won">원</span></p>
                    <div class="product-meta">
                        {% if product.delivery_fee %}
                        <span>🚚 배송비 {{ "{:,}".format(product.delivery_fee) }}원</span>
                        {% else %}
                        <span>🚚 무료배송</span>
                        {% endif %}
                    </div>
                </div>
            </a>
            {% endfor %}
        </div>
    </main>

    <footer class="footer">
        <p>© 2026 Young Fresh Mall. All rights reserved.</p>
        <p style="margin-top:5px;">고객센터: 1234-5678 | 평일 09:00 - 18:00</p>
    </footer>
</body>
</html>
"""

# 상세 페이지 템플릿
DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ product.name }} - Young Fresh Mall</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    """ + COMMON_STYLES + """
    <style>
        .detail-container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }

        .breadcrumb {
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 20px;
        }

        .breadcrumb a { color: var(--primary); }

        .product-detail {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            background: var(--bg-white);
            border-radius: var(--radius);
            padding: 30px;
            box-shadow: var(--shadow);
        }

        .detail-image {
            position: relative;
            border-radius: var(--radius-sm);
            overflow: hidden;
            background: var(--bg-gray);
        }

        .detail-image img {
            width: 100%;
            display: block;
        }

        .detail-info h1 {
            font-size: 24px;
            font-weight: 700;
            line-height: 1.4;
            margin-bottom: 15px;
            color: var(--text-dark);
        }

        .detail-category {
            display: inline-block;
            background: var(--bg-light);
            color: var(--primary);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
            margin-bottom: 15px;
        }

        .detail-price {
            font-size: 32px;
            font-weight: 800;
            color: var(--text-dark);
            margin: 20px 0;
        }

        .detail-price .won {
            font-size: 20px;
            font-weight: 500;
        }

        .detail-meta {
            background: var(--bg-light);
            border-radius: var(--radius-sm);
            padding: 20px;
            margin: 20px 0;
        }

        .meta-row {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }

        .meta-row:last-child { border-bottom: none; }
        .meta-label { color: var(--text-light); }
        .meta-value { font-weight: 600; color: var(--text-dark); }

        /* Option Dropdown */
        .option-section {
            margin: 20px 0;
        }

        .option-label {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-dark);
            margin-bottom: 8px;
        }

        .option-select {
            width: 100%;
            padding: 15px;
            font-size: 15px;
            border: 2px solid var(--border);
            border-radius: var(--radius-sm);
            background: var(--bg-white);
            color: var(--text-dark);
            cursor: pointer;
            transition: border-color 0.2s;
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23666' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 15px center;
        }

        .option-select:focus {
            outline: none;
            border-color: var(--primary);
        }

        .buy-button {
            width: 100%;
            padding: 18px;
            font-size: 18px;
            font-weight: 700;
            color: white;
            background: var(--primary);
            border: none;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: background 0.2s;
            margin-top: 15px;
        }

        .buy-button:hover {
            background: var(--primary-dark);
        }

        .cart-button {
            width: 100%;
            padding: 18px;
            font-size: 16px;
            font-weight: 600;
            color: var(--primary);
            background: var(--bg-white);
            border: 2px solid var(--primary);
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: all 0.2s;
            margin-top: 10px;
        }

        .cart-button:hover {
            background: var(--bg-light);
        }

        /* Content Section */
        .content-section {
            background: var(--bg-white);
            border-radius: var(--radius);
            padding: 30px;
            margin-top: 30px;
            box-shadow: var(--shadow);
        }

        .content-section h2 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 2px solid var(--primary);
            color: var(--text-dark);
        }

        .detail-content .text-block {
            background: var(--bg-light);
            padding: 20px;
            border-radius: var(--radius-sm);
            margin: 15px 0;
            font-size: 15px;
            line-height: 1.8;
            white-space: pre-wrap;
            color: var(--text-dark);
        }

        .detail-content .image-block {
            margin: 20px 0;
            text-align: center;
        }

        .detail-content .image-block img {
            max-width: 100%;
            border-radius: var(--radius-sm);
            box-shadow: var(--shadow);
        }

        /* Responsive */
        @media (max-width: 768px) {
            .product-detail {
                grid-template-columns: 1fr;
                gap: 20px;
                padding: 20px;
            }

            .detail-info h1 { font-size: 20px; }
            .detail-price { font-size: 26px; }
            .content-section { padding: 20px; }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-top">
            <a href="/" class="logo">Young<span>Fresh</span>Mall</a>
            <p class="tagline">실시간 경매상품 과일공동구매 (이제 과일 비싸게 사지 마세요!)</p>
        </div>
        <nav class="nav">
            <ul class="nav-list">
                <li class="nav-item"><a href="/">전체</a></li>
                {% for code, name in categories.items() %}
                <li class="nav-item">
                    <a href="/category/{{ code }}" {% if product.category and product.category.code == code %}class="active"{% endif %}>{{ name }}</a>
                </li>
                {% endfor %}
            </ul>
        </nav>
    </header>

    <main class="detail-container">
        <div class="breadcrumb">
            <a href="/">홈</a> &gt;
            {% if product.category %}
            <a href="/category/{{ product.category.code }}">{{ product.category.name }}</a> &gt;
            {% endif %}
            {{ product.name[:30] }}...
        </div>

        <div class="product-detail">
            <div class="detail-image">
                {% if product.main_image_url %}
                <img src="{{ product.main_image_url }}" alt="{{ product.name }}">
                {% else %}
                <div style="padding: 100px; text-align: center; color: #999;">이미지 없음</div>
                {% endif %}
            </div>

            <div class="detail-info">
                {% if product.category %}
                <span class="detail-category">{{ product.category.name }}</span>
                {% endif %}

                <h1>{{ product.name }}</h1>

                <p class="detail-price">{{ "{:,}".format(product.price or 0) }}<span class="won">원</span></p>

                <div class="detail-meta">
                    <div class="meta-row">
                        <span class="meta-label">배송비</span>
                        <span class="meta-value">
                            {% if product.delivery_fee %}{{ "{:,}".format(product.delivery_fee) }}원{% else %}무료배송{% endif %}
                        </span>
                    </div>
                    <div class="meta-row">
                        <span class="meta-label">재고</span>
                        <span class="meta-value">{{ product.stock or 0 }}개</span>
                    </div>
                    <div class="meta-row">
                        <span class="meta-label">배송안내</span>
                        <span class="meta-value">오후 5시 이전 주문 시 당일 발송</span>
                    </div>
                </div>

                {% if options and options|length > 0 %}
                <div class="option-section">
                    <p class="option-label">옵션 선택</p>
                    <select class="option-select" id="productOption">
                        <option value="">옵션을 선택해 주세요</option>
                        {% for opt in options %}
                        <option value="{{ opt.value }}">{{ opt.text }}</option>
                        {% endfor %}
                    </select>
                </div>
                {% endif %}

                <button class="buy-button">바로 구매하기</button>
                <button class="cart-button">장바구니 담기</button>
            </div>
        </div>

        {% if detail_content %}
        <section class="content-section">
            <h2>상품 상세정보</h2>
            <div class="detail-content">
                {% for item in detail_content %}
                    {% if item.type == 'text' %}
                    <div class="text-block">{{ item.content }}</div>
                    {% elif item.type == 'image' %}
                    <div class="image-block">
                        <img src="{{ item.url }}" alt="상세 이미지" loading="lazy">
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
        </section>
        {% endif %}
    </main>

    <footer class="footer">
        <p>© 2026 Young Fresh Mall. All rights reserved.</p>
        <p style="margin-top:5px;">고객센터: 1234-5678 | 평일 09:00 - 18:00</p>
    </footer>
</body>
</html>
"""


def from_json(value):
    try:
        return json.loads(value) if value else []
    except:
        return []


@app.route('/')
@app.route('/category/<code>')
def index(code=None):
    session = get_session()

    query = session.query(Product).options(joinedload(Product.category))
    if code:
        cat = session.query(Category).filter_by(code=code).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    products = query.all()

    # 세션 닫기 전에 카테고리 정보 미리 로드
    for p in products:
        _ = p.category

    session.close()

    return render_template_string(
        MAIN_TEMPLATE,
        products=products,
        categories=CATEGORIES,
        category=code,
    )


@app.route('/product/<int:article_idx>')
def product_detail(article_idx):
    session = get_session()
    product = session.query(Product).options(joinedload(Product.category)).filter_by(article_idx=article_idx).first()

    if not product:
        session.close()
        return "상품을 찾을 수 없습니다.", 404

    options = from_json(product.options)
    detail_content = from_json(product.detail_content)

    # 세션 닫기 전에 카테고리 정보 미리 로드
    _ = product.category

    session.close()

    return render_template_string(
        DETAIL_TEMPLATE,
        product=product,
        categories=CATEGORIES,
        options=options,
        detail_content=detail_content,
    )


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("🍎 Young Fresh Mall 서버 시작!")
    print("   http://127.0.0.1:5000 에서 확인하세요")
    print("   종료: Ctrl+C")
    print("=" * 50 + "\n")
    app.run(host='127.0.0.1', debug=True, port=5000)
