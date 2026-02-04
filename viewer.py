"""
크롤링 데이터 확인용 간단한 웹 뷰어
"""
import json
from flask import Flask, render_template_string
from models import get_session, Product, Category
from config import CATEGORIES

app = Flask(__name__)

# 목록 페이지 템플릿
LIST_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>OS79 크롤링 데이터 뷰어</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; }
        .header { background: #2c3e50; color: white; padding: 20px; text-align: center; }
        .header h1 { margin-bottom: 10px; }
        .stats { display: flex; justify-content: center; gap: 30px; margin-top: 15px; }
        .stat { text-align: center; }
        .stat-num { font-size: 24px; font-weight: bold; color: #3498db; }
        .nav { background: #34495e; padding: 10px; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }
        .nav a { color: white; text-decoration: none; padding: 8px 16px; border-radius: 5px; background: #3498db; }
        .nav a:hover, .nav a.active { background: #2980b9; }
        .container { max-width: 1400px; margin: 20px auto; padding: 0 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }
        .card { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); cursor: pointer; transition: transform 0.2s; }
        .card:hover { transform: translateY(-5px); }
        .card-img { width: 100%; height: 200px; object-fit: cover; background: #eee; }
        .card-img.missing { display: flex; align-items: center; justify-content: center; color: #999; }
        .card-body { padding: 15px; }
        .card-title { font-size: 16px; font-weight: 600; margin-bottom: 10px; line-height: 1.4;
                      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .card-price { font-size: 20px; font-weight: bold; color: #e74c3c; margin-bottom: 10px; }
        .card-meta { font-size: 13px; color: #666; }
        .card-meta span { display: inline-block; margin-right: 15px; margin-bottom: 5px; }
        .badge { display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 11px; margin-right: 5px; }
        .badge-stock { background: #27ae60; color: white; }
        .badge-nostock { background: #e74c3c; color: white; }
        .badge-option { background: #9b59b6; color: white; }
        .badge-img { background: #3498db; color: white; }
        .badge-content { background: #e67e22; color: white; }
        .check-list { margin-top: 10px; font-size: 12px; }
        .check-item { padding: 2px 0; }
        .check-ok { color: #27ae60; }
        .check-fail { color: #e74c3c; }
        .summary { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .summary h3 { margin-bottom: 15px; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .summary-item { padding: 15px; background: #f8f9fa; border-radius: 8px; }
        .summary-item h4 { color: #666; font-size: 14px; margin-bottom: 5px; }
        .summary-item .num { font-size: 24px; font-weight: bold; color: #2c3e50; }
        a.card-link { text-decoration: none; color: inherit; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🍎 OS79 크롤링 데이터 뷰어</h1>
        <div class="stats">
            <div class="stat">
                <div class="stat-num">{{ total_products }}</div>
                <div>총 상품</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ total_with_image }}</div>
                <div>이미지 있음</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ total_with_desc }}</div>
                <div>설명 있음</div>
            </div>
        </div>
    </div>

    <div class="nav">
        <a href="/" {% if not category %}class="active"{% endif %}>전체 ({{ total_products }})</a>
        {% for code, name in categories.items() %}
        <a href="/category/{{ code }}" {% if category == code %}class="active"{% endif %}>
            {{ name }} ({{ cat_counts.get(code, 0) }})
        </a>
        {% endfor %}
    </div>

    <div class="container">
        <div class="summary">
            <h3>📊 데이터 품질 요약</h3>
            <div class="summary-grid">
                <div class="summary-item">
                    <h4>이미지 수집률</h4>
                    <div class="num">{{ "%.1f"|format(image_rate) }}%</div>
                </div>
                <div class="summary-item">
                    <h4>가격 정보</h4>
                    <div class="num">{{ "%.1f"|format(price_rate) }}%</div>
                </div>
                <div class="summary-item">
                    <h4>상품 설명</h4>
                    <div class="num">{{ "%.1f"|format(desc_rate) }}%</div>
                </div>
                <div class="summary-item">
                    <h4>상세 콘텐츠</h4>
                    <div class="num">{{ "%.1f"|format(content_rate) }}%</div>
                </div>
            </div>
        </div>

        <div class="grid">
            {% for product in products %}
            <a href="/product/{{ product.article_idx }}" class="card-link">
                <div class="card">
                    {% if product.main_image_url %}
                    <img class="card-img" src="{{ product.main_image_url }}" onerror="this.outerHTML='<div class=\\'card-img missing\\'>이미지 로드 실패</div>'">
                    {% else %}
                    <div class="card-img missing">이미지 없음</div>
                    {% endif %}

                    <div class="card-body">
                        <div class="card-title">{{ product.name }}</div>
                        <div class="card-price">{{ "{:,}".format(product.price or 0) }}원</div>

                        <div class="card-meta">
                            {% if product.stock and product.stock > 0 %}
                            <span class="badge badge-stock">재고 {{ product.stock }}</span>
                            {% else %}
                            <span class="badge badge-nostock">재고 없음</span>
                            {% endif %}

                            {% if product.options and product.options != '[]' %}
                            <span class="badge badge-option">옵션 {{ (product.options | from_json | length) if product.options else 0 }}개</span>
                            {% endif %}

                            {% if product.detail_images and product.detail_images != '[]' %}
                            <span class="badge badge-img">상세이미지 {{ (product.detail_images | from_json | length) if product.detail_images else 0 }}개</span>
                            {% endif %}

                            {% if product.detail_content and product.detail_content != '[]' %}
                            <span class="badge badge-content">상세콘텐츠 {{ (product.detail_content | from_json | length) if product.detail_content else 0 }}개</span>
                            {% endif %}
                        </div>

                        <div class="check-list">
                            <div class="check-item {% if product.main_image_url %}check-ok{% else %}check-fail{% endif %}">
                                {{ "✓" if product.main_image_url else "✗" }} 메인 이미지
                            </div>
                            <div class="check-item {% if product.price %}check-ok{% else %}check-fail{% endif %}">
                                {{ "✓" if product.price else "✗" }} 가격 정보
                            </div>
                            <div class="check-item {% if product.description %}check-ok{% else %}check-fail{% endif %}">
                                {{ "✓" if product.description else "✗" }} 상품 설명
                            </div>
                            <div class="check-item {% if product.detail_content and product.detail_content != '[]' %}check-ok{% else %}check-fail{% endif %}">
                                {{ "✓" if product.detail_content and product.detail_content != '[]' else "✗" }} 상세 콘텐츠
                            </div>
                        </div>
                    </div>
                </div>
            </a>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

# 상세 페이지 템플릿
DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{{ product.name }} - OS79 뷰어</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; }
        .header { background: #2c3e50; color: white; padding: 15px 20px; }
        .header a { color: white; text-decoration: none; }
        .header h1 { font-size: 18px; }
        .container { max-width: 1000px; margin: 20px auto; padding: 0 20px; }
        .back-btn { display: inline-block; margin-bottom: 20px; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; }
        .back-btn:hover { background: #2980b9; }
        .product-header { background: white; border-radius: 10px; padding: 30px; margin-bottom: 20px; display: flex; gap: 30px; }
        .product-image { flex: 0 0 400px; }
        .product-image img { width: 100%; border-radius: 10px; }
        .product-info { flex: 1; }
        .product-info h1 { font-size: 24px; margin-bottom: 15px; line-height: 1.4; }
        .product-price { font-size: 32px; font-weight: bold; color: #e74c3c; margin-bottom: 20px; }
        .product-meta { margin-bottom: 20px; }
        .product-meta p { padding: 8px 0; border-bottom: 1px solid #eee; color: #666; }
        .product-meta strong { color: #333; }
        .badge { display: inline-block; padding: 5px 12px; border-radius: 5px; font-size: 13px; margin-right: 8px; margin-bottom: 8px; }
        .badge-stock { background: #27ae60; color: white; }
        .badge-option { background: #9b59b6; color: white; }
        .section { background: white; border-radius: 10px; padding: 30px; margin-bottom: 20px; }
        .section h2 { font-size: 20px; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #3498db; }
        .detail-content { line-height: 1.8; }
        .detail-content .text-block { margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; white-space: pre-wrap; }
        .detail-content .image-block { margin: 20px 0; text-align: center; }
        .detail-content .image-block img { max-width: 100%; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .options-list { display: flex; flex-wrap: wrap; gap: 10px; }
        .option-item { padding: 10px 15px; background: #f8f9fa; border-radius: 5px; border: 1px solid #ddd; }
        .raw-data { background: #f8f9fa; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
        .empty-notice { color: #999; font-style: italic; padding: 20px; text-align: center; background: #f8f9fa; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <a href="/"><h1>🍎 OS79 크롤링 데이터 뷰어</h1></a>
    </div>

    <div class="container">
        <a href="javascript:history.back()" class="back-btn">← 목록으로</a>

        <div class="product-header">
            <div class="product-image">
                {% if product.main_image_url %}
                <img src="{{ product.main_image_url }}" alt="{{ product.name }}">
                {% else %}
                <div style="width:100%;height:300px;background:#eee;display:flex;align-items:center;justify-content:center;border-radius:10px;">이미지 없음</div>
                {% endif %}
            </div>
            <div class="product-info">
                <h1>{{ product.name }}</h1>
                <div class="product-price">{{ "{:,}".format(product.price or 0) }}원</div>
                <div class="product-meta">
                    <p><strong>상품 ID:</strong> {{ product.article_idx }}</p>
                    <p><strong>재고:</strong> {{ product.stock or 0 }}개</p>
                    <p><strong>배송비:</strong> {{ "{:,}".format(product.delivery_fee or 0) }}원</p>
                    <p><strong>원본 URL:</strong> <a href="{{ product.source_url }}" target="_blank">{{ product.source_url }}</a></p>
                </div>
                <div>
                    {% if product.stock and product.stock > 0 %}
                    <span class="badge badge-stock">재고 있음</span>
                    {% endif %}
                    {% if options %}
                    <span class="badge badge-option">옵션 {{ options | length }}개</span>
                    {% endif %}
                </div>
            </div>
        </div>

        {% if options %}
        <div class="section">
            <h2>📦 옵션</h2>
            <div class="options-list">
                {% for opt in options %}
                <div class="option-item">{{ opt.text }}</div>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        <div class="section">
            <h2>📝 상세 콘텐츠</h2>
            <div class="detail-content">
                {% if detail_content %}
                    {% for item in detail_content %}
                        {% if item.type == 'text' %}
                        <div class="text-block">{{ item.content }}</div>
                        {% elif item.type == 'image' %}
                        <div class="image-block">
                            <img src="{{ item.url }}" alt="상세 이미지" onerror="this.style.display='none'">
                        </div>
                        {% endif %}
                    {% endfor %}
                {% else %}
                <div class="empty-notice">상세 콘텐츠가 없습니다. (재크롤링 필요)</div>
                {% endif %}
            </div>
        </div>

        {% if product.description %}
        <div class="section">
            <h2>📄 텍스트 설명 (Raw)</h2>
            <div class="raw-data">{{ product.description }}</div>
        </div>
        {% endif %}

        {% if detail_images %}
        <div class="section">
            <h2>🖼️ 상세 이미지 목록 ({{ detail_images | length }}개)</h2>
            <div class="detail-content">
                {% for img_url in detail_images %}
                <div class="image-block">
                    <img src="{{ img_url }}" alt="상세 이미지 {{ loop.index }}">
                    <p style="margin-top:5px;font-size:12px;color:#999;">{{ img_url }}</p>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


def from_json(value):
    try:
        return json.loads(value) if value else []
    except:
        return []


app.jinja_env.filters['from_json'] = from_json


@app.route('/')
@app.route('/category/<code>')
def index(code=None):
    session = get_session()

    # 카테고리별 카운트
    cat_counts = {}
    for c in CATEGORIES.keys():
        cat = session.query(Category).filter_by(code=c).first()
        if cat:
            cat_counts[c] = session.query(Product).filter_by(category_id=cat.id).count()

    # 상품 조회
    query = session.query(Product)
    if code:
        cat = session.query(Category).filter_by(code=code).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    products = query.all()
    total = len(products)

    # 통계
    with_image = sum(1 for p in products if p.main_image_url)
    with_price = sum(1 for p in products if p.price)
    with_desc = sum(1 for p in products if p.description)
    with_content = sum(1 for p in products if p.detail_content and p.detail_content != '[]')

    session.close()

    return render_template_string(
        LIST_TEMPLATE,
        products=products,
        categories=CATEGORIES,
        category=code,
        cat_counts=cat_counts,
        total_products=total,
        total_with_image=with_image,
        total_with_desc=with_desc,
        image_rate=(with_image / total * 100) if total else 0,
        price_rate=(with_price / total * 100) if total else 0,
        desc_rate=(with_desc / total * 100) if total else 0,
        content_rate=(with_content / total * 100) if total else 0,
    )


@app.route('/product/<int:article_idx>')
def product_detail(article_idx):
    session = get_session()
    product = session.query(Product).filter_by(article_idx=article_idx).first()

    if not product:
        session.close()
        return "상품을 찾을 수 없습니다.", 404

    # JSON 파싱
    options = from_json(product.options)
    detail_images = from_json(product.detail_images)
    detail_content = from_json(product.detail_content)

    session.close()

    return render_template_string(
        DETAIL_TEMPLATE,
        product=product,
        options=options,
        detail_images=detail_images,
        detail_content=detail_content,
    )


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("🌐 웹 뷰어 시작!")
    print("   http://127.0.0.1:5000 에서 확인하세요")
    print("   종료: Ctrl+C")
    print("=" * 50 + "\n")
    app.run(host='127.0.0.1', debug=True, port=5000)
