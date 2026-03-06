"""
Telegram Bot — YoungfreshBot
- 에러 알림 실시간 전송
- 밴드 포스팅 승인/거부 인라인 버튼
- /start, /status, /pending 명령
"""
import json
import threading
import traceback
from datetime import datetime

import requests as http_requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# ── Telegram API 직접 호출 (발송용, 의존성 최소) ────────────────

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

LEVEL_EMOJI = {
    "critical": "⚫",
    "error": "🔴",
    "warning": "🟡",
    "info": "🔵",
}


def _tg_post(method, data, timeout=10):
    """Telegram Bot API 호출 (동기)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None
    try:
        resp = http_requests.post(f"{API_BASE}/{method}", json=data, timeout=timeout)
        return resp.json()
    except Exception:
        return None


def send_alert(level, category, message, detail=None):
    """에러/이벤트 알림을 텔레그램으로 전송 (non-blocking)"""
    def _send():
        emoji = LEVEL_EMOJI.get(level, "📌")
        text = f"{emoji} <b>[{level.upper()}]</b> {category}\n\n{message}"
        if detail:
            short = str(detail)[:500]
            text += f"\n\n<pre>{short}</pre>"
        text += f"\n\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        _tg_post("sendMessage", {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        })

    threading.Thread(target=_send, daemon=True).start()


def send_message(text, parse_mode="HTML", reply_markup=None):
    """일반 텍스트 메시지 전송 (동기)"""
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return _tg_post("sendMessage", data)


def send_band_approval_request(article_idx, product_name, price, preview_url, image_url=None):
    """밴드 게시 승인 요청 (인라인 버튼)"""
    text = (
        f"🎯 <b>밴드 게시 승인 요청</b>\n\n"
        f"📦 <b>{product_name}</b>\n"
        f"💰 {price:,}원\n"
        f"🔗 <a href=\"{preview_url}\">테스트 밴드 미리보기</a>\n\n"
        f"본 밴드에 게시할까요?"
    )
    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ 승인", "callback_data": f"approve_{article_idx}"},
            {"text": "❌ 거부", "callback_data": f"reject_{article_idx}"},
        ]]
    }

    # 이미지가 있으면 사진 + 캡션으로 전송
    if image_url:
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": image_url,
            "caption": text,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }
        result = _tg_post("sendPhoto", data)
        if result and result.get("ok"):
            return result
        # 사진 전송 실패 시 텍스트로 fallback

    return send_message(text, reply_markup=reply_markup)


# ── 봇 서버 (Polling 방식) ─────────────────────────────────────

class TelegramBotServer:
    """장기 실행 봇 — getUpdates polling으로 메시지/콜백 수신"""

    def __init__(self):
        self.offset = 0
        self.running = False

    def start(self):
        """봇 polling 시작 (blocking — 별도 스레드에서 호출)"""
        self.running = True
        print(f"[TelegramBot] 봇 시작 (@YoungfreshBot)")
        while self.running:
            try:
                self._poll()
            except Exception as e:
                print(f"[TelegramBot] Polling 에러: {e}")
                import time
                time.sleep(5)

    def stop(self):
        self.running = False

    def _poll(self):
        """getUpdates 한 번 호출"""
        resp = http_requests.get(
            f"{API_BASE}/getUpdates",
            params={"offset": self.offset, "timeout": 30},
            timeout=40,
        )
        data = resp.json()
        if not data.get("ok"):
            return

        for update in data.get("result", []):
            self.offset = update["update_id"] + 1
            try:
                self._handle_update(update)
            except Exception as e:
                print(f"[TelegramBot] 핸들러 에러: {e}")
                traceback.print_exc()

    def _handle_update(self, update):
        """업데이트 분기 처리"""
        if "message" in update:
            self._handle_message(update["message"])
        elif "callback_query" in update:
            self._handle_callback(update["callback_query"])

    def _handle_message(self, message):
        """텍스트 명령 처리"""
        chat_id = message["chat"]["id"]
        text = message.get("text", "")

        if text == "/start":
            self._cmd_start(chat_id)
        elif text == "/status":
            self._cmd_status(chat_id)
        elif text == "/pending":
            self._cmd_pending(chat_id)
        elif text == "/help":
            self._cmd_help(chat_id)

    def _handle_callback(self, callback):
        """인라인 버튼 콜백 처리"""
        cb_id = callback["id"]
        data = callback.get("data", "")
        chat_id = callback["message"]["chat"]["id"]
        message_id = callback["message"]["message_id"]

        if data.startswith("approve_"):
            article_idx = int(data.split("_", 1)[1])
            self._approve_band_post(cb_id, chat_id, message_id, article_idx)
        elif data.startswith("reject_"):
            article_idx = int(data.split("_", 1)[1])
            self._reject_band_post(cb_id, chat_id, message_id, article_idx)

    # ── 명령 핸들러 ──

    def _cmd_start(self, chat_id):
        _tg_post("sendMessage", {
            "chat_id": chat_id,
            "text": (
                "🍎 <b>Young Fresh Mall 알림 봇</b>\n\n"
                "명령어:\n"
                "/status — 서버 상태 확인\n"
                "/pending — 승인 대기 상품\n"
                "/help — 도움말"
            ),
            "parse_mode": "HTML",
        })

    def _cmd_status(self, chat_id):
        try:
            from models import get_session, Product, Order
            session = get_session()
            total = session.query(Product).count()
            active = session.query(Product).filter_by(is_active=True).count()
            orders = session.query(Order).count()
            pending = session.query(Order).filter_by(status="awaiting_payment").count()
            session.close()

            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    f"📊 <b>Young Fresh Mall 상태</b>\n\n"
                    f"🛍️ 상품: {active}개 활성 / {total}개 전체\n"
                    f"📋 주문: {orders}건 (미입금 {pending}건)\n"
                    f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                "parse_mode": "HTML",
            })
        except Exception as e:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": f"❌ 상태 조회 실패: {e}"})

    def _cmd_pending(self, chat_id):
        try:
            from band_poster import get_unposted_products
            products = get_unposted_products()

            if not products:
                _tg_post("sendMessage", {"chat_id": chat_id, "text": "✅ 승인 대기 상품이 없습니다."})
                return

            lines = [f"📋 <b>미게시 상품 ({len(products)}개)</b>\n"]
            for i, p in enumerate(products[:20], 1):
                lines.append(f"{i}. {p.name} ({p.price:,}원)")
            if len(products) > 20:
                lines.append(f"\n... 외 {len(products) - 20}개")

            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": "\n".join(lines),
                "parse_mode": "HTML",
            })
        except Exception as e:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": f"❌ 조회 실패: {e}"})

    def _cmd_help(self, chat_id):
        _tg_post("sendMessage", {
            "chat_id": chat_id,
            "text": (
                "📖 <b>명령어 목록</b>\n\n"
                "/status — 서버 상태 (상품 수, 주문 수)\n"
                "/pending — 밴드 미게시 상품 목록\n"
                "/help — 이 도움말\n\n"
                "밴드 승인 요청이 오면 ✅/❌ 버튼으로 응답하세요."
            ),
            "parse_mode": "HTML",
        })

    # ── 승인/거부 핸들러 ──

    def _approve_band_post(self, cb_id, chat_id, message_id, article_idx):
        """승인 → 본 밴드에 게시"""
        # 먼저 응답 (Telegram 콜백 타임아웃 방지)
        _tg_post("answerCallbackQuery", {"callback_query_id": cb_id, "text": "처리 중..."})

        # 버튼 제거 + "처리 중" 메시지
        _tg_post("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []},
        })
        _tg_post("sendMessage", {"chat_id": chat_id, "text": f"⏳ 본 밴드 게시 중... (상품 ID: {article_idx})"})

        try:
            from band_poster import band_post_confirm
            post_url = band_post_confirm(article_idx)

            if post_url:
                _tg_post("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"✅ <b>본 밴드 게시 완료!</b>\n\n🔗 {post_url}",
                    "parse_mode": "HTML",
                })
            else:
                _tg_post("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"❌ 게시 실패 (article_idx={article_idx})\nBAND_PRODUCTION_URL을 확인하세요.",
                })
        except Exception as e:
            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": f"❌ 게시 중 에러: {e}",
            })

    def _reject_band_post(self, cb_id, chat_id, message_id, article_idx):
        """거부"""
        _tg_post("answerCallbackQuery", {"callback_query_id": cb_id, "text": "거부됨"})
        _tg_post("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []},
        })
        _tg_post("sendMessage", {"chat_id": chat_id, "text": f"🚫 거부됨 (상품 ID: {article_idx})"})


# ── 글로벌 봇 인스턴스 + 스레드 시작 ──────────────────────────

_bot_server = None
_bot_thread = None


def start_bot_thread():
    """봇 polling을 백그라운드 스레드로 시작"""
    global _bot_server, _bot_thread

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TelegramBot] 토큰/챗ID 미설정 — 봇 비활성")
        return

    _bot_server = TelegramBotServer()
    _bot_thread = threading.Thread(target=_bot_server.start, daemon=True)
    _bot_thread.start()
    print("[TelegramBot] 백그라운드 스레드 시작")


def stop_bot():
    """봇 중지"""
    global _bot_server
    if _bot_server:
        _bot_server.stop()


def send_test_alert():
    """테스트 알림 전송"""
    send_alert("info", "test", "🧪 텔레그램 알림 테스트입니다! Young Fresh Mall 연동 정상.")
    print("[TelegramBot] 테스트 알림 전송 완료")


if __name__ == "__main__":
    # 단독 실행 시 봇 서버 시작
    print("YoungfreshBot 시작...")
    bot = TelegramBotServer()
    try:
        bot.start()
    except KeyboardInterrupt:
        print("\n봇 종료")
