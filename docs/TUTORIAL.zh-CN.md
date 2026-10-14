# Print3D 小白部署教程

这份教程按“从没有安装，到收到第一个测试订单”的顺序写。照步骤操作即可，不要把 Token 或配置截图发给别人。

**先看这一步：Google 接单表单是必要前置条件。** 本项目提供 Telegram Bot 和订单后端，但没有第一阶段 Google Apps Script 的完整接单代码。你必须已经有可用的打印订单 Google Form，以及绑定该表单的 Stage 1 Apps Script、表单提交触发器和失败重试触发器。如果没有，请先向提供这套系统的人索取第一阶段代码并完成配置。仅创建空白 Google 表单不能接单。不要在没有这些文件的情况下继续部署。

## 第 1 步：准备账号和电脑

| 要准备什么 | 打开这里 | 说明 |
|---|---|---|
| Telegram 机器人 | [打开 BotFather](https://t.me/BotFather) | 创建自己的专用机器人，稍后复制 Token。Token 等同密码，不能公开。 |
| Google 账号和现有接单表单 | [Google Forms](https://forms.google.com) · [Google Apps Script](https://script.google.com) | 确认表单和第一阶段脚本已能接收订单。上传 STL 的客户可能需要登录 Google。 |
| Node.js | [Node.js LTS 下载](https://nodejs.org/zh-cn/download) | 下载适用于 Windows 的 LTS 安装包，保持默认选项安装。需要 22 或更新版本。 |
| Windows Linux 环境 | [Microsoft WSL 安装指南](https://learn.microsoft.com/zh-cn/windows/wsl/install) · [Ubuntu 24.04](https://apps.microsoft.com/detail/9nz3klhxdjp5) | 本项目在 Windows 上通过 WSL2 Ubuntu 运行。首次安装需要 Windows 管理员权限。 |
| 项目文件 | [GitHub 项目](https://github.com/Zhuan-05/print3) · [直接下载 ZIP](https://github.com/Zhuan-05/print3/archive/refs/heads/main.zip) | 仓库是私有的，必须先获得仓库访问权限并登录 GitHub，才能下载。 |

电脑需能访问 Telegram、Google、Cloudflare 和软件下载网站，并在 Bot 运行时保持开机、联网且不休眠。Quick Tunnel 会自动启动，试用不需购买域名，也不需创建 Cloudflare 账号。

## 第 2 步：先创建并检查 Bot

1. 在 Telegram 打开 [BotFather](https://t.me/BotFather)，发送 `/newbot`。
2. 按提示输入 Bot 显示名称和唯一用户名。用户名必须以 `bot` 结尾，例如 `MyPrint3D_bot`。
3. BotFather 会发给你一串 Token。复制并保存在自己的安全位置；稍后粘贴到安装窗口。不要发给管理员群、客户或公开聊天。
4. 在 Telegram 找到刚创建的 Bot，点 **Start/开始**。群接单时先创建一个私有管理员群，并把 Bot 加入。
5. 用自己的个人账号管理 Bot；群里不要启用匿名管理员身份，否则无法完成配对。

## 第 3 步：下载并解压项目

1. 使用表格中的 **直接下载 ZIP** 链接。浏览器提示登录时，用已有项目访问权限的 GitHub 账号登录。
2. 在 Windows 文件资源管理器中打开“下载”目录，右键 ZIP，选择“全部解压”。建议解压到简单路径，例如 `C:\print3d`。
3. 打开解压后的项目文件夹。你应该能看到 `package.json`、`deploy_print3d.bat`、`README.md` 等文件。

也可以使用 Git：先安装 [Git for Windows](https://git-scm.com/download/win)，然后打开命令提示符，运行：

```text
git clone https://github.com/Zhuan-05/print3.git
cd print3
```

## 第 4 步：安装 Node.js 和 WSL2

1. 安装 Node.js LTS 后，打开 Windows「命令提示符」或 PowerShell，运行：

```text
node -v
npm -v
```

两行都应显示版本号。若提示“不是内部或外部命令”，重新打开终端；仍不行就重新安装 Node.js。

2. 双击项目文件夹中的 `deploy_print3d.bat`。如果电脑还没有 WSL Ubuntu，程序会请求管理员权限安装。允许 Windows 弹窗后，如果提示重启，请先重启电脑。
3. 从 Windows「开始」菜单打开 **Ubuntu 24.04**。首次打开会让你创建 Linux 用户名和密码。输入密码时屏幕不会显示字符，这是正常的。记住这个密码，之后安装 Linux 组件时可能需要。
4. Ubuntu 初始化完成后，回到项目文件夹，再双击 `deploy_print3d.bat`。

## 第 5 步：运行安装向导

也可以在项目文件夹的地址栏输入 `cmd` 并按 Enter，打开命令窗口后运行：

```text
npm install
npm start
```

向导会自动安装 Linux/Python 依赖。第一次安装可能需要输入刚创建的 Ubuntu 密码，输入时不会显示字符。

按提示操作：

1. **Bot Token**：粘贴 BotFather 给你的 Token。输入隐藏时不显示字符，粘贴后按 Enter。
2. **管理方式**：接单管理员在群里处理订单就选群组；只在私聊里管理就选私聊。
3. **Telegram 配对**：先在 Telegram 私聊 Bot，发送窗口显示的 `/setup 随机码`。如果选择群组，向导会提示再把 Bot 加入的管理员群，并用同一账号发送 `/setup@你的Bot用户名 随机码`。命令必须是新消息。不要在 Telegram 聊天里贴 Token。
4. **Google 表单编辑链接**：回到已经配置好的打印订单 Google Form，确认题目包括 Telegram ID、绑定令牌、层高、填充率、材质及一个 STL 文件上传字段。
5. **制作预填链接**：在 Google Forms 表单右上角点「更多」→「预填表单」。找到 Telegram ID 题目，填 `123456789`；绑定令牌题目填 `PRINT3D_BINDING_TOKEN`。其他必填题也填任意测试值，然后点「获取链接」并复制。可参考 [Google 的预填表单帮助](https://support.google.com/docs/answer/2839588?hl=zh-Hans)。将链接粘贴回向导。
6. **收款说明**：输入客户付款时看到的一句话。还没准备正式说明时可填“请联系管理员获取收款信息”。

完成后程序会自动保存本机配置，启动订单服务和临时公网地址。以后启动会复用这些设置。

## 第 6 步：连接 Google Apps Script

1. 保持部署窗口打开，找到「配置脚本已复制到剪贴板」的提示。若没有这条提示，按窗口提供的文件路径打开私有配置文件并复制内容。该文件含 Webhook 密钥，不要发给其他人。
2. 打开表单对应的**现有第一阶段 Apps Script 项目**。在左侧点「添加文件」→「脚本」，新建文件。
3. 将剪贴板内容粘贴进去，保存。
4. 从上方函数列表选择 `configurePrint3D`，点「运行」。如果 Google 弹出授权窗口，选择表单所有者的 Google 账号并按提示授权。

这个小脚本只写入服务地址和密钥；它**不会**替代 Stage 1 接单代码，也不会替你创建表单提交/重试触发器。不要将它贴进一个没有 Stage 1 业务代码的空项目。

部署窗口显示的地址后加 `/healthz`，例如 `https://实际分配的地址.trycloudflare.com/healthz`。浏览器应该显示：

```json
{"ok":true}
```

## 第 7 步：测试第一张订单

1. 确认 Bot 仍在运行，部署窗口没有关闭。
2. 用另一个 Telegram 账号打开 Bot，点 **Start/开始**，再点「我要下单」。
3. 打开 Bot 发来的表单链接。上传一个小型 `.stl` 测试模型，填写打印参数后提交。Google 文件上传题可能要求测试客户登录 Google。
4. 等待管理员群收到新订单。记下通知中的订单编号，确认模型链接能打开。
5. 管理员在管理员群按实际订单编号报价，例如：

```text
/quote 1 35.50
```

把 `1` 换成真实订单编号，把 `35.50` 换成你的报价。用户收到报价后，跟随 Bot 按钮完成付款凭证流程。只有核对实际到账后，管理员才应确认付款。

## 日常启动和停止

下次运行，在项目目录双击 `deploy_print3d.bat`，或执行 `npm start`。服务运行时不要关掉窗口；按 `Ctrl+C` 正常停止。Quick Tunnel 每次重启都可能更换地址，所以重新启动后要在现有 Apps Script 项目再次粘贴新生成的配置，并运行 `configurePrint3D`。

修改 Bot 或 Google 表单配置时，运行 `npm run configure`，完成后运行 `npm start`。

## 常见问题

| 看到什么 | 怎么处理 |
|---|---|
| `node` 或 `npm` 找不到 | 安装 [Node.js LTS](https://nodejs.org/zh-cn/download)，关闭并重新打开命令窗口。 |
| Windows 提示需要 WSL/Ubuntu | 按提示允许安装并重启；从开始菜单打开 Ubuntu，完成用户名和密码设置，再启动部署。 |
| 配对等待超时 | Bot 必须先由管理员账号私聊 `/start`；重新运行 `npm start`，按新窗口的随机命令发送一条新消息。 |
| 表单没有订单通知 | 检查 Stage 1 代码、表单提交触发器、重试触发器是否已安装并授权；检查 `configurePrint3D` 是否在现有脚本项目运行。 |
| 再启动后表单失效 | 临时隧道 URL 已改变；在现有 Apps Script 项目更新配置并再次运行 `configurePrint3D`。 |
| 提示 Bot 已在其他地方运行 | 关闭旧的部署窗口和查询窗口。一个 Bot Token 同时只能有一个轮询服务。 |

如果仍无法继续，先复制终端最后几行错误文字并遮住 Token、私有链接及密钥，再寻求帮助。
