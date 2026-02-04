"""
Admin 사이트 연동 테스트 - 웹 인터페이스
브라우저에서 각 단계를 실행하고 결과를 실시간으로 확인합니다.
"""
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, jsonify, request
import json

app = Flask(__name__)

# 전역 세션 (테스트용)
admin_session = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Admin 연동 테스트</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Malgun Gothic', sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }

        h1 {
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #2E7D32;
        }

        .step-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .step-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .step-title {
            font-size: 18px;
            font-weight: bold;
            color: #333;
        }

        .step-number {
            background: #2E7D32;
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 14px;
        }

        .step-desc {
            color: #666;
            margin-bottom: 15px;
            font-size: 14px;
        }

        .btn {
            padding: 10px 25px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.3s;
        }

        .btn-primary {
            background: #2E7D32;
            color: white;
        }

        .btn-primary:hover {
            background: #1B5E20;
        }

        .btn-primary:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        .result-box {
            background: #1e1e1e;
            color: #d4d4d4;
            border-radius: 5px;
            padding: 15px;
            margin-top: 15px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            max-height: 400px;
            overflow-y: auto;
            display: none;
        }

        .result-box.show { display: block; }

        .success { color: #4CAF50; }
        .error { color: #f44336; }
        .info { color: #2196F3; }
        .warning { color: #FF9800; }

        .status-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 3px;
            font-size: 12px;
            margin-left: 10px;
        }

        .status-pending { background: #e0e0e0; color: #666; }
        .status-running { background: #FFF3E0; color: #E65100; }
        .status-success { background: #E8F5E9; color: #2E7D32; }
        .status-error { background: #FFEBEE; color: #C62828; }

        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #2E7D32;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-left: 10px;
            vertical-align: middle;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 13px;
        }

        .data-table th, .data-table td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }

        .data-table th {
            background: #f5f5f5;
        }

        .data-table tr:nth-child(even) {
            background: #fafafa;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 Admin 사이트 연동 테스트</h1>
        <p style="color:#666; margin-bottom:20px;">
            각 단계의 [실행] 버튼을 클릭하여 HTTP Request 과정을 확인하세요.
        </p>

        <!-- Step 1: 로그인 -->
        <div class="step-card" id="step1-card">
            <div class="step-header">
                <div>
                    <span class="step-number">Step 1</span>
                    <span class="step-title">Admin 사이트 로그인</span>
                    <span class="status-badge status-pending" id="step1-status">대기</span>
                </div>
                <button class="btn btn-primary" onclick="runStep(1)">실행</button>
            </div>
            <div class="step-desc">
                POST 요청으로 로그인하고 세션 쿠키를 획득합니다.<br>
                URL: http://admin.open79.co.kr/m/include/asp/login_ok.asp
            </div>
            <div class="result-box" id="step1-result"></div>
        </div>

        <!-- Step 2: 로그인 확인 -->
        <div class="step-card" id="step2-card">
            <div class="step-header">
                <div>
                    <span class="step-number">Step 2</span>
                    <span class="step-title">로그인 상태 확인</span>
                    <span class="status-badge status-pending" id="step2-status">대기</span>
                </div>
                <button class="btn btn-primary" onclick="runStep(2)">실행</button>
            </div>
            <div class="step-desc">
                메인 페이지에 접근하여 로그인된 사용자명을 확인합니다.<br>
                URL: http://admin.open79.co.kr/m/default.asp
            </div>
            <div class="result-box" id="step2-result"></div>
        </div>

        <!-- Step 3: 고객 목록 -->
        <div class="step-card" id="step3-card">
            <div class="step-header">
                <div>
                    <span class="step-number">Step 3</span>
                    <span class="step-title">고객 목록 조회</span>
                    <span class="status-badge status-pending" id="step3-status">대기</span>
                </div>
                <button class="btn btn-primary" onclick="runStep(3)">실행</button>
            </div>
            <div class="step-desc">
                고객 관리 페이지에서 등록된 고객 목록을 가져옵니다.<br>
                URL: http://admin.open79.co.kr/m/customer/p_custom_list.asp
            </div>
            <div class="result-box" id="step3-result"></div>
        </div>

        <!-- Step 4: 고객 등록 폼 -->
        <div class="step-card" id="step4-card">
            <div class="step-header">
                <div>
                    <span class="step-number">Step 4</span>
                    <span class="step-title">고객 등록 폼 구조 확인</span>
                    <span class="status-badge status-pending" id="step4-status">대기</span>
                </div>
                <button class="btn btn-primary" onclick="runStep(4)">실행</button>
            </div>
            <div class="step-desc">
                고객 등록 폼의 필드 구조를 분석합니다.<br>
                URL: http://admin.open79.co.kr/m/customer/p_custom_regist.asp
            </div>
            <div class="result-box" id="step4-result"></div>
        </div>

        <!-- Step 5: 주문 목록 -->
        <div class="step-card" id="step5-card">
            <div class="step-header">
                <div>
                    <span class="step-number">Step 5</span>
                    <span class="step-title">주문 목록 조회</span>
                    <span class="status-badge status-pending" id="step5-status">대기</span>
                </div>
                <button class="btn btn-primary" onclick="runStep(5)">실행</button>
            </div>
            <div class="step-desc">
                주문 관리 페이지에서 주문 목록을 가져옵니다.<br>
                URL: http://admin.open79.co.kr/m/customer/p_order_list.asp
            </div>
            <div class="result-box" id="step5-result"></div>
        </div>

        <!-- Step 6: 주문 상세 -->
        <div class="step-card" id="step6-card">
            <div class="step-header">
                <div>
                    <span class="step-number">Step 6</span>
                    <span class="step-title">주문 상세 조회</span>
                    <span class="status-badge status-pending" id="step6-status">대기</span>
                </div>
                <button class="btn btn-primary" onclick="runStep(6)">실행</button>
            </div>
            <div class="step-desc">
                특정 주문의 상세 정보를 조회합니다.<br>
                URL: http://admin.open79.co.kr/m/customer/p_order_view.asp
            </div>
            <div class="result-box" id="step6-result"></div>
        </div>

        <!-- Step 7: 주문서 폼 -->
        <div class="step-card" id="step7-card">
            <div class="step-header">
                <div>
                    <span class="step-number">Step 7</span>
                    <span class="step-title">주문서 작성 폼 구조 확인</span>
                    <span class="status-badge status-pending" id="step7-status">대기</span>
                </div>
                <button class="btn btn-primary" onclick="runStep(7)">실행</button>
            </div>
            <div class="step-desc">
                주문서 작성 폼의 필드 및 카테고리/상품 옵션을 분석합니다.<br>
                URL: http://admin.open79.co.kr/m/customer/p_order_regist.asp
            </div>
            <div class="result-box" id="step7-result"></div>
        </div>
    </div>

    <script>
        function runStep(step) {
            const statusEl = document.getElementById(`step${step}-status`);
            const resultEl = document.getElementById(`step${step}-result`);
            const btn = event.target;

            // 상태 업데이트
            statusEl.className = 'status-badge status-running';
            statusEl.textContent = '실행중...';
            btn.disabled = true;
            btn.innerHTML = '실행중 <span class="loading"></span>';
            resultEl.classList.add('show');
            resultEl.innerHTML = '<span class="info">요청 전송 중...</span>';

            fetch(`/api/step/${step}`)
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        statusEl.className = 'status-badge status-success';
                        statusEl.textContent = '성공';
                    } else {
                        statusEl.className = 'status-badge status-error';
                        statusEl.textContent = '실패';
                    }

                    resultEl.innerHTML = formatResult(data);
                    btn.disabled = false;
                    btn.textContent = '다시 실행';
                })
                .catch(err => {
                    statusEl.className = 'status-badge status-error';
                    statusEl.textContent = '오류';
                    resultEl.innerHTML = `<span class="error">오류 발생: ${err.message}</span>`;
                    btn.disabled = false;
                    btn.textContent = '다시 실행';
                });
        }

        function formatResult(data) {
            let html = '';

            // 요청 정보
            html += '<span class="info">━━━━━━━━━━ 요청 정보 ━━━━━━━━━━</span>\\n';
            html += `URL: ${data.request.url}\\n`;
            html += `Method: ${data.request.method}\\n`;
            if (data.request.data) {
                html += `Data: ${JSON.stringify(data.request.data)}\\n`;
            }

            // 응답 정보
            html += '\\n<span class="info">━━━━━━━━━━ 응답 정보 ━━━━━━━━━━</span>\\n';
            html += `Status Code: ${data.response.status_code}\\n`;
            html += `Response Size: ${data.response.size} bytes\\n`;

            // 쿠키 정보
            if (data.cookies && Object.keys(data.cookies).length > 0) {
                html += '\\n<span class="info">━━━━━━━━━━ 쿠키 정보 ━━━━━━━━━━</span>\\n';
                for (const [key, value] of Object.entries(data.cookies)) {
                    html += `${key} = ${value}\\n`;
                }
            }

            // 결과 데이터
            html += '\\n<span class="info">━━━━━━━━━━ 결과 데이터 ━━━━━━━━━━</span>\\n';
            if (data.success) {
                html += `<span class="success">✅ ${data.message}</span>\\n\\n`;
            } else {
                html += `<span class="error">❌ ${data.message}</span>\\n\\n`;
            }

            if (data.data) {
                if (Array.isArray(data.data)) {
                    data.data.forEach((item, i) => {
                        if (typeof item === 'object') {
                            html += `${i+1}. `;
                            for (const [k, v] of Object.entries(item)) {
                                html += `${k}: ${v} | `;
                            }
                            html += '\\n';
                        } else {
                            html += `${i+1}. ${item}\\n`;
                        }
                    });
                } else if (typeof data.data === 'object') {
                    for (const [key, value] of Object.entries(data.data)) {
                        html += `${key}: ${value}\\n`;
                    }
                } else {
                    html += data.data;
                }
            }

            return html;
        }
    </script>
</body>
</html>
"""

class AdminSession:
    BASE_URL = "http://admin.open79.co.kr"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logged_in = False

    def get_cookies_dict(self):
        return {c.name: c.value for c in self.session.cookies}


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/step/<int:step>')
def run_step(step):
    global admin_session

    if admin_session is None:
        admin_session = AdminSession()

    if step == 1:
        return step1_login()
    elif step == 2:
        return step2_verify()
    elif step == 3:
        return step3_customers()
    elif step == 4:
        return step4_customer_form()
    elif step == 5:
        return step5_orders()
    elif step == 6:
        return step6_order_detail()
    elif step == 7:
        return step7_order_form()
    else:
        return jsonify({"success": False, "message": "Unknown step"})


def step1_login():
    """Step 1: 로그인"""
    url = f"{admin_session.BASE_URL}/m/include/asp/login_ok.asp"
    data = {"m_id": "REDACTED_ID", "m_passwd": "REDACTED_PW"}

    resp = admin_session.session.post(url, data=data)

    success = "location.replace" in resp.text and "/m/default.asp" in resp.text
    admin_session.logged_in = success

    return jsonify({
        "success": success,
        "message": "로그인 성공! 세션 쿠키가 설정되었습니다." if success else "로그인 실패",
        "request": {
            "url": url,
            "method": "POST",
            "data": {"m_id": "REDACTED_ID", "m_passwd": "****"}
        },
        "response": {
            "status_code": resp.status_code,
            "size": len(resp.text),
            "content_preview": resp.text[:100]
        },
        "cookies": admin_session.get_cookies_dict()
    })


def step2_verify():
    """Step 2: 로그인 상태 확인"""
    url = f"{admin_session.BASE_URL}/m/default.asp"
    resp = admin_session.session.get(url)
    content = resp.content.decode('euc-kr', errors='ignore')

    soup = BeautifulSoup(content, 'html.parser')
    user_info = soup.find('span', style=lambda x: x and 'color:blue' in x)

    if user_info:
        username = user_info.text.strip()
        return jsonify({
            "success": True,
            "message": f"로그인 확인됨: {username}",
            "request": {"url": url, "method": "GET"},
            "response": {"status_code": resp.status_code, "size": len(content)},
            "data": {"로그인 사용자": username}
        })
    else:
        return jsonify({
            "success": False,
            "message": "로그인 상태를 확인할 수 없습니다. Step 1을 먼저 실행하세요.",
            "request": {"url": url, "method": "GET"},
            "response": {"status_code": resp.status_code, "size": len(content)}
        })


def step3_customers():
    """Step 3: 고객 목록"""
    url = f"{admin_session.BASE_URL}/m/customer/p_custom_list.asp"
    resp = admin_session.session.get(url)
    content = resp.content.decode('euc-kr', errors='ignore')

    soup = BeautifulSoup(content, 'html.parser')
    rows = soup.find_all('tr', class_='tr_class')

    customers = []
    for row in rows[:10]:  # 최근 10명
        cells = row.find_all('td')
        if len(cells) >= 4:
            no = cells[0].text.strip()
            name_link = cells[1].find('a')
            name = name_link.text.strip() if name_link else cells[1].text.strip()
            phone = cells[2].text.strip()
            address = cells[3].text.strip()[:30]
            customers.append({
                "번호": no,
                "이름": name,
                "휴대폰": phone,
                "주소": address + "..."
            })

    return jsonify({
        "success": len(customers) > 0,
        "message": f"총 {len(rows)}명의 고객 조회됨 (상위 10명 표시)",
        "request": {"url": url, "method": "GET"},
        "response": {"status_code": resp.status_code, "size": len(content)},
        "data": customers
    })


def step4_customer_form():
    """Step 4: 고객 등록 폼"""
    url = f"{admin_session.BASE_URL}/m/customer/p_custom_regist.asp"
    resp = admin_session.session.get(url)
    content = resp.content.decode('euc-kr', errors='ignore')

    soup = BeautifulSoup(content, 'html.parser')
    form = soup.find('form', id='frm_custom')

    if form:
        fields = {}
        fields["action"] = form.get('action')
        fields["method"] = form.get('method')

        input_fields = []
        for inp in form.find_all('input'):
            name = inp.get('name', '')
            type_ = inp.get('type', 'text')
            if name and type_ != 'hidden':
                input_fields.append(f"{name} ({type_})")

        for ta in form.find_all('textarea'):
            name = ta.get('name', '')
            if name:
                input_fields.append(f"{name} (textarea)")

        return jsonify({
            "success": True,
            "message": "고객 등록 폼 구조 분석 완료",
            "request": {"url": url, "method": "GET"},
            "response": {"status_code": resp.status_code, "size": len(content)},
            "data": {
                "Form Action": fields["action"],
                "Form Method": fields["method"],
                "입력 필드": ", ".join(input_fields)
            }
        })
    else:
        return jsonify({
            "success": False,
            "message": "폼을 찾을 수 없습니다",
            "request": {"url": url, "method": "GET"},
            "response": {"status_code": resp.status_code, "size": len(content)}
        })


def step5_orders():
    """Step 5: 주문 목록"""
    url = f"{admin_session.BASE_URL}/m/customer/p_order_list.asp"
    resp = admin_session.session.get(url)
    content = resp.content.decode('euc-kr', errors='ignore')

    soup = BeautifulSoup(content, 'html.parser')
    rows = soup.find_all('tr', class_='tr_class')

    orders = []
    for row in rows[:10]:
        cells = row.find_all('td')
        if len(cells) >= 5:
            name_link = cells[0].find('a')
            name = name_link.text.strip() if name_link else cells[0].text.strip()

            # 주문번호 추출
            href = name_link.get('href', '') if name_link else ''
            order_idx = ''
            if 'g_goods_idx=' in href:
                order_idx = href.split('g_goods_idx=')[1].split('&')[0]

            product = cells[1].get_text(separator=' ', strip=True)[:40]
            qty = cells[2].text.strip()
            total = cells[3].text.strip()

            orders.append({
                "주문번호": order_idx,
                "고객명": name,
                "상품": product + "...",
                "수량": qty,
                "합계": total
            })

    # 첫 번째 주문 ID 저장 (Step 6용)
    if orders:
        app.config['LAST_ORDER_IDX'] = orders[0]['주문번호']

    return jsonify({
        "success": len(orders) > 0,
        "message": f"총 {len(rows)}건의 주문 조회됨 (상위 10건 표시)",
        "request": {"url": url, "method": "GET"},
        "response": {"status_code": resp.status_code, "size": len(content)},
        "data": orders
    })


def step6_order_detail():
    """Step 6: 주문 상세"""
    order_idx = app.config.get('LAST_ORDER_IDX', '545939')
    url = f"{admin_session.BASE_URL}/m/customer/p_order_view.asp?g_goods_idx={order_idx}"
    resp = admin_session.session.get(url)
    content = resp.content.decode('euc-kr', errors='ignore')

    soup = BeautifulSoup(content, 'html.parser')
    tables = soup.find_all('table', class_='table_css')

    order_info = {}
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            ths = row.find_all('th')
            tds = row.find_all('td')
            for th, td in zip(ths, tds):
                label = th.text.strip()
                value = td.text.strip()
                if label and value:
                    order_info[label] = value[:50]

    return jsonify({
        "success": len(order_info) > 0,
        "message": f"주문번호 {order_idx}의 상세 정보 조회 완료",
        "request": {"url": url, "method": "GET"},
        "response": {"status_code": resp.status_code, "size": len(content)},
        "data": order_info
    })


def step7_order_form():
    """Step 7: 주문서 작성 폼"""
    # 첫 번째 고객으로 주문서 폼 열기
    url = f"{admin_session.BASE_URL}/m/customer/p_order_regist.asp?c_goods_idx=100601&c_name=테스트&m_panmae_gubun=E&c_panmae_m_id=JAEHONG86"
    resp = admin_session.session.get(url)
    content = resp.content.decode('euc-kr', errors='ignore')

    soup = BeautifulSoup(content, 'html.parser')

    # 카테고리 옵션 추출
    categories = []
    cate_select = soup.find('select', {'name': 'cate_idx[]'})
    if cate_select:
        for opt in cate_select.find_all('option'):
            val = opt.get('value', '')
            text = opt.text.strip()
            if val:
                categories.append(f"{val}: {text}")

    # 상품 옵션 추출
    products = []
    prod_select = soup.find('select', {'name': 'g_article_idx[]'})
    if prod_select:
        for opt in prod_select.find_all('option')[:10]:
            val = opt.get('value', '')
            text = opt.text.strip()
            if val and val != '0':
                products.append(f"{val}: {text}")

    # 폼 필드 추출
    form_fields = []
    for inp in soup.find_all('input'):
        name = inp.get('name', '')
        if name and not name.endswith('[]'):
            form_fields.append(name)

    return jsonify({
        "success": len(categories) > 0,
        "message": f"주문서 폼 분석 완료 - {len(categories)}개 카테고리, {len(products)}개 상품 옵션",
        "request": {"url": url, "method": "GET"},
        "response": {"status_code": resp.status_code, "size": len(content)},
        "data": {
            "카테고리 목록": categories[:10],
            "상품 옵션 (첫 10개)": products,
            "폼 필드": form_fields[:15]
        }
    })


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🔧 Admin 연동 테스트 웹 인터페이스")
    print("   http://127.0.0.1:5001 에서 확인하세요")
    print("="*60 + "\n")
    app.run(host='127.0.0.1', port=5001, debug=True)
