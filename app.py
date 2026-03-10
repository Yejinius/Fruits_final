"""
Young Fresh Mall - 과일 공동구매 쇼핑몰
"""
import json
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.orm import joinedload
from models import get_session, Product, Category, Order, OrderItem, log_event
from config import CATEGORIES, FLASK_SECRET_KEY, FLASK_HOST, FLASK_PORT, DATA_DIR
from order_processor import create_order, AdminOrderProcessor
from sms import send_order_received_sms, send_payment_confirmed_sms
from payment_checker import payment_checker

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])


# ── 익명 방문자 분석 (PageView 트래킹) ────────────────
import re
import hashlib
import uuid
import threading

_SKIP_PREFIXES = ("/api/", "/data-images/", "/static/", "/favicon")
_PRODUCT_RE = re.compile(r"^/product/(\d+)")
_MOBILE_RE = re.compile(r"Mobile|Android|iPhone", re.I)


@app.after_request
def track_page_view(response):
    """페이지 방문 기록 (비동기, GET 성공 응답만)"""
    if request.method != "GET" or response.status_code >= 400:
        return response
    path = request.path
    if path.startswith(_SKIP_PREFIXES):
        return response

    # 세션 쿠키 (_vid)
    vid = request.cookies.get("_vid")
    new_vid = False
    if not vid:
        vid = uuid.uuid4().hex
        new_vid = True

    # article_idx 추출
    m = _PRODUCT_RE.match(path)
    article_idx = int(m.group(1)) if m else None

    # 모바일 판별
    ua = request.headers.get("User-Agent", "")
    is_mobile = bool(_MOBILE_RE.search(ua))

    # IP 익명화
    ip = request.remote_addr or ""
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]

    referrer = request.referrer

    def _save():
        try:
            from models import get_session as _gs, PageView
            s = _gs()
            s.add(PageView(
                session_id=vid, path=path, article_idx=article_idx,
                referrer=referrer, user_agent=ua[:500],
                is_mobile=is_mobile, ip_hash=ip_hash,
            ))
            s.commit()
            s.close()
        except Exception:
            pass

    threading.Thread(target=_save, daemon=True).start()

    if new_vid:
        response.set_cookie("_vid", vid, max_age=30*24*3600, httponly=True, samesite="Lax")
    return response


@app.route('/data-images/<filename>')
def serve_data_image(filename):
    """data/ 폴더의 이미지 서빙"""
    from flask import send_from_directory
    return send_from_directory(str(DATA_DIR), filename)

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
        padding: 15px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        max-width: 1200px;
        margin: 0 auto;
        border-bottom: 1px solid var(--border);
    }

    .header-brand {
        text-align: left;
        flex-shrink: 0;
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

    /* Search */
    .search-form {
        flex: 1;
        max-width: 450px;
        margin: 0 30px;
    }

    .search-box {
        display: flex;
        border: 2px solid var(--border);
        border-radius: 50px;
        overflow: hidden;
        transition: border-color 0.2s;
    }

    .search-box:focus-within {
        border-color: var(--primary);
    }

    .search-box input {
        flex: 1;
        padding: 10px 20px;
        border: none;
        outline: none;
        font-size: 14px;
        font-family: inherit;
        background: transparent;
    }

    .search-box button {
        padding: 10px 20px;
        border: none;
        background: var(--primary);
        color: white;
        font-size: 14px;
        cursor: pointer;
        transition: background 0.2s;
    }

    .search-box button:hover {
        background: var(--primary-dark);
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
        .header-top { flex-direction: column; text-align: center; gap: 10px; }
        .search-form { margin: 0; max-width: 100%; }
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
            <div class="header-brand">
                <a href="/" class="logo">Young<span>Fresh</span>Mall</a>
                <p class="tagline">실시간 경매상품 과일공동구매 (이제 과일 비싸게 사지 마세요!)</p>
            </div>
            <form class="search-form" action="/search" method="GET">
                <div class="search-box">
                    <input type="text" name="q" placeholder="상품명을 검색하세요" value="{{ search_query or '' }}">
                    <button type="submit">검색</button>
                </div>
            </form>
        </div>
        <nav class="nav">
            <ul class="nav-list">
                <li class="nav-item"><a href="/" {% if not category and not search_query %}class="active"{% endif %}>전체</a></li>
                {% for code, name in categories.items() %}
                <li class="nav-item">
                    <a href="/category/{{ code }}" {% if category == code %}class="active"{% endif %}>{{ name }}</a>
                </li>
                {% endfor %}
            </ul>
        </nav>
    </header>

    {% if not category and not search_query %}
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
            {% if search_query %}
                "{{ search_query }}" 검색 결과
                <span style="font-weight:400; font-size:14px; color:#999;">({{ products|length }}개)</span>
            {% elif category %}
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
        <p><a href="https://open.kakao.com/o/sNgjJoBb" target="_blank" style="color:var(--primary);font-weight:600;">카카오 오픈채팅 문의하기</a></p>
        <p style="margin-top:8px;">&copy; 2026 Young Fresh Mall. 언보링컴퍼니 All rights reserved.</p>
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
            color: var(--text-dark);
            white-space: pre-line;
        }
        .detail-content .text-block p {
            margin: 8px 0;
        }
        .detail-content .text-block br {
            display: block;
            content: "";
            margin: 4px 0;
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
            <div class="header-brand">
                <a href="/" class="logo">Young<span>Fresh</span>Mall</a>
                <p class="tagline">실시간 경매상품 과일공동구매 (이제 과일 비싸게 사지 마세요!)</p>
            </div>
            <form class="search-form" action="/search" method="GET">
                <div class="search-box">
                    <input type="text" name="q" placeholder="상품명을 검색하세요">
                    <button type="submit">검색</button>
                </div>
            </form>
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

                <p class="detail-price" id="displayPrice">{{ "{:,}".format(product.price or 0) }}<span class="won">원</span></p>

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

                <div class="option-section">
                    <p class="option-label">수량</p>
                    <div style="display:flex; align-items:center; gap:12px;">
                        <div style="display:flex; border:2px solid var(--border); border-radius:var(--radius-sm); overflow:hidden;">
                            <button type="button" onclick="changeQty(-1)" style="width:40px; height:44px; border:none; background:var(--bg-light); font-size:18px; cursor:pointer;">-</button>
                            <input type="number" id="quantity" value="1" min="1" max="99" style="width:50px; height:44px; border:none; text-align:center; font-size:16px; font-weight:600; -moz-appearance:textfield;" onchange="updateTotal()">
                            <button type="button" onclick="changeQty(1)" style="width:40px; height:44px; border:none; background:var(--bg-light); font-size:18px; cursor:pointer;">+</button>
                        </div>
                        <span id="totalPrice" style="font-size:18px; font-weight:700; color:var(--accent);"></span>
                    </div>
                </div>

                <a href="#" id="buyBtn" class="buy-button" style="display:block; text-align:center; color:white; text-decoration:none;">바로 구매하기</a>

                <script>
                var unitPrice = {{ product.price or 0 }};
                var deliveryFee = {{ product.delivery_fee or 0 }};
                var selectedArticleIdx = {{ product.article_idx }};
                function changeQty(d) {
                    var inp = document.getElementById('quantity');
                    var v = parseInt(inp.value) + d;
                    if (v < 1) v = 1;
                    if (v > 99) v = 99;
                    inp.value = v;
                    updateTotal();
                }
                function updateTotal() {
                    var qty = parseInt(document.getElementById('quantity').value) || 1;
                    var total = (unitPrice + deliveryFee) * qty;
                    document.getElementById('totalPrice').textContent = '총 ' + total.toLocaleString() + '원';
                    document.getElementById('buyBtn').href = '/order/' + selectedArticleIdx + '?qty=' + qty;
                    document.getElementById('displayPrice').innerHTML = unitPrice.toLocaleString() + '<span class="won">원</span>';
                }
                var optSel = document.getElementById('productOption');
                if (optSel) {
                    optSel.addEventListener('change', function() {
                        var parts = this.value.split('|');
                        if (parts.length >= 4) {
                            selectedArticleIdx = parseInt(parts[0]);
                            unitPrice = parseInt(parts[2]);
                            deliveryFee = parseInt(parts[3]);
                        }
                        updateTotal();
                    });
                }
                updateTotal();
                </script>
            </div>
        </div>

        {% if detail_content %}
        <section class="content-section">
            <h2>상품 상세정보</h2>
            <div class="detail-content">
                {% for item in detail_content %}
                    {% if item.type == 'text' %}
                    <div class="text-block">{{ item.content | safe }}</div>
                    {% elif item.type == 'image' %}
                    <div class="image-block">
                        <img src="{{ item.url }}" alt="상세 이미지" loading="lazy">
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
            {% if product.category and product.category.code == 'A' %}
            <div class="image-block" style="margin-top:20px; text-align:center;">
                <img src="/data-images/YF_final_image.jpg" alt="Young Fresh Mall" style="max-width:100%; border-radius:var(--radius-sm);">
            </div>
            {% endif %}
        </section>
        {% endif %}
    </main>

    <footer class="footer">
        <p><a href="https://open.kakao.com/o/sNgjJoBb" target="_blank" style="color:var(--primary);font-weight:600;">카카오 오픈채팅 문의하기</a></p>
        <p style="margin-top:8px;">&copy; 2026 Young Fresh Mall. 언보링컴퍼니 All rights reserved.</p>
    </footer>
    <script>
    // 마지막 상세 이미지 높이 4000px 초과 시 숨김 처리
    (function() {
        var imgs = document.querySelectorAll('.detail-content > .image-block img');
        if (imgs.length > 0) {
            var last = imgs[imgs.length - 1];
            var check = function() {
                if (last.naturalHeight > 4000) {
                    last.parentElement.style.display = 'none';
                }
            };
            if (last.complete && last.naturalHeight) check();
            else last.addEventListener('load', check);
        }
    })();
    </script>
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

    query = session.query(Product).options(joinedload(Product.category)).filter(Product.is_active == True)
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
        search_query=None,
    )


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect('/')

    session = get_session()
    products = session.query(Product).options(
        joinedload(Product.category)
    ).filter(
        Product.is_active == True,
        Product.name.contains(q)
    ).all()

    for p in products:
        _ = p.category

    session.close()

    return render_template_string(
        MAIN_TEMPLATE,
        products=products,
        categories=CATEGORIES,
        category=None,
        search_query=q,
    )


@app.route('/product/<int:article_idx>')
def product_detail(article_idx):
    session = get_session()
    product = session.query(Product).options(joinedload(Product.category)).filter_by(article_idx=article_idx).first()

    if not product or not product.is_active:
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


# === 주문 관련 ===

# 주문 페이지 템플릿
ORDER_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>주문하기 - Young Fresh Mall</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"></script>
    """ + COMMON_STYLES + """
    <style>
        .order-container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .order-section {
            background: var(--bg-white);
            border-radius: var(--radius);
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        .order-section h3 {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--primary);
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-dark);
            margin-bottom: 5px;
        }
        .form-group input, .form-group textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            font-size: 15px;
            font-family: inherit;
        }
        .form-group input:focus, .form-group textarea:focus {
            outline: none;
            border-color: var(--primary);
        }
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        .product-summary {
            display: flex;
            gap: 15px;
            padding: 15px;
            background: var(--bg-light);
            border-radius: var(--radius-sm);
        }
        .product-summary img {
            width: 80px;
            height: 80px;
            object-fit: cover;
            border-radius: var(--radius-sm);
        }
        .product-summary-info h4 {
            font-size: 15px;
            margin-bottom: 5px;
        }
        .product-summary-info .price {
            font-size: 18px;
            font-weight: 700;
            color: var(--primary-dark);
        }
        .order-total {
            text-align: right;
            padding: 20px 0;
            font-size: 20px;
            font-weight: 700;
        }
        .order-total .amount {
            color: var(--accent);
            font-size: 28px;
        }
        .submit-btn {
            width: 100%;
            padding: 18px;
            font-size: 18px;
            font-weight: 700;
            color: white;
            background: var(--primary);
            border: none;
            border-radius: var(--radius-sm);
            cursor: pointer;
        }
        .submit-btn:hover {
            background: var(--primary-dark);
        }
        .address-row {
            display: flex;
            gap: 10px;
        }
        .address-row input:first-child {
            width: 120px;
            flex-shrink: 0;
        }
        .addr-search-btn {
            display: inline-block;
            padding: 12px 20px;
            background: #555;
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            font-family: inherit;
        }
        .addr-search-btn:hover {
            background: #333;
        }
        .addr-readonly {
            background: #f5f5f5 !important;
            color: #444 !important;
            cursor: default;
        }
        @media (max-width: 768px) {
            .form-row { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-top">
            <a href="/" class="logo">Young<span>Fresh</span>Mall</a>
            <p class="tagline">실시간 경매상품 과일공동구매</p>
        </div>
    </header>

    <main class="order-container">
        <h2 style="font-size:24px; margin:20px 0;">주문하기</h2>

        <form method="POST" action="/order/submit">
            <input type="hidden" name="article_idx" value="{{ product.article_idx }}">
            <input type="hidden" name="quantity" value="{{ quantity }}">

            <div class="order-section">
                <h3>주문 상품</h3>
                <div class="product-summary">
                    {% if product.main_image_url %}
                    <img src="{{ product.main_image_url }}" alt="{{ product.name }}">
                    {% endif %}
                    <div class="product-summary-info">
                        <h4>{{ product.name }}</h4>
                        <p style="font-size:13px; color:#999;">{{ product.category.name if product.category else '' }}</p>
                        <p class="price">{{ "{:,}".format(product.price or 0) }}원 x {{ quantity }}개</p>
                        <p style="font-size:13px; color:#666;">배송비 {{ "{:,}".format(product.delivery_fee or 0) }}원</p>
                    </div>
                </div>
                <div class="order-total">
                    총 결제금액: <span class="amount">{{ "{:,}".format(((product.price or 0) + (product.delivery_fee or 0)) * quantity) }}원</span>
                </div>
            </div>

            <div class="order-section">
                <h3>배송 정보</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label>받으실 분 *</label>
                        <input type="text" name="customer_name" required placeholder="이름">
                    </div>
                    <div class="form-group">
                        <label>휴대폰 *</label>
                        <input type="text" name="customer_phone" required placeholder="010-0000-0000">
                    </div>
                </div>
                <div class="form-group">
                    <label>주소 *</label>
                    <button type="button" class="addr-search-btn" onclick="openDaumPostcode()">주소 검색하기</button>
                    <div class="address-row" style="margin-top:10px; margin-bottom:10px;">
                        <input type="text" id="zipcode" name="zipcode" required placeholder="우편번호" readonly class="addr-readonly">
                        <input type="text" id="address" name="address" required placeholder="기본주소" readonly class="addr-readonly" style="flex:1;">
                    </div>
                    <input type="text" name="address_detail" placeholder="상세주소 (동/호수)">
                </div>
                <div class="form-group">
                    <label>배송 메모</label>
                    <textarea name="memo" rows="2" placeholder="배송 요청사항을 입력하세요"></textarea>
                </div>
            </div>

            <div class="order-section">
                <h3>결제 정보</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label>입금자명</label>
                        <input type="text" name="depositor_name" placeholder="미입력 시 받으실 분과 동일">
                    </div>
                    <div class="form-group">
                        <label>현금영수증 번호</label>
                        <input type="text" name="cash_receipt_no" placeholder="010-0000-0000">
                    </div>
                </div>
            </div>

            <button type="submit" class="submit-btn">주문하기</button>
        </form>
    </main>

    <footer class="footer">
        <p><a href="https://open.kakao.com/o/sNgjJoBb" target="_blank" style="color:var(--primary);font-weight:600;">카카오 오픈채팅 문의하기</a></p>
        <p style="margin-top:8px;">&copy; 2026 Young Fresh Mall. 언보링컴퍼니 All rights reserved.</p>
    </footer>

    <script>
    function openDaumPostcode() {
        new daum.Postcode({
            oncomplete: function(data) {
                var addr = data.userSelectedType === 'R' ? data.roadAddress : data.jibunAddress;
                document.getElementById('zipcode').value = data.zonecode;
                document.getElementById('address').value = addr;
            }
        }).open();
    }
    </script>
</body>
</html>
"""

# 주문 완료 템플릿
ORDER_COMPLETE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>주문 완료 - Young Fresh Mall</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    """ + COMMON_STYLES + """
    <style>
        .complete-container {
            max-width: 600px;
            margin: 0 auto;
            padding: 60px 20px;
            text-align: center;
        }
        .check-icon {
            width: 80px;
            height: 80px;
            background: var(--primary);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            font-size: 40px;
            color: white;
        }
        .order-info {
            background: var(--bg-white);
            border-radius: var(--radius);
            padding: 25px;
            margin: 30px 0;
            box-shadow: var(--shadow);
            text-align: left;
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }
        .info-row:last-child { border-bottom: none; }
        .info-label { color: var(--text-light); }
        .info-value { font-weight: 600; }
        .home-btn {
            display: inline-block;
            padding: 15px 40px;
            background: var(--primary);
            color: white;
            border-radius: var(--radius-sm);
            font-size: 16px;
            font-weight: 600;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-top">
            <a href="/" class="logo">Young<span>Fresh</span>Mall</a>
        </div>
    </header>

    <main class="complete-container">
        <div class="check-icon">&#10003;</div>
        <h2 style="font-size:24px; margin-bottom:10px;">입금 확인 시 주문이 완료됩니다!</h2>
        <p style="color:#e53935; font-weight:600; margin-bottom:5px;">주문 후 3시간 이내로 입금해 주세요.</p>
        <p style="color:#666; font-size:13px;">미입금 시 주문이 자동 취소될 수 있습니다.</p>

        <div style="background:#FFF8E1; border:2px solid #FFB300; border-radius:var(--radius); padding:25px; margin:25px 0; text-align:center;">
            <p style="font-size:15px; color:#666; margin-bottom:12px; font-weight:500;">아래 계좌로 <strong style="color:#E65100; font-size:17px;">총 {{ "{:,}".format(order.total_amount) }}원</strong>을 입금해 주세요</p>
            <p style="font-size:20px; font-weight:800; color:#E65100; margin-bottom:8px;">농협 351-1064-5212-83</p>
            <p style="font-size:17px; font-weight:700; color:#333;">예금주 : 오픈스토리☆</p>
            <p style="font-size:15px; color:#888; margin-top:10px;">입금자명: <strong style="color:#333;">{{ order.depositor_name or order.customer_name }}</strong></p>
        </div>

        <div class="order-info">
            <div class="info-row">
                <span class="info-label">주문번호</span>
                <span class="info-value">{{ order.order_number }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">받으실 분</span>
                <span class="info-value">{{ order.customer_name }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">연락처</span>
                <span class="info-value">{{ order.customer_phone }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">배송지</span>
                <span class="info-value">{{ order.address }} {{ order.address_detail }}</span>
            </div>
            {% for item in order.items %}
            <div class="info-row">
                <span class="info-label">상품</span>
                <span class="info-value">{{ item.product_name }} x {{ item.quantity }}</span>
            </div>
            {% endfor %}
            <div class="info-row">
                <span class="info-label">총 결제금액</span>
                <span class="info-value" style="color:var(--accent); font-size:18px;">{{ "{:,}".format(order.total_amount) }}원</span>
            </div>
            <div class="info-row">
                <span class="info-label">주문 상태</span>
                <span class="info-value">{{ {"pending": "입금 대기", "processing": "처리 중", "awaiting_payment": "입금 대기", "paid": "입금 확인", "out_of_stock": "품절", "completed": "주문 완료", "failed": "주문 실패"}.get(order.status, order.status) }}</span>
            </div>
        </div>

        <a href="/" class="home-btn">쇼핑 계속하기</a>
    </main>
</body>
</html>
"""


@app.route('/order/<int:article_idx>')
def order_form(article_idx):
    """주문 폼 페이지"""
    quantity = int(request.args.get('qty', 1))
    if quantity < 1:
        quantity = 1

    session = get_session()
    product = session.query(Product).options(
        joinedload(Product.category)
    ).filter_by(article_idx=article_idx).first()

    if not product or not product.is_active:
        session.close()
        return "판매 종료된 상품입니다.", 404

    _ = product.category
    session.close()

    return render_template_string(ORDER_TEMPLATE, product=product, categories=CATEGORIES, quantity=quantity)


def _validate_phone(phone: str) -> bool:
    """한국 휴대전화 번호 검증 (010-XXXX-XXXX 또는 01012345678)"""
    import re
    cleaned = phone.replace("-", "")
    return bool(re.match(r'^01[016789]\d{7,8}$', cleaned))


@app.route('/order/submit', methods=['POST'])
@limiter.limit("30 per minute")
def order_submit():
    """주문 접수 처리"""
    # 입력값 검증
    customer_name = request.form.get('customer_name', '').strip()
    customer_phone = request.form.get('customer_phone', '').strip()

    if not customer_name or len(customer_name) > 50:
        return jsonify({'error': '이름을 올바르게 입력해주세요 (1~50자)'}), 400
    if not _validate_phone(customer_phone):
        return jsonify({'error': '올바른 휴대전화 번호를 입력해주세요'}), 400

    try:
        article_idx = int(request.form['article_idx'])
        quantity = int(request.form.get('quantity', 1))
    except (ValueError, KeyError):
        return jsonify({'error': '잘못된 상품 정보입니다'}), 400

    if quantity < 1 or quantity > 99:
        return jsonify({'error': '수량은 1~99 사이로 입력해주세요'}), 400

    memo = request.form.get('memo') or None
    if memo and len(memo) > 500:
        return jsonify({'error': '메모는 500자 이내로 입력해주세요'}), 400

    order = create_order(
        customer_name=customer_name,
        customer_phone=customer_phone,
        zipcode=request.form.get('zipcode', ''),
        address=request.form.get('address', ''),
        address_detail=request.form.get('address_detail', ''),
        items=[{'article_idx': article_idx, 'quantity': quantity}],
        depositor_name=request.form.get('depositor_name') or None,
        cash_receipt_no=request.form.get('cash_receipt_no') or None,
        memo=memo
    )

    # Admin 자동 등록 (백그라운드로 처리하는 것이 이상적이나, 여기선 동기 처리)
    processor = AdminOrderProcessor()
    try:
        result = processor.process_order(order)
        if not result.get('success'):
            log_event('error', 'order', f"주문 {order.order_number} Admin 등록 실패: {result.get('error', '알 수 없는 오류')}", related_id=order.order_number)
    except Exception as e:
        log_event('error', 'order', f"주문 {order.order_number} Admin 등록 중 예외: {e}", detail=str(e), related_id=order.order_number)
    finally:
        processor.close()

    # 주문 접수 SMS 발송
    try:
        # DB에서 order를 다시 로드 (items 포함)
        sms_session = get_session()
        sms_order = sms_session.query(Order).filter_by(order_number=order.order_number).first()
        if sms_order:
            _ = sms_order.items  # lazy load
            send_order_received_sms(sms_order)
        sms_session.close()
    except Exception as e:
        log_event('error', 'sms', f"주문 {order.order_number} 접수 SMS 발송 실패: {e}", detail=str(e), related_id=order.order_number)

    # 10분 뒤 입금 확인 체크 예약
    payment_checker.on_new_order()

    return redirect(f'/order/complete/{order.order_number}')


@app.route('/order/complete/<order_number>')
def order_complete(order_number):
    """주문 완료 페이지"""
    session = get_session()
    order = session.query(Order).filter_by(order_number=order_number).first()

    if not order:
        session.close()
        return "주문을 찾을 수 없습니다.", 404

    # items 미리 로드
    _ = order.items
    session.close()

    return render_template_string(ORDER_COMPLETE_TEMPLATE, order=order)


# === 주문 관리 API ===

@app.route('/api/orders/<order_number>/confirm-payment', methods=['POST'])
@limiter.limit("30 per minute")
def api_confirm_payment(order_number):
    """수동 입금 확인 → DB 업데이트 + SMS 발송"""
    result = payment_checker.confirm_payment_manual(order_number)
    return jsonify(result)


@app.route('/api/payments/check', methods=['POST'])
@limiter.limit("10 per minute")
def api_check_payments():
    """수동 입금 확인 체크 실행 (Admin 주문 목록 스크래핑)"""
    result = payment_checker.check_payments()
    return jsonify(result)


@app.route('/api/orders')
def api_orders():
    """주문 목록 API"""
    session = get_session()
    orders = session.query(Order).order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        result.append({
            'order_number': o.order_number,
            'customer_name': o.customer_name,
            'total_amount': o.total_amount,
            'status': o.status,
            'admin_customer_idx': o.admin_customer_idx,
            'created_at': o.created_at.isoformat() if o.created_at else None,
            'items': [{'product_name': i.product_name, 'quantity': i.quantity, 'price': i.price} for i in o.items]
        })
    session.close()
    return jsonify(result)


# ── 테니스 스코어보드 (실시간 공유, 파일 기반) ────────────────
import os as _os
import time as _time
import fcntl as _fcntl

_TENNIS_DIR = _os.path.join(str(DATA_DIR), 'tennis')
_os.makedirs(_TENNIS_DIR, exist_ok=True)
_TENNIS_SCORES_FILE = _os.path.join(_TENNIS_DIR, 'scores.json')
_TENNIS_BRACKET_FILE = _os.path.join(_TENNIS_DIR, 'bracket.json')
_TENNIS_PLAYERS_FILE = _os.path.join(_TENNIS_DIR, 'players.json')


def _read_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _write_json(path, data):
    with open(path, 'w') as f:
        _fcntl.flock(f, _fcntl.LOCK_EX)
        json.dump(data, f, ensure_ascii=False)
        _fcntl.flock(f, _fcntl.LOCK_UN)


# ── 테니스 페이지 ────────────────
@app.route('/tennis')
def tennis_scoreboard():
    """테니스 스코어보드 페이지"""
    from flask import send_from_directory as _sfd
    return _sfd(app.static_folder, 'tennis.html')


# ── 스코어 API ────────────────
@app.route('/api/tennis/scores', methods=['GET'])
@limiter.exempt
def tennis_get_scores():
    return jsonify(_read_json(_TENNIS_SCORES_FILE, {"scores": {}, "ts": 0}))


@app.route('/api/tennis/scores', methods=['POST'])
@limiter.exempt
def tennis_update_score():
    data = request.get_json()
    key = data.get("key")
    if key and "scores" in data:
        store = _read_json(_TENNIS_SCORES_FILE, {"scores": {}, "ts": 0})
        store["scores"][key] = data["scores"]
        store["ts"] = int(_time.time() * 1000)
        _write_json(_TENNIS_SCORES_FILE, store)
        return jsonify({"ok": True, "ts": store["ts"]})
    return jsonify({"ok": False}), 400


@app.route('/api/tennis/reset', methods=['POST'])
@limiter.exempt
def tennis_reset():
    store = {"scores": {}, "ts": int(_time.time() * 1000)}
    _write_json(_TENNIS_SCORES_FILE, store)
    return jsonify({"ok": True})


# ── 참가자 API (실시간 동기화) ────────────────
@app.route('/api/tennis/players', methods=['GET'])
@limiter.exempt
def tennis_get_players():
    return jsonify(_read_json(_TENNIS_PLAYERS_FILE, {"players": [], "settings": {}, "ts": 0}))


@app.route('/api/tennis/players', methods=['POST'])
@limiter.exempt
def tennis_save_players():
    data = request.get_json()
    store = {
        "players": data.get("players", []),
        "settings": data.get("settings", {}),
        "ts": int(_time.time() * 1000),
    }
    _write_json(_TENNIS_PLAYERS_FILE, store)
    return jsonify({"ok": True, "ts": store["ts"]})


# ── 대진표 API (실시간 동기화) ────────────────
@app.route('/api/tennis/bracket', methods=['GET'])
@limiter.exempt
def tennis_get_bracket():
    return jsonify(_read_json(_TENNIS_BRACKET_FILE, {"rounds": [], "emojis": {}, "ts": 0}))


@app.route('/api/tennis/bracket', methods=['POST'])
@limiter.exempt
def tennis_save_bracket():
    data = request.get_json()
    store = {
        "rounds": data.get("rounds", []),
        "emojis": data.get("emojis", {}),
        "date": data.get("date", ""),
        "ts": int(_time.time() * 1000),
    }
    _write_json(_TENNIS_BRACKET_FILE, store)
    # 대진표 확정 시 스코어 초기화
    _write_json(_TENNIS_SCORES_FILE, {"scores": {}, "ts": store["ts"]})
    return jsonify({"ok": True, "ts": store["ts"]})


# ── 대진표 AI 생성 (Claude CLI) ────────────────
@app.route('/api/tennis/generate', methods=['POST'])
@limiter.limit("10 per hour")
def tennis_generate():
    """희망사항을 반영한 AI 대진표 생성 (claude CLI 사용)"""
    import subprocess
    import re as _re

    data = request.get_json()
    players = data.get('players', [])
    num_courts = data.get('numCourts', 2)
    duration = data.get('duration', 20)
    start_time = data.get('startTime', '19:00')
    end_time = data.get('endTime', '22:00')
    warmup = data.get('warmup', 20)
    wish = data.get('wish', '')

    if len(players) < 4:
        return jsonify({"ok": False, "error": "최소 4명 필요"}), 400
    if not wish:
        return jsonify({"ok": False, "error": "희망사항이 없으면 로컬 생성 사용"}), 400

    # 시간 슬롯 계산
    sh, sm = map(int, start_time.split(':'))
    eh, em = map(int, end_time.split(':'))
    total_min = (eh * 60 + em) - (sh * 60 + sm) - warmup
    num_rounds = total_min // duration

    start_min = sh * 60 + sm + warmup
    time_slots = []
    for i in range(num_rounds):
        fr = start_min + i * duration
        to = fr + duration
        fh, fm_ = divmod(fr, 60)
        th, tm_ = divmod(to, 60)
        time_slots.append(f"{fh:02d}:{fm_:02d}~{th:02d}:{tm_:02d}")

    player_info = "\n".join(
        f"- {p['name']} (성별: {'남' if p['gender']=='M' else '여'}, NTRP: {p.get('ntrp', 3.0)})"
        for p in players
    )

    prompt = f"""테니스 복식 대진표를 생성해주세요.

## 참가자 ({len(players)}명)
{player_info}

## 경기 설정
- 코트 수: {num_courts}
- 라운드 수: {num_rounds}
- 경기 시간: {duration}분
- 타임슬롯: {', '.join(time_slots)}

## 규칙
1. 각 라운드에 {num_courts}개 코트 × 4명 = {num_courts * 4}명 경기, 나머지는 휴식
2. 복식 유형: 혼복(남2+여2), 남복(남4), 여복(여4) — 가능한 한 혼복 우선
3. 모든 참가자의 경기 수가 균등해야 함 (±1 이내)
4. 최대 2라운드 연속 출전 가능 (3연속 금지)
5. 같은 파트너 조합 반복 최소화

## 희망사항 (반드시 반영!)
{wish}

## 출력 형식 (반드시 이 JSON 형식만 출력! 설명 없이!)
```json
{{
  "rounds": [
    {{
      "num": 1,
      "time": "{time_slots[0] if time_slots else '19:20~19:40'}",
      "courts": [
        {{
          "type": "혼복",
          "team1": ["이름1", "이름2"],
          "team2": ["이름3", "이름4"]
        }}
      ],
      "rest": ["이름5", "이름6"]
    }}
  ]
}}
```"""

    try:
        _claude_bin = "/opt/homebrew/bin/claude"
        _env = {**_os.environ, "TERM": "dumb"}
        # gunicorn PATH에 homebrew가 없으므로 추가
        _env["PATH"] = "/opt/homebrew/bin:" + _env.get("PATH", "/usr/bin:/bin")
        # dotenv로 로드된 토큰이 os.environ에 없을 수 있으므로 .env에서 직접 읽기
        if "CLAUDE_CODE_OAUTH_TOKEN" not in _env:
            try:
                with open(_os.path.join(str(BASE_DIR), ".env")) as _ef:
                    for _line in _ef:
                        if _line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                            _env["CLAUDE_CODE_OAUTH_TOKEN"] = _line.split("=", 1)[1].strip()
            except Exception:
                pass

        result = subprocess.run(
            [_claude_bin, "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=120,
            env=_env,
        )

        if result.returncode != 0:
            return jsonify({"ok": False, "error": f"Claude CLI 오류: {result.stderr[:200]}"}), 500

        text = result.stdout.strip()

        # Parse JSON from response
        json_match = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, _re.DOTALL)
        if json_match:
            bracket_data = json.loads(json_match.group(1))
        elif text.startswith('{'):
            bracket_data = json.loads(text)
        else:
            # Try finding JSON object anywhere in text
            brace_match = _re.search(r'\{[\s\S]*"rounds"[\s\S]*\}', text)
            if brace_match:
                bracket_data = json.loads(brace_match.group(0))
            else:
                return jsonify({"ok": False, "error": "AI 응답에서 JSON을 찾을 수 없습니다"}), 500

        rounds = bracket_data.get("rounds", [])
        if not rounds:
            return jsonify({"ok": False, "error": "대진표가 비어있습니다"}), 500

        return jsonify({"ok": True, "rounds": rounds})

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "AI 생성 시간 초과 (2분)"}), 500
    except json.JSONDecodeError as e:
        return jsonify({"ok": False, "error": f"JSON 파싱 실패: {str(e)[:100]}"}), 500
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "Claude CLI가 설치되어 있지 않습니다"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 500


if __name__ == '__main__':
    import os
    is_production = os.getenv('FLASK_ENV') == 'production'

    print("\n" + "=" * 50)
    print("Young Fresh Mall")
    print(f"   http://{FLASK_HOST}:{FLASK_PORT} 에서 확인하세요")
    print("   종료: Ctrl+C")
    print("=" * 50 + "\n")

    # 입금 확인 스케줄러 시작 (미입금 건 있으면 30분 후 첫 체크)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or is_production:
        payment_checker.start_periodic(interval_minutes=30)

    app.run(host=FLASK_HOST, debug=not is_production, port=FLASK_PORT)
