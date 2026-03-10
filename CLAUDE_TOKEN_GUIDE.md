# Claude CLI OAuth Token 세팅 가이드 (Fruits_final)

로컬 Mac 환경에서 Claude CLI를 Flask 백엔드에서 subprocess로 호출하기 위한 장기 토큰(1년) 설정 방법.

## 개요

- Claude CLI는 기본적으로 브라우저 OAuth 인증을 사용
- `claude auth login`으로 발급된 토큰은 **8~12시간**에 만료됨
- Flask subprocess에서 호출 시 자동 갱신이 안 되므로, `setup-token`으로 발급한 장기 토큰(1년) 사용
- Anthropic API 키와 무관 — Claude Max/Pro 구독 계정의 OAuth 토큰

## 1. 토큰 발급 (로컬 터미널)

```bash
claude setup-token
```

- 브라우저가 열리고 Anthropic 계정 로그인 요청
- 인증 완료 시 터미널에 `sk-ant-oat01-...` 형태의 토큰 출력
- **유효기간: 약 1년**
- 계정: yejinius@gmail.com (Max 구독)

## 2. 토큰 저장

### Fruits_final/.env에 추가

```bash
# .env 파일에 추가 (이미 gitignored)
echo 'CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-여기에토큰' >> /Users/ivan/Fruits_final/.env
```

Flask가 `python-dotenv`로 `.env`를 자동 로드하므로, 서버 재시작 시 환경변수로 인식됨.

### 또는 shell profile에 추가 (전역 사용)

```bash
# ~/.zshrc에 추가 (모든 터미널에서 사용 가능)
echo 'export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-여기에토큰' >> ~/.zshrc
source ~/.zshrc
```

## 3. 서버 재시작

```bash
# Fruits_final 서버가 systemd/pm2로 관리되는 경우
# 현재는 수동 실행 또는 auto_pull.sh로 관리

cd /Users/ivan/Fruits_final
git pull origin main
# 서버 프로세스 재시작
```

## 4. 토큰 검증

```bash
# 토큰이 환경변수에 잘 설정되었는지 확인
echo $CLAUDE_CODE_OAUTH_TOKEN | head -c 20

# Claude CLI 동작 확인
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-... claude -p "say hello" --output-format text
```

정상이면 Claude 응답이 출력됨.

### Flask API 검증

```bash
# /api/tennis/generate 엔드포인트 테스트
curl -X POST https://youngfresh.net/api/tennis/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "players": [
      {"name": "테스트1", "gender": "M", "ntrp": 3.0},
      {"name": "테스트2", "gender": "F", "ntrp": 2.5},
      {"name": "테스트3", "gender": "M", "ntrp": 2.0},
      {"name": "테스트4", "gender": "F", "ntrp": 2.0}
    ],
    "numCourts": 1,
    "duration": 20,
    "startTime": "19:00",
    "endTime": "20:00",
    "warmup": 20,
    "wish": "혼복으로만 배치해줘"
  }'
```

## 5. 만료 시 갱신 절차

1. 로컬 터미널에서 `claude setup-token` 재발급
2. `.env` 파일의 `CLAUDE_CODE_OAUTH_TOKEN=` 값 교체
3. 서버 재시작
4. `/api/tennis/generate` 테스트로 확인

## 6. 자동 갱신 (선택)

토큰 만료 1개월 전 리마인더 설정:
- OpenClaw cron job으로 11개월 후 알림
- 또는 MEMORY.md에 만료 예상일 기록

## 파일 위치

- 토큰 저장: `/Users/ivan/Fruits_final/.env` (gitignored)
- 이 가이드: `/Users/ivan/Fruits_final/CLAUDE_TOKEN_GUIDE.md`
- Flask 서버: `/Users/ivan/Fruits_final/app.py` (`/api/tennis/generate`)

## 주의사항

- `.env`는 gitignored — 절대 커밋하지 말 것
- 토큰은 Anthropic 계정(yejinius@gmail.com)에 바인딩됨
- 계정 변경이나 구독 해지 시 재발급 필요
- 토큰 노출 시 즉시 `claude auth logout` 후 재발급
