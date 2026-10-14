# Print3D

**语言 / Language:** 中文 | [English](README.md)

Telegram 3D 打印接单系统，支持 npm 部署或 Windows 双击启动。Node.js 负责安装和启动，接单后端使用 Python；程序会自动准备 Python 虚拟环境和依赖。

## 小白完整教程

第一次部署请按[小白部署教程](docs/TUTORIAL.zh-CN.md)从准备账号到测试首单逐步操作。

## 小白快速部署

按顺序完成下面几步。Node.js 负责部署，业务后端和依赖会自动准备。

| 步骤 | 需要准备 | 直接打开 |
|---|---|---|
| 1. 安装 Node.js | 安装 LTS 版本（22 或更新），安装完成后重新打开终端 | [Node.js 下载](https://nodejs.org/zh-cn/download) |
| 2. 准备运行环境 | Windows 用户安装 WSL2 和 Ubuntu 24.04；Linux 用户需要 Ubuntu/Debian 和安装权限 | [Windows WSL 安装指南](https://learn.microsoft.com/zh-cn/windows/wsl/install) · [Ubuntu 24.04 下载](https://apps.microsoft.com/detail/9nz3klhxdjp5) |
| 3. 创建 Telegram Bot | 在 BotFather 创建专用 Bot，复制 Token；群接单时先建群并把 Bot 拉进群 | [打开 Telegram BotFather](https://t.me/BotFather) |
| 4. 准备接单表单 | 使用已经安装第一阶段接单 Apps Script 和提交/重试触发器的 Google Form；需要 Google 账号 | [Google Forms](https://forms.google.com) · [Google Apps Script](https://script.google.com) |
| 5. 获取项目 | 私有仓库需要 GitHub 账号有访问权限；也可下载下方分享包 | [打开 GitHub 仓库](https://github.com/Zhuan-05/print3) · [下载 ZIP](https://github.com/Zhuan-05/print3/archive/refs/heads/main.zip) |

> **Google 表单是必要前置条件：**表单需包含 Telegram ID、绑定令牌、层高、填充率、材质和一个 STL 上传字段，而且第一阶段 Apps Script 与触发器必须已经安装并授权。本仓库不包含完整的第一阶段 `Code.gs`；新建空白表单还不能接单。上传 STL 的客户可能需要登录 Google。

准备一句给客户看的收款说明即可，例如“请联系管理员获取收款信息”。不需要 DeepSeek 或 OpenAI API Key。Quick Tunnel 由程序自动启动，不用注册 Cloudflare 账号或购买域名；它适合试用，重启后地址可能变化。

### 安装和启动

**Windows：**如果从 GitHub 克隆，请先确保账号能访问私有仓库。

```bash
git clone https://github.com/Zhuan-05/print3.git
cd print3
npm install
npm start
```

也可以下载上表中的 ZIP，解压后进入 `print3-main` 目录，运行 `npm install` 和 `npm start`。首次安装 WSL 时按提示允许管理员安装，打开 Ubuntu 创建 Linux 用户名和密码后再运行命令。你也可以双击 `deploy_print3d.bat` 启动。

**Ubuntu/Debian：**在项目目录打开终端，运行：

```bash
npm install
npm start
```

安装系统组件时输入 Linux 密码（输入过程不显示字符）。Linux 建议用普通用户运行，不要用 root。电脑需保持联网并避免休眠。

启动后跟随终端提示输入 Bot Token、完成 Telegram 配对、提供表单链接和收款说明。首次 Google 配置需要把自动生成的脚本粘贴到已有 Apps Script 项目，再运行 `configurePrint3D`。

| 命令 | 用途 |
|---|---|
| `npm start` | 自动安装依赖，首次配置并启动；以后直接复用已有配置 |
| `npm run setup` | 只准备运行环境，不启动 Bot |
| `npm run configure` | 重新配置 |
| `npm run build` | 生成 `dist/print3d-autodeploy.zip` 分享包 |
| `npm test` | 检查 npm 部署入口 |
| `npm run test:backend` | 安装测试依赖并运行后端测试（不发送真实消息） |

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

运行 `npm start` 或双击同一个 `deploy_print3d.bat`，自动复用配置和数据库。保持窗口开启；Ctrl+C 停止服务。Quick Tunnel 地址可能每次变化，重新启动后要把新生成的配置脚本粘贴到 Google 并运行一次。

需要修改账号或表单配置时，运行 `npm run configure`；使用 BAT 时可运行 `deploy_print3d.bat reconfigure`。npm 配置完成后再运行 `npm start`。完整配置不会在日常启动时被覆盖；重新配置保留已有数据库路径和有效 Webhook Secret。修改 Bot 或管理员前请备份并确认业务归属。

## 长期接单部署

当前自动入口适用于本机试用和演示。Quick Tunnel 为临时地址，不保证生产可用性；它不能实现无需更新 Google 配置的长期部署。长期运行准备 Ubuntu VPS、固定 HTTPS 域名及 Cloudflare 固定隧道，按 [运维说明](docs/OPERATIONS.md) 第 6、8 节安装服务。VPS、域名和账号授权仍需使用者提供。Windows 自动入口不会自动创建开机任务或云服务器。

## 分享与数据

分享 `dist/print3d-autodeploy.zip`，不要分享已经配置过的整个项目目录。包不含 `.env`、真实密钥、订单数据库、日志或私有 Google 配置。每个商家使用自己的机器人、表单和安装目录。

数据库默认在 Linux/WSL 的 `~/.local/share/print3d-data/<项目摘要>/`，与 Windows 挂载盘分开。已有配置沿用其数据库位置。环境和私有 Google 配置在 `~/.local/share/print3d-launcher/<项目摘要>/`。数据库按 [运维说明](docs/OPERATIONS.md) 使用 SQLite 在线备份。

排障：重复实例先关闭旧 BAT 或 ID 工具；Telegram 无法连接时检查 WSL 网络；表单不出单先确认第一阶段脚本和触发器已安装、Google 配置已应用。程序不会自动删除已有 Telegram Webhook，也不会自动修改代理或防火墙。

官方说明：[WSL 安装](https://learn.microsoft.com/en-us/windows/wsl/install)、[Cloudflare 临时隧道](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)。

## 项目结构

- `package.json`：npm 部署命令；`deploy_print3d.bat`：Windows 双击入口。
- `auto_setup.py`、`app/`、`scripts/`：配置向导、接单后端和部署工具。
- `manage.py`：订单状态、备份及重试工具。
- `docs/`、`deploy/`：运维参考和服务器服务配置。
- `tests/`：自动化验证。
- `dist/`：可分享的干净安装包，运行 `npm run build` 重新生成。

## 许可证

本项目采用 [MIT License](LICENSE)。
