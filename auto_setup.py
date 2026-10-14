"""First-run setup. No tokens in arguments, logs or distributable archives."""
from __future__ import annotations
import asyncio
import getpass
from hashlib import sha256
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values
from telegram import Bot
from telegram.error import TelegramError
from scripts.config_helpers import validate, write_env

ROOT = Path(__file__).resolve().parent


def parse_form(editor: str, prefilled: str) -> dict[str, str]:
    edit = urlsplit(editor.strip())
    match = re.fullmatch(r'/forms/d/([A-Za-z0-9_-]+)/edit/?', edit.path)
    if edit.scheme != 'https' or edit.netloc != 'docs.google.com' or not match:
        raise ValueError('请粘贴 Google 表单编辑链接：https://docs.google.com/forms/d/…/edit')
    public = urlsplit(prefilled.strip())
    if (public.scheme != 'https' or public.netloc != 'docs.google.com' or
            not re.fullmatch(r'/forms/d/e/[A-Za-z0-9_-]+/viewform', public.path)):
        raise ValueError('请使用 Google 表单生成的公开预填链接。')
    fields = parse_qs(public.query)
    def entry(marker):
        found = [k for k, v in fields.items() if re.fullmatch(r'entry\.\d+', k) and v == [marker]]
        if len(found) != 1:
            raise ValueError(f'预填链接中必须恰好有一个字段填写 {marker}，请重新生成。')
        return found[0]
    return {'GOOGLE_FORM_ID': match[1],
            'GOOGLE_FORM_URL': f'https://docs.google.com{public.path}',
            'FORM_TELEGRAM_ENTRY': entry('123456789'),
            'FORM_BINDING_ENTRY': entry('PRINT3D_BINDING_TOKEN')}


def pairing_message(update, code: str, username: str):
    m = update.message
    if not m or not m.from_user or m.from_user.is_bot or m.sender_chat:
        return None
    words = (m.text or '').split()
    if len(words) != 2 or words[1] != code:
        return None
    command = words[0].split('@', 1)
    if command[0].lower() != '/setup' or (len(command) == 2 and command[1].lower() != username.lower()):
        return None
    if m.chat.type == 'private' and m.chat_id == m.from_user.id:
        return ('owner', m.from_user.id)
    if m.chat.type in ('group', 'supergroup'):
        return ('group', m.chat_id, m.from_user.id)
    return None


async def pair(token: str, group: bool) -> tuple[str, str]:
    code = secrets.token_hex(4)
    async with Bot(token) as bot:
        info = await bot.get_webhook_info()
        if info.url:
            raise ValueError('此 Bot 已配置 Webhook。请使用专用新 Bot；向导不会删除已有 Webhook。')
        print(f'已连接 @{bot.username}。请私聊发送：/setup {code}', flush=True)
        owner = None
        offset = 0
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            updates = await bot.get_updates(offset=offset, timeout=20, read_timeout=30,
                                             allowed_updates=['message'])
            for update in updates:
                offset = update.update_id + 1
                result = pairing_message(update, code, bot.username)
                if not result:
                    continue
                if result[0] == 'owner' and owner is None:
                    owner = result[1]
                    if not group:
                        return str(owner), str(owner)
                    print(f'管理员已识别。请将 Bot 加入管理群，用同一账号发送：/setup@{bot.username} {code}', flush=True)
                elif result[0] == 'group' and owner and result[2] == owner:
                    member = await bot.get_chat_member(result[1], bot.id)
                    if member.status in {'left', 'kicked'} or (member.status == 'restricted' and not member.can_send_messages):
                        print('Bot 无法在该群发送消息，请调整权限后重发配对命令。', flush=True)
                        continue
                    return str(result[1]), str(owner)
        raise ValueError('配对等待超过 10 分钟，请重新运行；没有保存配置。')


def ready() -> bool:
    if not (ROOT / '.env').exists():
        return False
    values = dotenv_values(ROOT / '.env', interpolate=False)
    try:
        validate(values)
        required = ['BOT_TOKEN', 'WEBHOOK_SECRET', 'GOOGLE_FORM_ID', 'GOOGLE_FORM_URL']
        if any(any(mark in values[k].lower() for mark in ('replace', 'your_', 'xxxxx')) for k in required):
            return False
        return True
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def ask_form():
    while True:
        print('\n打开现有 Google 表单的编辑页面。菜单「获取预填链接」：')
        print('Telegram ID 字段填 123456789；绑定令牌字段填 PRINT3D_BINDING_TOKEN。')
        try:
            return parse_form(input('表单编辑链接：'), input('生成的预填链接：'))
        except ValueError as exc:
            print(exc)


def main():
    os.chdir(ROOT)
    if ready() and '--reconfigure' not in sys.argv:
        print('现有配置完整，直接启动。修改配置请运行 deploy_print3d.bat reconfigure。')
        return 0
    print('首次部署：请准备 BotFather Token、接单 Google 表单（含第一阶段 Apps Script）和收款说明。')
    if (ROOT / '.env').exists():
        if input('已有配置不完整或要求重新配置。替换现有 .env？输入 YES：').strip() != 'YES':
            print('已取消，原配置保留。')
            return 1
    token = getpass.getpass('BotFather Token（隐藏输入）：').strip()
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', token):
        print('Token 格式不正确。')
        return 1
    group = input('使用管理员群接单？[Y/n]：').strip().lower() not in {'n', 'no'}
    chat, owner = asyncio.run(pair(token, group))
    previous = dotenv_values(ROOT / '.env', interpolate=False) if (ROOT / '.env').exists() else {}
    database = previous.get('DATABASE_PATH') or str(Path.home() / '.local/share/print3d-data' / sha256(str(ROOT).encode()).hexdigest()[:16] / 'orders.sqlite3')
    webhook_secret = previous.get('WEBHOOK_SECRET', '')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', webhook_secret or ''):
        webhook_secret = secrets.token_hex(32)
    values = {'BOT_TOKEN': token, 'ADMIN_CHAT_ID': chat, 'ADMIN_USER_IDS': owner,
              'WEBHOOK_SECRET': webhook_secret, **ask_form(),
              'DATABASE_PATH': database}
    while True:
        payment = input('给客户的收款说明（单行，可先填“请联系管理员获取收款信息”）：').strip()
        if payment and len(payment) <= 1500:
            values['PAYMENT_INSTRUCTIONS'] = payment
            break
        print('请填写 1–1500 字的收款说明。')
    validate(values)
    write_env(values)
    print('配置已保存。管理员 ID、字段 ID 和密钥已自动处理。即将启动并生成 Google 配置文件。')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print('\n已取消。')
        raise SystemExit(1)
    except ValueError as exc:
        print(str(exc))
        raise SystemExit(1)
    except TelegramError as exc:
        print('Telegram 连接失败：' + type(exc).__name__ + '。检查网络、Token，关闭其他 ID 工具或 Bot 实例。')
        raise SystemExit(1)
    except Exception as exc:
        print('部署失败：' + type(exc).__name__ + '。未显示密钥或原始错误。')
        raise SystemExit(1)
