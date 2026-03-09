"""
Telegram Bot — YoungfreshBot
- 에러 알림 실시간 전송
- 밴드 포스팅 승인/거부 인라인 버튼
- /start, /status, /pending 명령
"""
import json
import time
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


_alert_targets = None

def _get_alert_targets():
    """알림 대상 chat_id 목록 (1:1 + 그룹), 최초 1회만 파싱"""
    global _alert_targets
    if _alert_targets is None:
        import os
        targets = []
        if TELEGRAM_CHAT_ID:
            targets.append(TELEGRAM_CHAT_ID)
        for gid in os.getenv("TELEGRAM_GROUP_IDS", "").split(","):
            gid = gid.strip()
            if gid:
                targets.append(gid)
        _alert_targets = tuple(targets)
    return _alert_targets


def send_alert(level, category, message, detail=None):
    """에러/이벤트 알림을 텔레그램으로 전송 (non-blocking, 1:1 + 그룹)"""
    def _send():
        emoji = LEVEL_EMOJI.get(level, "📌")
        text = f"{emoji} <b>[{level.upper()}]</b> {category}\n\n{message}"
        if detail:
            short = str(detail)[:500]
            text += f"\n\n<pre>{short}</pre>"
        text += f"\n\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        for chat_id in _get_alert_targets():
            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            })

    threading.Thread(target=_send, daemon=True).start()


def send_message(text, parse_mode="HTML", reply_markup=None, chat_id=None):
    """일반 텍스트 메시지 전송 (동기)"""
    data = {"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return _tg_post("sendMessage", data)


def send_band_approval_request(article_idx, product_name, price, preview_url, image_url=None, chat_id=None):
    """밴드 게시 승인 요청 (인라인 버튼)"""
    target_chat = chat_id or TELEGRAM_CHAT_ID
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
            "chat_id": target_chat,
            "photo": image_url,
            "caption": text,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }
        result = _tg_post("sendPhoto", data)
        if result and result.get("ok"):
            return result
        # 사진 전송 실패 시 텍스트로 fallback

    return send_message(text, reply_markup=reply_markup, chat_id=target_chat)


# ── 봇 서버 (Polling 방식) ─────────────────────────────────────

class TelegramBotServer:
    """장기 실행 봇 — getUpdates polling으로 메시지/콜백 수신"""

    def __init__(self):
        self.offset = 0
        self.running = False
        self._posting_active = False
        # 허용된 chat_id 목록 (1:1 + 그룹) — 한 번만 파싱
        import os
        allowed = {int(TELEGRAM_CHAT_ID)} if TELEGRAM_CHAT_ID else set()
        for gid in os.getenv("TELEGRAM_GROUP_IDS", "").split(","):
            gid = gid.strip()
            if gid:
                try:
                    allowed.add(int(gid))
                except ValueError:
                    pass
        self._allowed_chats = frozenset(allowed)

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

    def _is_authorized(self, chat_id):
        """허용된 채팅인지 확인 (1:1 또는 허용된 그룹)"""
        return chat_id in self._allowed_chats

    def _handle_message(self, message):
        """텍스트 명령 처리"""
        chat_id = message["chat"]["id"]
        chat_type = message["chat"].get("type", "private")
        text = message.get("text", "").strip()

        # 모든 메시지에 chat_id 로깅 (그룹 설정용)
        if chat_type != "private":
            user = message.get("from", {}).get("first_name", "?")
            print(f"[TelegramBot] 그룹 메시지: chat_id={chat_id}, user={user}, text={text[:50]}")

        if not self._is_authorized(chat_id):
            return

        if text == "/start":
            self._cmd_start(chat_id)
        elif text == "/status":
            self._cmd_status(chat_id)
        elif text == "/pending":
            self._cmd_pending(chat_id)
        elif text == "/post" or text.startswith("/post "):
            self._cmd_post(chat_id, text)
        elif text == "/skip" or text.startswith("/skip "):
            self._cmd_skip(chat_id, text)
        elif text == "/unskip" or text.startswith("/unskip "):
            self._cmd_unskip(chat_id, text)
        elif text == "/help":
            self._cmd_help(chat_id)

    def _handle_callback(self, callback):
        """인라인 버튼 콜백 처리"""
        cb_id = callback["id"]
        data = callback.get("data", "")
        chat_id = callback["message"]["chat"]["id"]
        message_id = callback["message"]["message_id"]

        if not self._is_authorized(chat_id):
            _tg_post("answerCallbackQuery", {"callback_query_id": cb_id, "text": "권한 없음"})
            return

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
                "/pending — 미게시 상품 (카테고리별)\n"
                "/post 번호 — 테스트 밴드 게시\n"
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

    @staticmethod
    def _send_long_message(chat_id, text, parse_mode="HTML"):
        """긴 메시지 분할 전송 (4000자 기준)"""
        if len(text) <= 4000:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
            return
        lines = text.split('\n')
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 4000:
                if chunk:
                    _tg_post("sendMessage", {"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode})
                chunk = line
            else:
                chunk = chunk + '\n' + line if chunk else line
        if chunk:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode})

    def _cmd_pending(self, chat_id):
        """미게시 상품 카테고리별 분류 표시"""
        try:
            from band_poster import get_unposted_products
            products = get_unposted_products()

            if not products:
                _tg_post("sendMessage", {"chat_id": chat_id, "text": "✅ 모든 상품이 밴드에 게시되었습니다."})
                return

            # 카테고리별 그룹핑 (전체 넘버링 유지)
            cat_groups = {}
            for i, p in enumerate(products, 1):
                cat_name = p.category.name if p.category else "미분류"
                cat_code = p.category.code if p.category else "Z"
                cat_groups.setdefault((cat_code, cat_name), []).append((i, p))

            lines = [f"📋 <b>미게시 상품 ({len(products)}개)</b>"]
            for (cat_code, cat_name), items in sorted(cat_groups.items()):
                lines.append(f"\n<b>[{cat_name}]</b> ({len(items)}개)")
                for num, p in items:
                    price = f"{p.price:,}원" if p.price else "가격미정"
                    lines.append(f"  {num}. {p.name[:35]} ({price})")

            lines.append(f"\n💡 <code>/post 번호</code>로 테스트 게시")
            lines.append(f"예: <code>/post 1 3 5-8</code>")

            self._send_long_message(chat_id, "\n".join(lines))
        except Exception as e:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": f"❌ 조회 실패: {e}"})

    @staticmethod
    def _parse_numbers(text):
        """'/post 1 3 5-8' → [1, 3, 5, 6, 7, 8]"""
        nums = set()
        text = text.split(maxsplit=1)[1] if ' ' in text else ""
        for part in text.replace(',', ' ').split():
            if '-' in part:
                try:
                    start, end = part.split('-', 1)
                    for n in range(int(start), int(end) + 1):
                        nums.add(n)
                except ValueError:
                    pass
            else:
                try:
                    nums.add(int(part))
                except ValueError:
                    pass
        return sorted(nums)

    def _cmd_post(self, chat_id, text):
        """번호 지정으로 테스트 밴드 게시"""
        if self._posting_active:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": "⏳ 이미 게시 작업이 진행 중입니다."})
            return

        nums = self._parse_numbers(text)
        if not nums:
            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": "사용법: <code>/post 번호</code>\n예: <code>/post 1 3 5-8</code>\n\n/pending에서 번호를 확인하세요.",
                "parse_mode": "HTML",
            })
            return

        try:
            from band_poster import get_unposted_products
            products = get_unposted_products()
        except Exception as e:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": f"❌ 상품 목록 조회 실패: {e}"})
            return

        targets = []
        invalid = []
        for n in nums:
            if 1 <= n <= len(products):
                targets.append((n, products[n - 1]))
            else:
                invalid.append(n)

        if not targets:
            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": f"❌ 유효한 상품 번호가 없습니다. (범위: 1-{len(products)})",
            })
            return

        target_names = "\n".join(f"  #{n}. {p.name[:30]}" for n, p in targets)
        msg = f"⏳ <b>{len(targets)}개 상품 테스트 밴드 게시 시작</b>\n\n{target_names}"
        if invalid:
            msg += f"\n\n⚠️ 유효하지 않은 번호: {', '.join(str(n) for n in invalid)}"
        _tg_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})

        self._posting_active = True
        threading.Thread(
            target=self._post_products_thread,
            args=(chat_id, targets),
            daemon=True,
        ).start()

    def _post_products_thread(self, chat_id, targets):
        """백그라운드에서 밴드 게시물 생성 + 승인 요청"""
        poster = None
        db_session = None
        try:
            from band_poster import BandPoster
            from config import BAND_PREVIEW_URL
            from models import get_session, Product

            if not BAND_PREVIEW_URL:
                _tg_post("sendMessage", {"chat_id": chat_id, "text": "❌ BAND_PREVIEW_URL이 설정되지 않았습니다."})
                return

            poster = BandPoster(headless=True)
            poster._init_driver()
            if not poster.check_login():
                _tg_post("sendMessage", {"chat_id": chat_id, "text": "❌ 밴드 로그인이 필요합니다. band-login을 먼저 실행하세요."})
                return

            db_session = get_session()
            success = 0
            failed = 0

            for i, (num, product) in enumerate(targets, 1):
                _tg_post("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"📝 [{i}/{len(targets)}] #{num}. {product.name[:30]} 게시 중...",
                })

                post_url = poster.post_product(BAND_PREVIEW_URL, product.article_idx)

                if post_url:
                    p = db_session.query(Product).filter_by(article_idx=product.article_idx).first()
                    if p:
                        p.band_preview_posted_at = datetime.now()
                        p.band_preview_url = post_url
                        db_session.commit()

                    send_band_approval_request(
                        product.article_idx,
                        product.name,
                        product.price or 0,
                        post_url,
                        product.main_image_url,
                        chat_id=chat_id,
                    )
                    success += 1
                else:
                    _tg_post("sendMessage", {
                        "chat_id": chat_id,
                        "text": f"❌ #{num}. {product.name[:30]} 게시 실패",
                    })
                    failed += 1

                if i < len(targets):
                    time.sleep(3)

            msg = f"✅ <b>테스트 밴드 게시 완료</b>\n성공: {success}개"
            if failed:
                msg += f", 실패: {failed}개"
            msg += "\n\n각 상품의 승인 요청을 확인하세요."
            _tg_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
        except Exception as e:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": f"❌ 게시 중 에러: {e}"})
        finally:
            if db_session:
                db_session.close()
            if poster:
                poster.close()
            self._posting_active = False

    def _cmd_skip(self, chat_id, text):
        """pending 목록에서 상품 제외 (벌크)"""
        nums = self._parse_numbers(text)
        if not nums:
            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": "사용법: <code>/skip 번호</code>\n예: <code>/skip 1 3 5-8</code>\n\n/pending에서 번호를 확인하세요.",
                "parse_mode": "HTML",
            })
            return

        try:
            from band_poster import get_unposted_products
            from models import get_session, Product
            products = get_unposted_products()

            skipped = []
            invalid = []
            skip_idxs = []
            for n in nums:
                if 1 <= n <= len(products):
                    skip_idxs.append(products[n - 1].article_idx)
                    skipped.append(f"#{n}. {products[n - 1].name[:30]}")
                else:
                    invalid.append(n)

            if skip_idxs:
                db_session = get_session()
                db_session.query(Product).filter(
                    Product.article_idx.in_(skip_idxs)
                ).update({Product.band_skipped: True}, synchronize_session=False)
                db_session.commit()
                db_session.close()

            msg = f"⏭️ <b>{len(skipped)}개 상품 제외 완료</b>\n\n" + "\n".join(skipped)
            if invalid:
                msg += f"\n\n⚠️ 유효하지 않은 번호: {', '.join(str(n) for n in invalid)}"
            _tg_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
        except Exception as e:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": f"❌ 제외 실패: {e}"})

    def _cmd_unskip(self, chat_id, text):
        """제외된 상품 복원 (번호 또는 'all')"""
        arg = text.split(maxsplit=1)[1].strip() if ' ' in text else ""

        try:
            from models import get_session, Product

            db_session = get_session()

            if arg == "all":
                count = db_session.query(Product).filter(
                    Product.band_skipped == True
                ).update({Product.band_skipped: False})
                db_session.commit()
                db_session.close()
                _tg_post("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"✅ 제외된 상품 {count}개 모두 복원했습니다.",
                })
                return

            if arg == "list":
                skipped = db_session.query(Product).filter(
                    Product.band_skipped == True,
                    Product.is_active == True,
                ).all()
                db_session.close()
                if not skipped:
                    _tg_post("sendMessage", {"chat_id": chat_id, "text": "제외된 상품이 없습니다."})
                    return
                lines = [f"⏭️ <b>제외된 상품 ({len(skipped)}개)</b>\n"]
                for i, p in enumerate(skipped, 1):
                    lines.append(f"  {i}. {p.name[:35]}")
                lines.append(f"\n<code>/unskip all</code> — 전체 복원")
                _tg_post("sendMessage", {"chat_id": chat_id, "text": "\n".join(lines), "parse_mode": "HTML"})
                return

            db_session.close()
            _tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": "사용법:\n<code>/unskip list</code> — 제외 목록 보기\n<code>/unskip all</code> — 전체 복원",
                "parse_mode": "HTML",
            })
        except Exception as e:
            _tg_post("sendMessage", {"chat_id": chat_id, "text": f"❌ 복원 실패: {e}"})

    def _cmd_help(self, chat_id):
        _tg_post("sendMessage", {
            "chat_id": chat_id,
            "text": (
                "📖 <b>명령어 목록</b>\n\n"
                "/status — 서버 상태 (상품 수, 주문 수)\n"
                "/pending — 밴드 미게시 상품 (카테고리별)\n"
                "/post 번호 — 테스트 밴드 게시\n"
                "  예: <code>/post 1 3 5-8</code>\n"
                "/skip 번호 — pending에서 제외\n"
                "  예: <code>/skip 1 3 5-8</code>\n"
                "/unskip list — 제외 목록 보기\n"
                "/unskip all — 전체 복원\n"
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
