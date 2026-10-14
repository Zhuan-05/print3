# 双击部署 Print3D

把整个分享包解压到固定目录，双击 `deploy_print3d.bat`。不要只复制 BAT。

## 使用者需要准备什么

1. Windows 10/11、管理员安装权限和稳定网络（能访问 Telegram、Google、Python 软件源和 Cloudflare）。电脑运行期间不能休眠。
2. 自己向 Telegram `@BotFather` 创建的专用机器人 Token，以及自己的 Telegram 账号。群接单时先建管理群并加入机器人。
3. **已完成第一阶段接单脚本的 Google 表单**：包含 Telegram ID、绑定令牌、层高、填充率、材质、单个 STL 上传字段；原来的表单提交及失败重试触发器已安装并授权。这个第二阶段包不含第一阶段完整 Code.gs，不能把空白表单当成已接通的表单。
4. 收款说明。可以先填“请联系管理员获取收款信息”。不需要 DeepSeek 或 OpenAI API Key。

## 首次使用

- 自动检查 WSL Ubuntu。未安装时请求 Windows 管理员权限安装 Ubuntu 24.04。按 Windows 提示重启，首次打开 Ubuntu 创建 Linux 用户名/密码，再双击 BAT。系统安装和账号授权不能跳过。
- 自动安装 Linux 依赖、创建 Python 环境、下载锁定依赖。首次安装可能需要输入 Linux 密码；输入时不显示字符。
- 在窗口粘贴 Token（隐藏输入），选择群接单或私聊管理。
- 按窗口显示的随机 `/setup` 命令私聊机器人；群模式再用同一账号在群里发送带 Bot 用户名的命令。管理员和群 ID 自动识别，无需查 ID 或编辑 `.env`。匿名管理员不能配对。
- 粘贴表单编辑链接。Google 表单菜单选择“获取预填链接”：Telegram ID 填 `123456789`，绑定令牌填 `PRINT3D_BINDING_TOKEN`，其他字段按需填测试值，生成链接后粘贴到窗口。程序自动提取 Form ID、公开 URL 和两个 entry ID。
- 输入收款说明，程序自动生成密钥、保存配置、启动后端和临时公网隧道。
- 启动成功后会把配置脚本复制到 Windows 剪贴板。在**现有第一阶段 Apps Script** 新建脚本文件，粘贴并运行 `configurePrint3D`。脚本只设置 `WEBHOOK_URL` 和 `WEBHOOK_SECRET`，不替代业务代码、不安装触发器。若剪贴板不可用，窗口会显示私有文件路径。
- 打开窗口显示的公网地址加 `/healthz`，确认 `{"ok":true}`。用客户账号 `/start` 获取新链接，提交一份真实测试表单，确认管理员收到新订单。

## 再次使用

双击同一个 `deploy_print3d.bat`，自动复用配置和数据库。保持窗口开启；Ctrl+C 停止服务。Quick Tunnel 地址可能每次变化，重新启动后要把新生成的配置脚本粘贴到 Google 并运行一次。

需要修改账号或表单配置时，在 CMD 中运行 `deploy_print3d.bat reconfigure`。完整配置不会在日常启动时被覆盖；重新配置保留已有数据库路径和有效 Webhook Secret。修改 Bot 或管理员前请备份并确认业务归属。

## 长期接单部署

当前自动入口适用于本机试用和演示。Quick Tunnel 为临时地址，不保证生产可用性；它不能实现无需更新 Google 配置的长期部署。长期运行准备 Ubuntu VPS、固定 HTTPS 域名及 Cloudflare 固定隧道，按 [运维说明](docs/OPERATIONS.md) 第 6、8 节安装服务。VPS、域名和账号授权仍需使用者提供。Windows 自动入口不会自动创建开机任务或云服务器。

## 分享与数据

分享 `dist/print3d-autodeploy.zip`，不要分享已经配置过的整个项目目录。包不含 `.env`、真实密钥、订单数据库、日志或私有 Google 配置。每个商家使用自己的机器人、表单和安装目录。

数据库默认在 WSL 的 `~/.local/share/print3d-data/<项目摘要>/`，与 Windows 挂载盘分开。已有配置沿用其数据库位置。环境和私有 Google 配置在 `~/.local/share/print3d-launcher/<项目摘要>/`。数据库按 [运维说明](docs/OPERATIONS.md) 使用 SQLite 在线备份。

排障：重复实例先关闭旧 BAT 或 ID 工具；Telegram 无法连接时检查 WSL 网络；表单不出单先确认第一阶段脚本和触发器已安装、Google 配置已应用。程序不会自动删除已有 Telegram Webhook，也不会自动修改代理或防火墙。

官方说明：[WSL 安装](https://learn.microsoft.com/en-us/windows/wsl/install)、[Cloudflare 临时隧道](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)。

## 项目结构

- `deploy_print3d.bat`：唯一 Windows 部署及启动入口。
- `auto_setup.py`、`app/`、`scripts/`：配置向导、接单后端和部署工具。
- `manage.py`：订单状态、备份及重试工具。
- `docs/`、`deploy/`：运维参考和服务器服务配置。
- `tests/`：自动化验证。
- `dist/`：可分享的干净安装包，运行 `python3 scripts/build_release.py` 重新生成。
