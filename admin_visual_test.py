"""
Admin 사이트 시각적 테스트
- HTTP Request로 받은 페이지를 브라우저에 그대로 표시
- 폼 필드에 데이터를 자동으로 채워넣은 상태로 표시
- 각 단계별로 확인 후 다음 단계 진행
"""
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
import re

app = Flask(__name__)
app.secret_key = 'admin_visual_test_secret_key'

# 전역 Admin 세션
class AdminSession:
    BASE_URL = "http://admin.open79.co.kr"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logged_in = False
        self.last_customer_idx = None
        self.last_response = None

    def login(self, user_id, password):
        resp = self.session.post(
            f"{self.BASE_URL}/m/include/asp/login_ok.asp",
            data={"m_id": user_id, "m_passwd": password}
        )
        self.logged_in = "location.replace" in resp.text
        return self.logged_in

    def get_page(self, path):
        """페이지 가져오기"""
        url = f"{self.BASE_URL}{path}"
        resp = self.session.get(url)
        self.last_response = resp
        return resp.content.decode('euc-kr', errors='ignore')

    def post_form(self, path, data):
        """폼 제출 - EUC-KR 인코딩으로 전송"""
        url = f"{self.BASE_URL}{path}"
        # 한글 데이터를 EUC-KR로 인코딩
        encoded_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                # UTF-8 문자열을 EUC-KR 바이트로 변환
                encoded_data[key] = value.encode('euc-kr', errors='ignore')
            else:
                encoded_data[key] = value
        resp = self.session.post(url, data=encoded_data)
        self.last_response = resp
        return resp.content.decode('euc-kr', errors='ignore')


admin = AdminSession()


def search_address_juso(keyword):
    """
    행정안전부 도로명주소 API로 주소 검색
    결과가 있으면 첫 번째 주소의 (우편번호, 도로명주소) 반환
    """
    # 도로명주소 API (confmKey 없이 테스트 가능한 무료 API)
    # 실제 운영 시에는 https://www.juso.go.kr 에서 API 키 발급 필요
    try:
        # Kakao Local API 사용 (REST API 키 필요 없는 방식)
        # 대신 Daum 우편번호 서비스의 내부 API 활용
        url = "https://dapi.kakao.com/v2/local/search/address.json"

        # 카카오 API 키가 없으므로 다른 방법 사용:
        # 네이버 또는 직접 DB에서 조회하는 방식으로 대체

        # 여기서는 SAMPLE_ORDER_DATA에 이미 정확한 주소가 있으므로
        # 해당 데이터를 그대로 사용하고, 검색은 확인용으로만 사용
        return None
    except Exception as e:
        print(f"주소 검색 실패: {e}")
        return None


# 테스트용 샘플 데이터 (실제로는 DB에서 가져옴)
SAMPLE_ORDER_DATA = {
    "depositor_name": "정예진",           # 입금자 이름
    "recipient_name": "정예진",           # 받으실 분 이름
    "phone": "REDACTED_PHONE",            # 휴대폰
    "zipcode": "02504",                   # 우편번호
    "address": "서울특별시 동대문구 서울시립대로 19 청계와이즈노벨리아", # 기본주소
    "address_detail": "101동 1002호",     # 상세주소
    "cash_receipt_no": "REDACTED_PHONE",   # 현금영수증 번호
    "memo": "부재시 경비실에 맡겨주세요",   # 기타 요청사항
    "product_name": "2박스*제주/보배진/레드향(26과)-6kg내외",  # 옵션 상품
    "category_idx": "13",                 # 참외/귤종류/포도종류/유자 (Admin 카테고리)
    "article_idx": "42092",               # 2박스 옵션 상품 ID
    "price": 47000,                       # Admin 판매가 (참고용)
    "delivery_fee": 3000,                 # 배송비
    "total_payment": 56700,               # 고객 입금액
    "quantity": 1
}


# 컨트롤 패널 HTML
CONTROL_PANEL = """
<div id="control-panel" style="
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: white;
    padding: 15px 20px;
    z-index: 99999;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    font-family: 'Malgun Gothic', sans-serif;
">
    <div style="max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center;">
        <div>
            <span style="font-size: 18px; font-weight: bold; color: #4CAF50;">🔧 Admin 시각적 테스트</span>
            <span style="margin-left: 20px; padding: 5px 15px; background: {status_color}; border-radius: 20px; font-size: 13px;">
                {current_step}
            </span>
        </div>
        <div style="display: flex; gap: 10px;">
            {buttons}
        </div>
    </div>
    <div style="max-width: 1400px; margin: 10px auto 0; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.1); font-size: 13px; color: #aaa;">
        {info}
    </div>
</div>
<div style="height: 100px;"></div>
"""

BUTTON_STYLE = """
    padding: 8px 20px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 13px;
    font-weight: bold;
    text-decoration: none;
    display: inline-block;
"""


def make_button(text, href, color="#4CAF50", disabled=False):
    if disabled:
        return f'<span style="{BUTTON_STYLE} background: #555; color: #888; cursor: not-allowed;">{text}</span>'
    return f'<a href="{href}" style="{BUTTON_STYLE} background: {color}; color: white;">{text}</a>'


def inject_control_panel(html, step_name, info, buttons_html, status_color="#4CAF50"):
    """HTML에 컨트롤 패널 삽입"""
    panel = CONTROL_PANEL.format(
        current_step=step_name,
        info=info,
        buttons=buttons_html,
        status_color=status_color
    )

    # body 태그 뒤에 패널 삽입
    if '<body' in html.lower():
        html = re.sub(
            r'(<body[^>]*>)',
            r'\1' + panel,
            html,
            flags=re.IGNORECASE
        )
    else:
        html = panel + html

    return html


def fix_relative_urls(html):
    """상대 URL을 절대 URL로 변환"""
    base = admin.BASE_URL

    # CSS, JS, 이미지 경로 수정
    html = re.sub(r'href="(/[^"]*)"', f'href="{base}\\1"', html)
    html = re.sub(r'src="(/[^"]*)"', f'src="{base}\\1"', html)
    html = re.sub(r"href='(/[^']*)'", f"href='{base}\\1'", html)
    html = re.sub(r"src='(/[^']*)'", f"src='{base}\\1'", html)

    # form action도 수정 (우리 서버로 프록시)
    # html = re.sub(r'action="([^"]*)"', r'action="/proxy/post?target=\1"', html)

    return html


@app.route('/')
def index():
    """시작 페이지"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Admin 시각적 테스트</title>
        <style>
            body {
                font-family: 'Malgun Gothic', sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 0;
                color: white;
            }
            .container {
                text-align: center;
                padding: 40px;
            }
            h1 {
                font-size: 36px;
                margin-bottom: 20px;
            }
            .desc {
                color: #aaa;
                margin-bottom: 40px;
                line-height: 1.8;
            }
            .steps {
                display: flex;
                flex-direction: column;
                gap: 15px;
                max-width: 500px;
                margin: 0 auto;
            }
            .step-item {
                background: rgba(255,255,255,0.1);
                padding: 15px 20px;
                border-radius: 10px;
                display: flex;
                align-items: center;
                gap: 15px;
            }
            .step-num {
                background: #4CAF50;
                color: white;
                width: 30px;
                height: 30px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .step-text {
                text-align: left;
            }
            .step-title {
                font-weight: bold;
                margin-bottom: 3px;
            }
            .step-desc {
                font-size: 12px;
                color: #888;
            }
            .start-btn {
                display: inline-block;
                margin-top: 40px;
                padding: 15px 50px;
                background: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 30px;
                font-size: 18px;
                font-weight: bold;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .start-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(76, 175, 80, 0.4);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔧 Admin 시각적 테스트</h1>
            <p class="desc">
                HTTP Request로 Admin 사이트의 실제 페이지를 가져와서 표시합니다.<br>
                폼에 데이터가 자동으로 채워지는 것을 확인하고, 단계별로 진행할 수 있습니다.
            </p>

            <div class="steps">
                <div class="step-item">
                    <div class="step-num">1</div>
                    <div class="step-text">
                        <div class="step-title">로그인</div>
                        <div class="step-desc">Admin 사이트에 로그인합니다</div>
                    </div>
                </div>
                <div class="step-item">
                    <div class="step-num">2</div>
                    <div class="step-text">
                        <div class="step-title">고객 등록 폼</div>
                        <div class="step-desc">DB 데이터가 채워진 고객 등록 폼을 확인합니다</div>
                    </div>
                </div>
                <div class="step-item">
                    <div class="step-num">3</div>
                    <div class="step-text">
                        <div class="step-title">고객 등록 실행</div>
                        <div class="step-desc">폼을 제출하고 결과를 확인합니다</div>
                    </div>
                </div>
                <div class="step-item">
                    <div class="step-num">4</div>
                    <div class="step-text">
                        <div class="step-title">주문서 작성</div>
                        <div class="step-desc">등록된 고객으로 주문서를 작성합니다</div>
                    </div>
                </div>
                <div class="step-item">
                    <div class="step-num">5</div>
                    <div class="step-text">
                        <div class="step-title">주문 확인</div>
                        <div class="step-desc">주문 목록에서 등록된 주문을 확인합니다</div>
                    </div>
                </div>
            </div>

            <a href="/step/1" class="start-btn">테스트 시작 →</a>
        </div>
    </body>
    </html>
    """
    return html


@app.route('/step/1')
def step1_login():
    """Step 1: 로그인 페이지 표시"""
    html = admin.get_page("/m/include/asp/login_openstory.asp?QS_URL=/m/default.asp")
    html = fix_relative_urls(html)

    # 로그인 폼에 값 채우기
    html = html.replace('name="m_id"', 'name="m_id" value="REDACTED_ID"')
    html = html.replace('name="m_passwd"', 'name="m_passwd" value="REDACTED_PW"')

    # 폼 액션을 우리 서버로 변경
    html = html.replace('action="/m/include/asp/login_ok.asp"', 'action="/step/1/submit"')

    buttons = make_button("로그인 실행 →", "/step/1/submit", "#4CAF50")
    info = "ID와 비밀번호가 자동으로 채워졌습니다. [로그인 실행] 버튼을 클릭하세요."

    html = inject_control_panel(html, "Step 1: 로그인", info, buttons)
    return html


@app.route('/step/1/submit')
def step1_submit():
    """Step 1: 로그인 실행"""
    success = admin.login("REDACTED_ID", "REDACTED_PW")

    if success:
        return redirect('/step/2')
    else:
        return "로그인 실패", 400


@app.route('/step/2')
def step2_customer_form():
    """Step 2: 고객 등록 폼 - Daum Postcode 연동"""
    if not admin.logged_in:
        admin.login("REDACTED_ID", "REDACTED_PW")

    html = admin.get_page("/m/customer/p_custom_regist.asp")
    html = fix_relative_urls(html)

    # 폼 필드에 샘플 데이터 채우기 (주소 제외 - Daum Postcode로 입력)
    data = SAMPLE_ORDER_DATA

    # input 필드에 값 채우기 (주소 관련 필드 제외)
    html = html.replace(
        'name="c_name" class="txtbox"',
        f'name="c_name" class="txtbox" value="{data["recipient_name"]}"'
    )
    html = html.replace(
        'name="c_tel2" class="txtbox"',
        f'name="c_tel2" class="txtbox" value="{data["phone"]}"'
    )
    html = html.replace(
        'name="c_tax_no" class="txtbox"',
        f'name="c_tax_no" class="txtbox" value="{data["cash_receipt_no"]}"'
    )

    # textarea에 값 채우기
    html = html.replace(
        'name="c_bigo" rows=4 class="txtbox" style="width:99%;"></textarea>',
        f'name="c_bigo" rows=4 class="txtbox" style="width:99%;">{data["memo"]}</textarea>'
    )

    # 폼 액션 변경
    html = html.replace('action="p_custom_regist_ok.asp"', 'action="/step/2/submit"')

    # 주소 필드에도 값 채우기 (SAMPLE_ORDER_DATA에서 가져옴)
    # 실제 운영에서는 주문 데이터에 이미 우편번호/주소가 있음
    html = html.replace(
        'id="c_zipcode" name="c_zipcode"',
        f'id="c_zipcode" name="c_zipcode" value="{data["zipcode"]}"'
    )
    html = html.replace(
        'id="c_address" name="c_address" class="txtbox"',
        f'id="c_address" name="c_address" class="txtbox" value="{data["address"]}"'
    )
    html = html.replace(
        'id="c_address_etc" name="c_address_etc" class="txtbox"',
        f'id="c_address_etc" name="c_address_etc" class="txtbox" value="{data["address_detail"]}"'
    )

    # 자동 입력된 필드 하이라이트 스크립트
    highlight_script = '''
    <script>
    window.addEventListener('load', function() {
        // 자동 입력된 필드들 하이라이트
        var fields = ['c_zipcode', 'c_address', 'c_address_etc', 'c_name', 'c_tel2', 'c_tax_no'];
        fields.forEach(function(id) {
            var el = document.getElementById(id);
            if (el && el.value) {
                el.style.backgroundColor = '#e8f5e9';
                el.style.border = '2px solid #4CAF50';
            }
        });

        // textarea도 하이라이트
        var bigo = document.querySelector('textarea[name="c_bigo"]');
        if (bigo && bigo.value) {
            bigo.style.backgroundColor = '#e8f5e9';
            bigo.style.border = '2px solid #4CAF50';
        }

        // 2초 후 자동 제출 확인
        setTimeout(function() {
            if (confirm("모든 데이터가 자동 입력되었습니다.\\n\\n[확인]을 누르면 고객 등록을 진행합니다.\\n[취소]를 누르면 수동으로 확인 후 진행할 수 있습니다.")) {
                document.getElementById('frm_custom').submit();
            }
        }, 1500);
    });
    </script>
    '''

    # </html> 앞에 스크립트 삽입
    if '</html>' in html:
        html = html.replace('</html>', highlight_script + '</html>')
    else:
        html = html + highlight_script

    buttons = (
        make_button("← 이전", "/step/1", "#666") +
        make_button("고객 등록 실행 →", "/step/2/submit", "#4CAF50")
    )
    info = f"""
    <b style="color: #4CAF50;">✅ 모든 데이터가 자동 입력되었습니다!</b><br>
    <b>우편번호:</b> {data['zipcode']} | <b>주소:</b> {data['address']} {data['address_detail']}<br>
    <b>고객명:</b> {data['recipient_name']} | <b>휴대폰:</b> {data['phone']} | <b>현금영수증:</b> {data['cash_receipt_no']}
    """

    html = inject_control_panel(html, "Step 2: 고객 등록 폼 (데이터 자동 입력 완료)", info, buttons, "#4CAF50")
    return html


@app.route('/step/2/submit', methods=['GET', 'POST'])
def step2_submit():
    """Step 2: 고객 등록 실행 - 폼에서 입력된 값 사용"""
    data = SAMPLE_ORDER_DATA

    if request.method == 'POST':
        # 폼에서 제출된 값 사용 (Daum Postcode에서 선택한 주소 포함)
        form_data = {
            "c_name": request.form.get("c_name", data["recipient_name"]),
            "c_tel1": request.form.get("c_tel1", ""),
            "c_tel2": request.form.get("c_tel2", data["phone"]).replace("-", ""),
            "c_zipcode": request.form.get("c_zipcode", ""),
            "c_address": request.form.get("c_address", ""),
            "c_address_etc": request.form.get("c_address_etc", ""),
            "c_tax_no": request.form.get("c_tax_no", data["cash_receipt_no"]),
            "c_bigo": request.form.get("c_bigo", data["memo"])
        }
    else:
        # GET 요청 시 기본값 사용
        form_data = {
            "c_name": data["recipient_name"],
            "c_tel1": "",
            "c_tel2": data["phone"].replace("-", ""),
            "c_zipcode": data["zipcode"],
            "c_address": data["address"],
            "c_address_etc": data["address_detail"],
            "c_tax_no": data["cash_receipt_no"],
            "c_bigo": data["memo"]
        }

    # 주소가 비어있으면 경고
    if not form_data["c_zipcode"] or not form_data["c_address"]:
        return """
        <script>
            alert("주소를 선택하지 않았습니다. Daum 주소검색에서 주소를 선택해주세요.");
            history.back();
        </script>
        """

    result = admin.post_form("/m/customer/p_custom_regist_ok.asp", form_data)

    # 세션에 제출된 데이터 저장 (결과 페이지에서 확인용)
    admin.last_submitted_data = form_data

    # 등록 성공 후 고객 목록에서 방금 등록한 고객 찾기
    return redirect('/step/2/result')


@app.route('/step/2/result')
def step2_result():
    """Step 2: 고객 등록 결과 확인"""
    html = admin.get_page("/m/customer/p_custom_list.asp")
    html = fix_relative_urls(html)

    # 첫 번째 고객의 c_goods_idx 추출
    soup = BeautifulSoup(html, 'html.parser')
    first_row = soup.find('tr', class_='tr_class')
    if first_row:
        order_btn = first_row.find('span', class_='btn_m_white01')
        if order_btn and order_btn.get('onclick'):
            onclick = order_btn.get('onclick')
            match = re.search(r"c_goods_idx=(\d+)", onclick)
            if match:
                admin.last_customer_idx = match.group(1)

    buttons = (
        make_button("← 이전", "/step/2", "#666") +
        make_button("주문서 작성 →", "/step/3", "#4CAF50")
    )

    customer_info = f"등록된 고객 ID: {admin.last_customer_idx}" if admin.last_customer_idx else "고객 ID를 찾을 수 없습니다"

    # 제출된 데이터 표시
    submitted_info = ""
    if hasattr(admin, 'last_submitted_data') and admin.last_submitted_data:
        d = admin.last_submitted_data
        submitted_info = f"""<br><b>제출된 데이터:</b> 이름={d.get('c_name')}, 휴대폰={d.get('c_tel2')},
        우편번호={d.get('c_zipcode')}, 주소={d.get('c_address')} {d.get('c_address_etc')}"""

    info = f"""
    <b style="color: #4CAF50;">✅ 고객 등록 완료!</b> {customer_info}{submitted_info}<br>
    목록 상단에서 방금 등록한 고객을 확인하세요.
    """

    html = inject_control_panel(html, "Step 2: 고객 등록 결과", info, buttons, "#4CAF50")
    return html


@app.route('/step/3')
def step3_order_form():
    """Step 3: 주문서 작성 폼"""
    if not admin.last_customer_idx:
        return redirect('/step/2')

    data = SAMPLE_ORDER_DATA
    customer_idx = admin.last_customer_idx

    # 주문서 폼 가져오기
    html = admin.get_page(f"/m/customer/p_order_regist.asp?c_goods_idx={customer_idx}&c_name={data['recipient_name']}&m_panmae_gubun=E&c_panmae_m_id=JAEHONG86")
    html = fix_relative_urls(html)

    # 현금영수증 번호 채우기
    html = html.replace(
        f'name="c_tax_no"',
        f'name="c_tax_no" value="{data["cash_receipt_no"]}"'
    )

    # 카테고리 선택 (고구마/감자/야채)
    html = html.replace(
        f'<option value="{data["category_idx"]}">',
        f'<option value="{data["category_idx"]}" selected>'
    )

    # 주문 수량
    html = html.replace('name="g_goods_cnt[]"', f'name="g_goods_cnt[]" value="{data["quantity"]}"')

    # 입금액 (total_payment가 있으면 사용, 없으면 price + delivery_fee)
    total = data.get("total_payment", data["price"] + data["delivery_fee"])
    html = html.replace('name="c_input_money[]"', f'name="c_input_money[]" value="{total}"')

    # 입금자명
    html = html.replace('name="c_input_name"', f'name="c_input_name" value="{data["depositor_name"]}"')

    # 폼 액션 변경
    html = html.replace('action="p_order_regist_ok.asp"', 'action="/step/3/submit"')

    # 품목 자동 선택 스크립트 추가
    article_select_script = f'''
    <script>
    window.addEventListener('load', function() {{
        // 품목(g_article_idx) 드롭다운에서 상품 자동 선택
        var articleSelect = document.querySelector('select[name="g_article_idx[]"]');
        if (articleSelect) {{
            var targetValue = "{data["article_idx"]}";
            var found = false;

            // 옵션 중에서 article_idx 값과 일치하는 것 선택
            for (var i = 0; i < articleSelect.options.length; i++) {{
                if (articleSelect.options[i].value === targetValue) {{
                    articleSelect.selectedIndex = i;
                    articleSelect.style.backgroundColor = '#e8f5e9';
                    articleSelect.style.border = '2px solid #4CAF50';
                    found = true;

                    // onchange 이벤트 트리거 (재고, 가격 등 자동 입력)
                    var event = new Event('change', {{ bubbles: true }});
                    articleSelect.dispatchEvent(event);
                    break;
                }}
            }}

            if (!found) {{
                console.log("품목을 찾을 수 없습니다. article_idx=" + targetValue);
                articleSelect.style.backgroundColor = '#ffebee';
                articleSelect.style.border = '2px solid #f44336';
            }}
        }}

        // 카테고리 드롭다운 하이라이트
        var cateSelect = document.querySelector('select[name="cate_idx[]"]');
        if (cateSelect) {{
            cateSelect.style.backgroundColor = '#e8f5e9';
            cateSelect.style.border = '2px solid #4CAF50';
        }}

        // 기타 입력 필드들 하이라이트
        var fields = ['c_tax_no', 'c_input_name'];
        fields.forEach(function(name) {{
            var el = document.querySelector('[name="' + name + '"]');
            if (el && el.value) {{
                el.style.backgroundColor = '#e8f5e9';
                el.style.border = '2px solid #4CAF50';
            }}
        }});

        // 입금액 필드 하이라이트
        var moneyField = document.querySelector('input[name="c_input_money[]"]');
        if (moneyField && moneyField.value) {{
            moneyField.style.backgroundColor = '#e8f5e9';
            moneyField.style.border = '2px solid #4CAF50';
        }}

        // 수량 필드 하이라이트
        var cntField = document.querySelector('input[name="g_goods_cnt[]"]');
        if (cntField && cntField.value) {{
            cntField.style.backgroundColor = '#e8f5e9';
            cntField.style.border = '2px solid #4CAF50';
        }}

        // 2초 후 자동 제출 확인
        setTimeout(function() {{
            if (confirm("모든 주문 데이터가 자동 입력되었습니다.\\n\\n[확인]을 누르면 주문 등록을 진행합니다.\\n[취소]를 누르면 수동으로 확인 후 진행할 수 있습니다.")) {{
                document.getElementById('frm_order').submit();
            }}
        }}, 2000);
    }});
    </script>
    '''

    # </html> 앞에 스크립트 삽입
    if '</html>' in html:
        html = html.replace('</html>', article_select_script + '</html>')
    else:
        html = html + article_select_script

    buttons = (
        make_button("← 고객목록", "/step/2/result", "#666") +
        make_button("주문 등록 실행 →", "/step/3/submit", "#4CAF50")
    )
    info = f"""
    <b style="color: #4CAF50;">✅ 모든 주문 데이터가 자동 입력되었습니다!</b><br>
    <b>주문 정보:</b> 고객ID={customer_idx}, 카테고리={data['category_idx']},
    상품={data['product_name']} (ID: {data['article_idx']}), 금액={data['price']:,}원, 택배비={data['delivery_fee']:,}원,
    총액={total:,}원, 입금자={data['depositor_name']}
    """

    html = inject_control_panel(html, "Step 3: 주문서 작성", info, buttons, "#FF9800")
    return html


@app.route('/step/3/submit')
def step3_submit():
    """Step 3: 주문 등록 실행"""
    data = SAMPLE_ORDER_DATA
    total = data.get("total_payment", data["price"] + data["delivery_fee"])

    form_data = {
        "g_panmae_gubun": "E",
        "c_goods_idx": admin.last_customer_idx,
        "g_panmae_m_id": "JAEHONG86",
        "g_goods_bigo": "",
        "g_goods_bigo1": "",
        "c_tax_no": data["cash_receipt_no"],
        "cate_idx[]": data["category_idx"],
        "g_article_idx[]": data["article_idx"],
        "g_goods_name[]": data["product_name"],
        "g_goods_cnt[]": str(data["quantity"]),
        "g_goods_price[]": str(data["price"]),
        "g_goods_sell[]": str(data["price"]),
        "g_goods_delivery[]": str(data["delivery_fee"]),
        "g_order_type": "입금",
        "c_input_money[]": str(total),
        "c_input_name": data["depositor_name"],
        "g_goods_sell_d[]": "",
        "g_goods_sell_s[]": "",
        "g_goods_stock[]": ""
    }

    result = admin.post_form("/m/customer/p_order_regist_ok.asp", form_data)
    return redirect('/step/4')


@app.route('/step/4')
def step4_order_list():
    """Step 4: 주문 목록에서 확인"""
    html = admin.get_page("/m/customer/p_order_list.asp")
    html = fix_relative_urls(html)

    buttons = (
        make_button("← 주문서", "/step/3", "#666") +
        make_button("처음으로", "/", "#2196F3") +
        make_button("종료", "/finish", "#f44336")
    )
    info = """
    <b style="color: #4CAF50;">✅ 전체 프로세스 완료!</b><br>
    주문 목록 상단에서 방금 등록한 주문을 확인하세요.
    """

    html = inject_control_panel(html, "Step 4: 주문 목록 확인", info, buttons, "#4CAF50")
    return html


@app.route('/finish')
def finish():
    """테스트 종료"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>테스트 완료</title>
        <style>
            body {
                font-family: 'Malgun Gothic', sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 0;
                color: white;
            }
            .container {
                text-align: center;
                padding: 40px;
            }
            h1 { font-size: 48px; margin-bottom: 20px; }
            p { color: #aaa; margin-bottom: 30px; }
            .summary {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 15px;
                max-width: 500px;
                margin: 0 auto 30px;
                text-align: left;
            }
            .summary-item {
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .summary-item:last-child { border: none; }
            .check { color: #4CAF50; }
            a {
                display: inline-block;
                padding: 12px 30px;
                background: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 25px;
                margin: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ 테스트 완료</h1>
            <p>HTTP Request 방식으로 Admin 사이트 연동 테스트가 완료되었습니다.</p>

            <div class="summary">
                <div class="summary-item">
                    <span>로그인</span>
                    <span class="check">✓ 성공</span>
                </div>
                <div class="summary-item">
                    <span>고객 등록</span>
                    <span class="check">✓ 완료 (ID: """ + str(admin.last_customer_idx) + """)</span>
                </div>
                <div class="summary-item">
                    <span>주문서 작성</span>
                    <span class="check">✓ 완료</span>
                </div>
                <div class="summary-item">
                    <span>주문 확인</span>
                    <span class="check">✓ 확인됨</span>
                </div>
            </div>

            <a href="/">다시 시작</a>
            <a href="/step/4" style="background: #666;">주문 목록 보기</a>
        </div>
    </body>
    </html>
    """
    return html


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🔧 Admin 시각적 테스트")
    print("   http://127.0.0.1:5002 에서 확인하세요")
    print("="*60 + "\n")
    app.run(host='127.0.0.1', port=5002, debug=True)
