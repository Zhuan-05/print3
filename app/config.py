from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_chat_id: int
    admin_user_ids: frozenset[int]
    webhook_secret: str
    form_id: str
    form_url: str
    telegram_entry: str
    binding_entry: str
    db_path: str = "data/orders.sqlite3"
    payment_instructions: str = "请联系人工客服取得收款信息，转账备注订单号。"

    @classmethod
    def load(cls):
        load_dotenv()
        required = ["BOT_TOKEN", "ADMIN_CHAT_ID", "ADMIN_USER_IDS", "WEBHOOK_SECRET",
                    "GOOGLE_FORM_ID", "GOOGLE_FORM_URL", "FORM_TELEGRAM_ENTRY", "FORM_BINDING_ENTRY"]
        for key in required:
            if not os.getenv(key, "").strip():
                raise ValueError(f"Missing environment variable: {key}")
        obj = cls(
            bot_token=os.environ["BOT_TOKEN"].strip(),
            admin_chat_id=int(os.environ["ADMIN_CHAT_ID"]),
            admin_user_ids=frozenset(int(x.strip()) for x in os.environ["ADMIN_USER_IDS"].split(",")),
            webhook_secret=os.environ["WEBHOOK_SECRET"].strip(),
            form_id=os.environ["GOOGLE_FORM_ID"].strip(),
            form_url=os.environ["GOOGLE_FORM_URL"].strip(),
            telegram_entry=os.environ["FORM_TELEGRAM_ENTRY"].strip(),
            binding_entry=os.environ["FORM_BINDING_ENTRY"].strip(),
            db_path=os.getenv("DATABASE_PATH", "data/orders.sqlite3"),
            payment_instructions=os.getenv("PAYMENT_INSTRUCTIONS", cls.payment_instructions),
        )
        if not re.fullmatch(r"[a-fA-F0-9]{64}", obj.webhook_secret):
            raise ValueError("WEBHOOK_SECRET must be 64 hexadecimal characters")
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", obj.bot_token):
            raise ValueError("Invalid BOT_TOKEN format")
        if obj.admin_chat_id == 0 or not obj.admin_user_ids or min(obj.admin_user_ids) <= 0:
            raise ValueError("Use a nonzero chat ID and positive administrator user IDs")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", obj.form_id):
            raise ValueError("Invalid GOOGLE_FORM_ID")
        parsed = urlsplit(obj.form_url)
        if (parsed.scheme != "https" or parsed.netloc != "docs.google.com" or
                not re.fullmatch(r"/forms/d/e/[A-Za-z0-9_-]+/viewform", parsed.path) or
                parsed.query or parsed.fragment):
            raise ValueError("GOOGLE_FORM_URL must be the full public viewform URL without query parameters")
        for entry in (obj.telegram_entry, obj.binding_entry):
            if not re.fullmatch(r"entry\.\d+", entry):
                raise ValueError("Entry keys must have the form entry.12345")
        if obj.telegram_entry == obj.binding_entry:
            raise ValueError("Form entry keys must differ")
        if len(obj.payment_instructions) > 1500:
            raise ValueError("PAYMENT_INSTRUCTIONS is too long")
        return obj
