"""Business transactions. No network calls occur inside database transactions."""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from urllib.parse import urlencode, urlsplit
import json
import logging
import re
import secrets
import time

from .db import dumps, enqueue

log = logging.getLogger(__name__)
MAX_USER_ID = 2**53 - 1
MENU = {"keyboard": [["我要下单", "我的订单"], ["FAQ", "联系人工"], ["结束人工", "取消凭证上传"]],
        "resize_keyboard": True}
FAQ = ("常见问题\n\n"
       "1. 如何报价？提交 STL、层高、填充率与材质后，由管理员检查模型并报价。\n"
       "2. 多久完成？交期随模型与排单而变，以管理员确认结果为准。\n"
       "3. 如何付款？收到报价后按收款说明转账，再点击对应订单的“提交付款凭证”。\n"
       "4. 上传需要什么？Google 账号、一个不超过 10 MiB 的 STL 文件。\n"
       "5. 可以修改需求吗？报价前联系人工；付款后需重新确认价格和排期。")


def buttons(rows):
    return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in rows]}


def notify(c, chat_id, text, markup=None, mapping=None):
    args = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if markup:
        args["reply_markup"] = markup
    if mapping:
        args["_mapping"] = mapping
    return enqueue(c, "send_message", **args)


def money(sen):
    return f"RM {sen // 100}.{sen % 100:02d}"


def price_sen(raw):
    if not re.fullmatch(r"(?:0|[1-9]\d{0,5})(?:\.\d{1,2})?", raw):
        raise ValueError("金额格式错误；示例 /quote 12 35.50，最多两位小数。")
    amount = int(Decimal(raw) * 100)
    if not 1 <= amount <= 10000000:
        raise ValueError("报价范围为 RM 0.01–100000.00。")
    return amount


def drive_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        u = urlsplit(value)
        return (u.scheme == "https" and u.hostname in
                {"drive.google.com", "drive.usercontent.google.com", "docs.google.com"}
                and u.username is None and u.password is None and u.port in (None, 443))
    except ValueError:
        return False


class Service:
    def __init__(self, db, settings):
        self.db, self.s = db, settings
        self.bot_username = ""

    def accept_form(self, p):
        # Envelope defects cannot be acknowledged under the GAS event-ID contract.
        if not isinstance(p, dict):
            raise ValueError("Expected JSON object")
        for key in ('form_id', 'response_id'):
            if not isinstance(p.get(key), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', p[key]):
                raise ValueError("Invalid event identity")
        eid = p['form_id'] + ':' + p['response_id']
        if p.get('event_id') != eid:
            raise ValueError("Event identity mismatch")
        reasons = []
        if p.get('source') != 'google_forms' or type(p.get('schema_version')) is not int or p['schema_version'] != 1:
            reasons.append('INVALID_SCHEMA')
        if p['form_id'] != self.s.form_id:
            reasons.append('UNEXPECTED_FORM')
        raw_uid = p.get('telegram_id')
        uid = None
        if isinstance(raw_uid, str) and re.fullmatch(r'[1-9]\d{0,15}', raw_uid):
            uid = int(raw_uid)
        if uid is None or uid > MAX_USER_ID:
            uid = None
            reasons.append('INVALID_TELEGRAM_ID')
        token = p.get('binding_token')
        th = None
        if isinstance(token, str) and re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            th = sha256(token.encode()).hexdigest()
        else:
            reasons.append('INVALID_BINDING_TOKEN')
        submitted = 0
        try:
            dt = datetime.fromisoformat(p['submitted_at'].replace('Z', '+00:00'))
            if dt.tzinfo is None:
                raise ValueError('Missing timezone')
            submitted = dt.timestamp()
            if submitted > time.time() + 60 or submitted <= 0:
                raise ValueError('Invalid submission time')
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            reasons.append('INVALID_SUBMITTED_AT')
        req = p.get('requirements')
        if not isinstance(req, dict):
            req = {}
        choices = {'layer_height_mm': ['0.12', '0.16', '0.20', '0.28'],
                   'infill_percent': ['10', '20', '30', '50', '100'],
                   'material': ['PLA', 'PETG', 'ABS', 'TPU']}
        for key, allowed in choices.items():
            if req.get(key) not in allowed:
                reasons.append('INVALID_' + key.upper())
        files = p.get('files')
        if not isinstance(files, list) or len(files) != 1:
            reasons.append('EXPECTED_ONE_STL')
            files = []
        clean_files = []
        for f in files:
            if not isinstance(f, dict):
                reasons.append('INVALID_FILE')
                continue
            if (not isinstance(f.get('file_id'), str) or
                    not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', f['file_id']) or
                    not isinstance(f.get('name'), str) or len(f['name']) > 255 or
                    not f['name'].lower().endswith('.stl') or
                    type(f.get('size_bytes')) is not int or not 0 < f['size_bytes'] <= 10 * 1024 * 1024 or
                    not drive_url(f.get('view_url')) or not drive_url(f.get('download_url')) or
                    f.get('metadata_error')):
                reasons.append('INVALID_FILE_METADATA')
                continue
            clean_files.append({k: f[k] for k in ('file_id', 'name', 'size_bytes', 'view_url', 'download_url')})
        if not isinstance(p.get('validation_errors'), list) or p['validation_errors']:
            reasons.append('GAS_VALIDATION_FAILED')
        now = time.time()
        with self.db.transaction() as c:
            old = c.execute('SELECT disposition FROM webhook_events WHERE event_id=?', (eid,)).fetchone()
            if old:
                return {'accepted': True, 'event_id': eid,
                        'disposition': 'quarantined' if old['disposition'] == 'quarantined' else 'duplicate'}
            record = c.execute('SELECT * FROM binding_tokens WHERE token_hash=?', (th,)).fetchone() if th else None
            if not record:
                reasons.append('UNKNOWN_TOKEN')
            elif record['user_id'] != uid:
                reasons.append('TOKEN_USER_MISMATCH')
            elif record['used_event_id']:
                reasons.append('TOKEN_ALREADY_USED')
            elif not record['issued_at'] - 5 <= submitted <= record['expires_at']:
                reasons.append('TOKEN_OUTSIDE_VALIDITY')
            reasons = sorted(set(reasons))
            disposition = 'quarantined' if reasons else 'created'
            c.execute('INSERT INTO webhook_events VALUES (?,?,?,?,?,?)',
                      (eid, p['form_id'], p['response_id'], disposition, dumps(reasons), now))
            if reasons:
                notify(c, self.s.admin_chat_id,
                       '⚠️ 表单事件已隔离，未创建订单。\n事件: ' + eid + '\n原因: ' + ', '.join(reasons))
                log.warning('form_quarantined event=%s reasons=%s', eid, ','.join(reasons))
            else:
                oid = c.execute('''INSERT INTO orders(event_id,user_id,status,requirements_json,files_json,created_at,updated_at)
                                   VALUES (?,?,'PENDING_QUOTE',?,?,?,?)''',
                                (eid, uid, dumps({k: req[k] for k in choices}), dumps(clean_files), now, now)).lastrowid
                c.execute('UPDATE binding_tokens SET used_event_id=? WHERE token_hash=?', (eid, th))
                f = clean_files[0]
                text = (f"新订单 #{oid}\n客户 ID: {uid}\n材质: {req['material']}\n"
                        f"层高: {req['layer_height_mm']} mm\n填充率: {req['infill_percent']}%\n"
                        f"文件: {f['name']}\n查看: {f['view_url']}\n下载: {f['download_url']}")
                # Keep Telegram messages below its UTF-16 length limit.
                notify(c, self.s.admin_chat_id, text[:3500])
                notify(c, self.s.admin_chat_id, f'报价命令: /quote {oid} 35.50\n下载文件需要获授权的 Google 账号。')
                notify(c, uid, f'订单 #{oid} 已收到，等待模型检查与人工报价。')
            return {'accepted': True, 'event_id': eid, 'disposition': disposition}

    def process_one(self):
        with self.db.transaction() as c:
            row = c.execute("SELECT * FROM telegram_inbox WHERE status='PENDING' AND next_at<=? ORDER BY update_id LIMIT 1",
                            (time.time(),)).fetchone()
            if not row:
                return False
            c.execute('SAVEPOINT business')
            try:
                self.handle(c, json.loads(row['payload_json']))
                c.execute('RELEASE business')
                # Processed inbound content is no longer needed; keep only the update ID.
                c.execute("UPDATE telegram_inbox SET status='DONE',payload_json='{}' WHERE update_id=?", (row['update_id'],))
            except Exception as exc:
                c.execute('ROLLBACK TO business')
                c.execute('RELEASE business')
                attempt = row['attempts'] + 1
                state = 'DEAD' if attempt >= 5 else 'PENDING'
                c.execute('UPDATE telegram_inbox SET attempts=?,status=?,next_at=?,last_error=? WHERE update_id=?',
                          (attempt, state, time.time() + min(300, 2**attempt), type(exc).__name__, row['update_id']))
                log.error('inbox_failed update=%s error_type=%s', row['update_id'], type(exc).__name__)
                if state == 'DEAD':
                    notify(c, self.s.admin_chat_id, f"⚠️ Telegram 消息处理失败，update_id={row['update_id']}。请检查本机死信队列。")
            return True

    def handle(self, c, update):
        if 'callback_query' in update:
            self.callback(c, update['callback_query'])
            return
        m = update.get('message')
        if not m or not m.get('from') or m['from'].get('is_bot'):
            return
        uid, chat_id = m['from']['id'], m['chat']['id']
        text = m.get('text', '')
        if text.startswith('/') and '@' in text.split()[0]:
            target = text.split()[0].split('@', 1)[1]
            if self.bot_username and target.lower() != self.bot_username.lower():
                return
        cmd = text.split()[0].split('@')[0].lower() if text.startswith('/') else ''
        if chat_id == self.s.admin_chat_id:
            if uid in self.s.admin_user_ids and not m.get('sender_chat'):
                self.admin(c, m, cmd)
            return
        if m['chat']['type'] != 'private' or uid != chat_id:
            return
        c.execute('INSERT OR IGNORE INTO user_sessions(user_id,chat_id,created_at) VALUES (?,?,?)',
                  (uid, chat_id, time.time()))
        if cmd == '/start':
            notify(c, uid, '欢迎使用 3D 打印接单客服。点击“我要下单”提交需求；付款前请先等待报价。', MENU)
            self.new_link(c, uid)
        elif cmd == '/order' or text == '我要下单':
            self.new_link(c, uid)
        elif cmd == '/orders' or text == '我的订单':
            rows = c.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10', (uid,)).fetchall()
            if not rows:
                notify(c, uid, '暂无订单。点击“我要下单”开始。')
            for o in rows:
                markup = buttons([[("提交付款凭证", f"pay:{o['id']}")]]) if o['status'] == 'AWAITING_PAYMENT' else None
                notify(c, uid, f"订单 #{o['id']}\n状态: {o['status']}\n报价: " +
                       (money(o['price_sen']) if o['price_sen'] is not None else '等待报价'), markup)
        elif cmd == '/faq' or text == 'FAQ':
            notify(c, uid, FAQ)
        elif cmd == '/support' or text == '联系人工':
            session = c.execute('SELECT * FROM user_sessions WHERE user_id=?', (uid,)).fetchone()
            if session['mode'] != 'HUMAN_SUPPORT':
                c.execute("UPDATE user_sessions SET mode='HUMAN_SUPPORT',support_session_id=? WHERE user_id=?",
                          (secrets.token_hex(16), uid))
            notify(c, uid, '已进入人工客服。请发送文字、图片或文件；输入 /end 结束。')
            self.support(c, uid, None)
        elif cmd == '/end' or text == '结束人工':
            c.execute("UPDATE user_sessions SET mode='BOT_MODE',support_session_id=NULL WHERE user_id=?", (uid,))
            notify(c, uid, '人工会话已结束。', MENU)
        elif cmd == '/cancelproof' or text == '取消凭证上传':
            c.execute('UPDATE user_sessions SET payment_order_id=NULL WHERE user_id=?', (uid,))
            notify(c, uid, '已取消本次凭证选择；订单状态未改变。')
        else:
            self.customer_content(c, uid, m)

    def new_link(self, c, uid):
        now = time.time()
        recent = c.execute('SELECT COUNT(*) FROM binding_tokens WHERE user_id=? AND issued_at>?', (uid, now - 3600)).fetchone()[0]
        if recent >= 20:
            notify(c, uid, '一小时内申请下单链接次数过多，请稍后再试或联系人工。')
            return
        token = secrets.token_urlsafe(32)
        c.execute('INSERT INTO binding_tokens(token_hash,user_id,issued_at,expires_at) VALUES (?,?,?,?)',
                  (sha256(token.encode()).hexdigest(), uid, now, now + 86400))
        url = self.s.form_url + '?' + urlencode({'usp': 'pp_url', self.s.telegram_entry: str(uid), self.s.binding_entry: token})
        notify(c, uid, '请在 24 小时内填写表单。需要登录 Google 账号上传 STL；不要修改或转发绑定字段。',
               {'inline_keyboard': [[{'text': '填写打印需求', 'url': url}]]})

    def callback(self, c, q):
        m, uid = q.get('message', {}), q['from']['id']
        cid = m.get('chat', {}).get('id')
        data = q.get('data', '')
        answer = '无效操作。'
        if re.fullmatch(r'pay:\d{1,12}', data) and cid == uid:
            oid = int(data.split(':')[1])
            row = c.execute("SELECT id FROM orders WHERE id=? AND user_id=? AND status='AWAITING_PAYMENT'", (oid, uid)).fetchone()
            if row:
                c.execute('UPDATE user_sessions SET payment_order_id=? WHERE user_id=?', (oid, uid))
                notify(c, uid, f'请上传订单 #{oid} 的付款截图（单张照片或 JPG/PNG 文件，最大 10 MiB）。\n取消选择: /cancelproof')
                answer = '已选择订单，请发送付款截图。'
            else:
                answer = '订单不存在、不属于你，或当前不是待付款状态。'
        elif re.fullmatch(r'(approve|reject):\d{1,12}:\d{1,12}', data):
            if cid == self.s.admin_chat_id and uid in self.s.admin_user_ids:
                action, oid, pid = data.split(':')
                answer = self.review(c, uid, int(oid), int(pid), action == 'approve')
            else:
                answer = '你没有审核权限。'
        enqueue(c, 'answer_callback_query', callback_query_id=q['id'], text=answer[:180], show_alert=False)

    def admin(self, c, m, cmd):
        uid, text = m['from']['id'], m.get('text', '')
        args = text.split()
        try:
            if cmd == '/quote':
                if len(args) != 3 or not re.fullmatch(r'\d{1,12}', args[1]):
                    raise ValueError('用法: /quote 订单号 金额，例如 /quote 12 35.50')
                self.quote(c, uid, int(args[1]), price_sen(args[2]))
            elif cmd == '/complete':
                if len(args) != 2 or not re.fullmatch(r'\d{1,12}', args[1]):
                    raise ValueError('用法: /complete 订单号')
                oid = int(args[1])
                row = c.execute("SELECT user_id FROM orders WHERE id=? AND status='PROCESSING'", (oid,)).fetchone()
                if not row:
                    raise ValueError('订单不存在或不在制作中。')
                c.execute("UPDATE orders SET status='COMPLETED',updated_at=? WHERE id=?", (time.time(), oid))
                self.audit(c, uid, 'COMPLETE', oid)
                notify(c, row['user_id'], f'订单 #{oid} 已完成，请联系人工安排领取或寄送。')
                notify(c, self.s.admin_chat_id, f'订单 #{oid} 已标记完成。')
            elif cmd in ('/reply', '/close'):
                parts = text.split(maxsplit=2)
                if len(parts) < 2:
                    raise ValueError('用法: /reply 客服编号 回复内容，或 /close 客服编号')
                route = self.active_route(c, parts[1])
                if not route:
                    raise ValueError('客服编号不存在或会话已结束。')
                if cmd == '/close':
                    c.execute("UPDATE user_sessions SET mode='BOT_MODE',support_session_id=NULL WHERE user_id=?", (route['user_id'],))
                    notify(c, route['user_id'], '管理员已结束本次人工会话。', MENU)
                    notify(c, self.s.admin_chat_id, '人工会话已关闭。')
                else:
                    if len(parts) != 3:
                        raise ValueError('请提供回复内容。')
                    notify(c, route['user_id'], parts[2])
                    notify(c, self.s.admin_chat_id, '客服回复已加入发送队列。')
            elif cmd == '/status':
                counts = c.execute("SELECT status,COUNT(*) n FROM notification_outbox GROUP BY status").fetchall()
                notify(c, self.s.admin_chat_id, '通知队列: ' + ', '.join(f"{r['status']}={r['n']}" for r in counts))
            elif m.get('reply_to_message') and not cmd:
                target = m['reply_to_message']['message_id']
                route = c.execute('SELECT * FROM message_mappings WHERE admin_chat_id=? AND admin_message_id=?',
                                  (self.s.admin_chat_id, target)).fetchone()
                if not route or not self.active_route(c, route['route_id']):
                    raise ValueError('找不到有效客服映射。请回复客服标题消息，或用 /reply 客服编号 内容。已结束的会话不能继续回复。')
                if not self.copyable(m):
                    raise ValueError('仅支持文字、照片、文件、视频、语音及贴纸回复。')
                enqueue(c, 'copy_message', chat_id=route['user_chat_id'], from_chat_id=self.s.admin_chat_id,
                        message_id=m['message_id'])
                notify(c, self.s.admin_chat_id, '客服回复已加入发送队列。')
        except ValueError as exc:
            notify(c, self.s.admin_chat_id, str(exc))

    def quote(self, c, admin, oid, amount):
        row = c.execute("SELECT * FROM orders WHERE id=? AND status='PENDING_QUOTE'", (oid,)).fetchone()
        if not row:
            raise ValueError('订单不存在或已报价，不能重复报价。')
        c.execute("UPDATE orders SET status='AWAITING_PAYMENT',price_sen=?,quoted_by=?,updated_at=? WHERE id=?",
                  (amount, admin, time.time(), oid))
        self.audit(c, admin, 'QUOTE', oid, str(amount))
        notify(c, row['user_id'], f'订单 #{oid} 报价: {money(amount)}\n\n{self.s.payment_instructions}\n\n'
               '完成转账后，点击下方按钮提交截图。截图不代表到账，需人工核验。',
               buttons([[("提交付款凭证", f'pay:{oid}')]]))
        notify(c, self.s.admin_chat_id, f'订单 #{oid} 已报价 {money(amount)}，等待付款。')

    def customer_content(self, c, uid, m):
        session = c.execute('SELECT * FROM user_sessions WHERE user_id=?', (uid,)).fetchone()
        selected = session['payment_order_id']
        is_image = bool(m.get('photo') or m.get('document', {}).get('mime_type', '').startswith('image/'))
        if selected and is_image:
            self.proof(c, uid, selected, m)
        elif session['mode'] == 'HUMAN_SUPPORT':
            if self.copyable(m):
                self.support(c, uid, m)
            else:
                notify(c, uid, '请发送文字、照片、文件、视频、语音或贴纸。')
        elif is_image:
            pending = c.execute("SELECT id FROM orders WHERE user_id=? AND status='AWAITING_PAYMENT' LIMIT 1", (uid,)).fetchone()
            notify(c, uid, '请打开“我的订单”，选择对应订单的“提交付款凭证”。' if pending else '请先完成报价；若已提交截图，请等待人工审核。')
        else:
            notify(c, uid, '请选择菜单。上传凭证前请先选择订单；咨询问题请点击“联系人工”。', MENU)

    def proof(self, c, uid, oid, m):
        row = c.execute("SELECT * FROM orders WHERE id=? AND user_id=? AND status='AWAITING_PAYMENT'", (oid, uid)).fetchone()
        if not row:
            c.execute('UPDATE user_sessions SET payment_order_id=NULL WHERE user_id=?', (uid,))
            notify(c, uid, '订单当前不能提交凭证，请查看“我的订单”。')
            return
        if m.get('photo'):
            media, kind = m['photo'][-1], 'photo'
        else:
            media, kind = m.get('document', {}), 'document'
            if (media.get('mime_type') not in ('image/jpeg', 'image/png') or
                    not re.search(r'\.(png|jpe?g)$', media.get('file_name', ''), re.I)):
                notify(c, uid, '凭证文件仅支持 JPG/PNG；也可以直接发送照片。')
                return
        if not media.get('file_id') or not 0 < media.get('file_size', 0) <= 10 * 1024 * 1024:
            notify(c, uid, '图片大小必须在 10 MiB 以内，请重新发送。')
            return
        pid = c.execute('''INSERT INTO payment_proofs(order_id,user_id,source_message_id,file_id,media_type,status,created_at)
                           VALUES (?,?,?,?,?,'PENDING',?)''',
                        (oid, uid, m['message_id'], media['file_id'], kind, time.time())).lastrowid
        c.execute("UPDATE orders SET status='PAYMENT_REVIEW',current_proof_id=?,updated_at=? WHERE id=?",
                  (pid, time.time(), oid))
        c.execute('UPDATE user_sessions SET payment_order_id=NULL WHERE user_id=?', (uid,))
        enqueue(c, 'send_' + kind, chat_id=self.s.admin_chat_id, **{kind: media['file_id']},
                caption=f"订单 #{oid}，凭证 #{pid}\n报价 {money(row['price_sen'])}\n请核对真实到账后确认。",
                reply_markup=buttons([[("确认收款", f'approve:{oid}:{pid}'), ("驳回凭证", f'reject:{oid}:{pid}')]]))
        notify(c, uid, f'订单 #{oid} 的凭证已收到，等待人工核验。')

    def review(self, c, admin, oid, pid, approved):
        row = c.execute("SELECT * FROM orders WHERE id=? AND status='PAYMENT_REVIEW' AND current_proof_id=?", (oid, pid)).fetchone()
        proof = c.execute("SELECT id FROM payment_proofs WHERE id=? AND order_id=? AND status='PENDING'", (pid, oid)).fetchone()
        if not row or not proof:
            return '已处理，或此按钮对应的是旧凭证。'
        c.execute('UPDATE payment_proofs SET status=?,reviewed_by=?,reviewed_at=? WHERE id=?',
                  ('APPROVED' if approved else 'REJECTED', admin, time.time(), pid))
        c.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?',
                  ('PROCESSING' if approved else 'AWAITING_PAYMENT', time.time(), oid))
        self.audit(c, admin, 'APPROVE_PAYMENT' if approved else 'REJECT_PAYMENT', oid, str(pid))
        markup = None if approved else buttons([[("重新提交付款凭证", f'pay:{oid}')]])
        notify(c, row['user_id'], f'订单 #{oid} ' + ('已确认收款，进入制作流程。' if approved else '凭证未通过核验，请联系人工或重新提交。'), markup)
        notify(c, self.s.admin_chat_id, f'订单 #{oid} 凭证 #{pid} ' + ('已确认收款。' if approved else '已驳回。'))
        return '审核完成。'

    @staticmethod
    def copyable(m):
        return any(k in m for k in ('text', 'photo', 'document', 'video', 'voice', 'audio', 'sticker', 'animation', 'video_note')) and not m.get('has_protected_content')

    def support(self, c, uid, m):
        session = c.execute('SELECT * FROM user_sessions WHERE user_id=?', (uid,)).fetchone()
        rid = 'R' + secrets.token_hex(8)
        c.execute('INSERT INTO support_routes VALUES (?,?,?,?)', (rid, uid, session['support_session_id'], time.time()))
        mapping = {'user_id': uid, 'user_chat_id': uid, 'support_session_id': session['support_session_id'], 'route_id': rid}
        notify(c, self.s.admin_chat_id, f'人工客服\n客户 ID: {uid}\n客服编号: {rid}\n回复本条或随后客户消息即可。\n备用: /reply {rid} 内容\n结束: /close {rid}', mapping=mapping)
        if m:
            enqueue(c, 'copy_message', chat_id=self.s.admin_chat_id, from_chat_id=uid,
                    message_id=m['message_id'], _mapping=mapping)

    @staticmethod
    def active_route(c, rid):
        return c.execute('''SELECT r.* FROM support_routes r JOIN user_sessions s ON s.user_id=r.user_id
                            WHERE r.route_id=? AND s.mode='HUMAN_SUPPORT' AND s.support_session_id=r.support_session_id''', (rid,)).fetchone()

    @staticmethod
    def audit(c, actor, action, oid, detail=''):
        c.execute('INSERT INTO audit_log(actor_id,action,order_id,detail,created_at) VALUES (?,?,?,?,?)',
                  (actor, action, oid, detail, time.time()))
