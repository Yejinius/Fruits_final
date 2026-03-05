# Young Fresh Mall 배포 가이드

## 1. OpenClaw 맥으로 프로젝트 이전

```bash
# 이 머신에서 (git push)
cd /Users/ivan/PycharmProjects/Fruits_final
git add -A
git commit -m "배포 준비: .env 분리, Gunicorn 설정, 배포 스크립트"
git push origin main

# OpenClaw 맥에서 (git clone)
cd ~
git clone <repo-url> Fruits_final
cd Fruits_final

# 가상환경 + 의존성
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env 설정 (.env.example 복사 후 값 입력)
cp .env.example .env
nano .env   # API 키, 비밀번호 입력

# DB 초기화 + 크롤링
python -c "from models import init_db; init_db()"
python main.py all --no-images
```

## 2. 도메인 구매

추천 도메인 등록 업체:
- **Cloudflare Registrar** (최저가, 마진 없음, 연 $10~12)
- Namecheap, 가비아

도메인 예시: `youngfresh.kr`, `youngfresh.shop`, `youngfreshmall.com`

> Cloudflare Tunnel을 쓸 거면 Cloudflare에서 직접 도메인을 사는 게 DNS 설정이 가장 간편

## 3. Cloudflare Tunnel 설정

### 3-1. Cloudflare 계정 + 도메인 등록
1. https://dash.cloudflare.com 회원가입
2. 도메인 추가 (또는 Cloudflare에서 구매)
3. 네임서버를 Cloudflare로 변경 (타사 구매 시)

### 3-2. cloudflared 설치 (OpenClaw 맥)
```bash
brew install cloudflared

# Cloudflare 로그인
cloudflared tunnel login
# → 브라우저가 열리면 도메인 선택 후 인증

# 터널 생성
cloudflared tunnel create youngfresh

# 터널 설정 파일 생성
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: youngfresh
credentials-file: /Users/<username>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: youngfresh.kr
    service: http://127.0.0.1:5000
  - service: http_status:404
EOF

# DNS 레코드 연결
cloudflared tunnel route dns youngfresh youngfresh.kr

# 터널 실행 (테스트)
cloudflared tunnel run youngfresh
```

### 3-3. 자동 시작 (macOS LaunchAgent)
```bash
# Cloudflare Tunnel 서비스 등록
cloudflared service install

# 또는 수동 LaunchAgent
cat > ~/Library/LaunchAgents/com.cloudflare.tunnel.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cloudflare.tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/cloudflared</string>
        <string>tunnel</string>
        <string>run</string>
        <string>youngfresh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.cloudflare.tunnel.plist
```

## 4. Flask 프로덕션 서버 실행

```bash
# 프로덕션 모드로 실행
cd ~/Fruits_final
FLASK_ENV=production ./start.sh

# 또는 직접 Gunicorn
source venv/bin/activate
gunicorn -c gunicorn.conf.py app:app
```

### 자동 시작 (macOS LaunchAgent)
```bash
cat > ~/Library/LaunchAgents/com.youngfresh.mall.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youngfresh.mall</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/<username>/Fruits_final/start.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/<username>/Fruits_final</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>FLASK_ENV</key>
        <string>production</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/<username>/Fruits_final/data/server.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/<username>/Fruits_final/data/server.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.youngfresh.mall.plist
```

## 5. 크롤링 자동 실행 (1시간 주기)

```bash
# crontab에 추가
crontab -e

# 매 시간 크롤링 (이미지 없이)
0 * * * * cd /Users/<username>/Fruits_final && /Users/<username>/Fruits_final/venv/bin/python main.py all --no-images >> data/crawl.log 2>&1
```

## 6. .env 프로덕션 설정

```env
# 도메인 설정 후 변경
SHOPPING_MALL_URL=https://youngfresh.kr
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_SECRET_KEY=<랜덤-문자열-생성>
```

## 구조 요약

```
사용자 브라우저
    ↓ HTTPS
Cloudflare (SSL + CDN + DDoS 방어)
    ↓ Tunnel
OpenClaw 맥 (127.0.0.1:5000)
    ↓
Gunicorn → Flask (app.py)
    ↓
SQLite (data/products.db)
```
