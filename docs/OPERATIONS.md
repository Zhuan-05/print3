# 部署与运维参考

日常使用请参阅 [README](../README.md)。首次配置由 `deploy_print3d.bat` 自动完成。

## 6. Cloudflare Tunnel：固定域名

假设你已有接入 Cloudflare 的域名。域名与 VPS 是否收费取决于你的现有资源；本方案不承诺整体永久免费。

1. 在 Cloudflare 控制台 Networking → Tunnels 创建隧道，选择服务器系统。
2. 按控制台生成的 token 安装命令启动连接器。典型命令如下，将 token 占位符换为控制台真实值，不要发到聊天或代码仓库：

```bash
sudo cloudflared service install YOUR_CLOUDFLARE_TUNNEL_TOKEN
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared --no-pager
```

3. 添加 Published application 路由：主机名例如 orders.your-domain.com，Service URL 为 http://127.0.0.1:8000。
4. GAS WEBHOOK_URL 使用 https://orders.your-domain.com/webhooks/google-form。
5. 此路由不要套交互式登录、验证码或浏览器挑战，否则 GAS 不能完成请求。当前协议只发送 X-Webhook-Secret；如果你另行启用 Cloudflare Access Service Token，必须同步扩展 GAS Header，不能仅启用登录墙。
6. 外部请求由 HTTPS Tunnel 进入；Python 仍只监听 127.0.0.1，不必开放公网 8000 端口。

Tunnel Token、Bot Token 与 WEBHOOK_SECRET 是三个不同用途的密钥，不能相互替代。

## 7. ngrok 替代方案

按 ngrok 官方安装指南安装 CLI，在控制台获得 authtoken 后执行：

```bash
ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN
ngrok http 8000
```

将 ngrok 显示的 HTTPS 地址加 /webhooks/google-form 后填入 GAS WEBHOOK_URL。检查账号方案、流量限制与域名分配；不要假设临时地址永久不变。Cloudflare 和 ngrok 二选一即可。

## 8. 作为 Linux 服务运行

停止前台进程。以下假设当前目录含解压后的 print3d 文件夹，服务账号尚未创建：

```bash
sudo useradd --system --home /opt/print3d --shell /usr/sbin/nologin print3d
sudo mkdir -p /opt/print3d
sudo cp -a print3d/. /opt/print3d/
sudo python3 -m venv /opt/print3d/.venv
sudo /opt/print3d/.venv/bin/python -m pip install -r /opt/print3d/requirements.txt
sudo chown -R root:print3d /opt/print3d
sudo chmod 0755 /opt/print3d
sudo chmod 0640 /opt/print3d/.env
sudo install -d -m 0700 -o print3d -g print3d /opt/print3d/data
sudo chown -R print3d:print3d /opt/print3d/data
sudo cp /opt/print3d/deploy/print3d.service /etc/systemd/system/print3d.service
sudo systemctl daemon-reload
sudo systemctl enable --now print3d
sudo systemctl status print3d --no-pager
```

注意：如果尚未创建真实 .env，先完成自动配置向导或按 `.env.example` 填写并确认配置，再运行 chmod / enable。若此前在其他目录创建过 .venv，复制后必须删除 /opt/print3d/.venv 并重新创建，因为 venv 不应跨路径搬迁。最省事的是直接从干净解压包安装。

查看日志、重启：

```bash
sudo journalctl -u print3d -n 100 --no-pager
sudo systemctl restart print3d
```

服务异常退出会被 systemd 重启；/healthz 检查 DB、后台任务与轮询新鲜度。长期 Telegram 网络故障、管理员群权限丢失、磁盘满仍需运维处理。应监测 /healthz、队列积压及 DEAD 数量，systemd 本身不会因 HTTP 健康检查失败自动重启。

## 9. 与第一阶段 GAS 的协议

POST /webhooks/google-form；Content-Type: application/json；Header: X-Webhook-Secret。

字段为 schema_version、source、event_id、form_id、response_id、submitted_at、telegram_id、binding_token、requirements、files、validation_errors，与第一阶段脚本一致。

- Header 错误：401，不接收业务数据。
- JSON 或事件身份结构损坏：400；GAS 保持重试，管理员修复配置。
- 请求超过 32 KiB：413；读入超时：408；格式不是 JSON：415。
- 空、非数字、越界 Telegram ID：200 + quarantined，事件与管理员预警原子入库。
- 数字 ID 被替换、绑定令牌错误、过期、已被另一事件使用：隔离，不创建订单。
- 第一次有效事件：200 + created；重复：200 + duplicate；已隔离事件重复：仍返回 quarantined。
- 数据库失败：503，GAS 重试。
- accepted=true 表示事件已持久化，管理员 Telegram 通知可能仍在队列中。

订单事件不记录原始令牌。业务字段和文件链接在订单表保存；隔离事件保存事件身份和原因，不保存任意原始请求正文。修复隔离原因后，请引导客户申请新链接重新提交；没有自动“重新认可已隔离事件”的危险快捷操作。

## 10. 客户与管理员操作

客户：/start 或 /order、/orders、/faq、/support、/end、/cancelproof，及对应中文菜单。

管理员（必须在指定群组且用户 ID 在白名单中）：

```text
/quote 1 35.50
/complete 1
/status
/reply R实际客服编号 回复内容
/close R实际客服编号
```

群里有多个 Bot 时，使用 /quote@你的Bot用户名 1 35.50 这样的显式命令。常规客服使用 Telegram 原生 Reply 回复 Bot 的客服标题或客户消息；/reply 仅作为映射丢失窗口的备用。只允许在仍活跃的同一人工会话中回复，结束后的旧消息不会再次路由给客户。

订单状态：PENDING_QUOTE → AWAITING_PAYMENT → PAYMENT_REVIEW → PROCESSING → COMPLETED。驳回凭证回到 AWAITING_PAYMENT。金额用 Decimal 解析后转整数 sen 存储，拒绝 NaN、科学计数法、负数与三位小数。

人工状态独立：BOT_MODE / HUMAN_SUPPORT。上传截图前客户必须点击指定订单的“提交付款凭证”；这样多订单不会错误关联。选中订单时，下一张有效图片优先作为凭证；想发普通客服图片可先 /cancelproof。

没有选择订单的普通客服图片不会自动当成付款截图。确认收款校验白名单、订单当前状态和当前凭证 ID；旧按钮与重复点击不会重复确认。按钮不会自动从旧消息上移除，但再次点击会明确返回“已处理或旧凭证”。

## 11. 四项关键验收

| 验收项 | 操作 | 预期 |
|---|---|---|
| 1. Webhook 安全与身份绑定 | 缺少/错误 Secret；正确 Secret 下提交空 ID、abc、另一用户的数字 ID；重复提交同一有效事件 | Secret 错误 401；非法 ID/令牌不匹配隔离并管理员预警；重复只创建一单 |
| 2. 报价与付款 FSM | 未报价发图；管理员报价；选订单上传；非白名单审核；驳回后重传；点击旧确认按钮；正确确认两次 | 未报价不保存凭证；有效上传进入 PAYMENT_REVIEW；越权/旧按钮无效；PROCESSING 只变更一次 |
| 3. 客服重启恢复 | 联系人工并发图；等待管理员收到消息；systemctl restart print3d；管理员 Reply；关闭会话再 Reply 旧消息 | 重启后从 SQLite 找到正确客户；结束后的旧会话不能继续回复 |
| 4. 故障重试与幂等 | 暂停后端提交 Form，再启动、运行 GAS retryPending；中断 Telegram 网络后恢复；重复表单事件；模拟数据库入库失败 | GAS 最终收到 ACK；单事件单订单；通知队列恢复发送；数据库失败不留下半成品订单 |

运行自动化覆盖：

```bash
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

自动化测试不调用你的真实 Telegram / Google 账号。测试通过不等于已经替你完成公网部署；正式接单前需要用真实 Form、管理员群和小额测试付款完成上述验收。

## 12. 数据维护与故障处理

本机检查（/opt/print3d 为工作目录）：

```bash
cd /opt/print3d
sudo -u print3d .venv/bin/python manage.py status
sudo -u print3d .venv/bin/python manage.py quarantined
sudo install -d -m 0700 -o print3d -g print3d /var/backups/print3d
sudo -u print3d .venv/bin/python manage.py backup /var/backups/print3d/orders-2026-10-14.sqlite3
```

备份文件名必须每次不同。工具使用 SQLite backup API，可以在线生成一致性备份；不要只复制活跃数据库的 .sqlite3 而遗漏 WAL。

死信在解决实际原因后可重试。例如 outbox 任务 42：

```bash
sudo -u print3d .venv/bin/python manage.py retry outbox 42
```

inbox 使用 Telegram update_id。仅 DEAD 状态可手动重试，SENT 状态不会重发。恢复数据库备份时先停止服务，另存整个原 data 目录，再在新的 data 目录放入备份并恢复所有权；恢复旧备份可能使事件重新处理，需核对业务账目，不要将旧备份覆盖到运行中的 WAL 数据库。

## 13. 边界与已知限制

- 这是按单机生产部署方式编写并离线验证的实现；没有真实商家账号，未进行线上端到端验收或正式安全审计。
- Google Drive 文件继续保持权限控制；后端不公开模型、不从任意 URL 下载文件。扩展名和大小校验不等于 STL 内容有效，报价前必须人工在切片软件检查。
- Telegram/Google 的服务故障与配额不能被本地代码消除。Telegram 服务端未领取的更新最多保留约 24 小时，长时间完全停机可能丢失尚未入库的消息。
- Telegram API 发送和 SQLite 提交不是一个分布式事务。发送成功但记账前崩溃，重试可能重复通知；稳定订单号与凭证版本保证不会重复建单/重复收款状态迁移。
- 管理员消息映射在 Telegram 返回消息 ID 后立即写入。极端崩溃窗口可能让某一条副本没有映射；请回复客服标题，或使用标题中的客服编号 /reply。客服编号在发送前已经持久化。
- copyMessage 的源消息若在送达前被删除，任务可能进入 DEAD；付款凭证使用 Telegram file_id 重发，减少对原消息的依赖。
- 管理员群消息按约每 3.1 秒一条发送，客户私聊按约每 1.05 秒一条；仍遵守 Telegram 返回的 RetryAfter。突发高峰会排队。
- 日常维护应设置备份、磁盘/队列/健康监控，并依据业务保留政策清理历史订单与付款凭证；代码不擅自删除财务记录。
- 本版本不包含自动退款、订单取消、改价、运费计算、多租户、自动切片或自动认款。管理员人工核对实际到账后才确认收款。

## 14. 官方参考

- Telegram Bot API: https://core.telegram.org/bots/api
- Telegram FAQ / privacy mode: https://core.telegram.org/bots/faq
- python-telegram-bot 22.6: https://docs.python-telegram-bot.org/en/v22.6/
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/get-started/
- Quick Tunnels: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- Cloudflare package repository: https://pkg.cloudflare.com/
- ngrok: https://ngrok.com/docs/start
