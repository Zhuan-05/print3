# Print3D beginner deployment guide

This guide takes you from a new computer setup to your first test order. Follow the steps in order. Never share your bot token or screenshots that show secrets.

**First, check the Google Forms prerequisite.** This repository provides the Telegram bot and Stage 2 order backend. It does not include the complete Stage 1 Google Apps Script that receives form submissions. You need an existing 3D-print order form, its Stage 1 Apps Script, an installed form-submission trigger, and an installed retry trigger. If you do not have them, ask the person who supplied the original system for the Stage 1 code and setup before continuing. A blank Google Form by itself cannot create orders.

**Language / 语言:** [简体中文](TUTORIAL.zh-CN.md) | English

## 1. Prepare your accounts and computer

| What you need | Open directly | Details |
|---|---|---|
| A Telegram bot | [Open BotFather](https://t.me/BotFather) | Create your own dedicated bot. You will copy its token during setup. Keep it private. |
| A Google account and an existing order form | [Google Forms](https://forms.google.com) · [Google Apps Script](https://script.google.com) | Confirm the form and Stage 1 script can already receive orders. Customers may need a Google account to upload STL files. |
| Node.js | [Download Node.js LTS](https://nodejs.org/en/download) | Install the Windows LTS installer, keeping its default options. Version 22 or newer is required. |
| Linux on Windows | [Microsoft WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install) · [Ubuntu 24.04](https://apps.microsoft.com/detail/9nz3klhxdjp5) | The Windows deployment runs in WSL2 Ubuntu. First-time installation requires Windows administrator permission. |
| Project files | [GitHub repository](https://github.com/Zhuan-05/print3) · [Download ZIP](https://github.com/Zhuan-05/print3/archive/refs/heads/main.zip) | This repository is private. Sign in to a GitHub account that has access before downloading. |

Your computer needs internet access to Telegram, Google, Cloudflare, and software download sites. Keep it on and awake while the bot runs. The temporary Quick Tunnel starts automatically; for a trial you do not need a domain or a Cloudflare account.

## 2. Create and check your bot

1. Open [BotFather](https://t.me/BotFather) in Telegram and send `/newbot`.
2. Follow the prompts to choose a display name and a unique username. The username must end in `bot`, for example `MyPrint3D_bot`.
3. BotFather will send a token. Copy it and keep it somewhere private. You will paste it into the setup window later. Do not post it in a group, send it to customers, or put it in a screenshot.
4. Open your new bot in Telegram and press **Start**. For group order management, create a private admin group and add the bot to it.
5. Pair with your personal Telegram account. Anonymous admin mode cannot be used for pairing.

## 3. Download and extract the project

1. Click **Download ZIP** in the table above. If GitHub asks you to sign in, use an account that has access to this private repository.
2. In Windows File Explorer, open Downloads, right-click the ZIP, and choose **Extract All**. A short folder such as `C:\print3d` is recommended.
3. Open the extracted project folder. You should see files such as `package.json`, `deploy_print3d.bat`, and `README.md`.

Alternatively, install [Git for Windows](https://git-scm.com/download/win), open Command Prompt, and run:

```text
git clone https://github.com/Zhuan-05/print3.git
cd print3
```

## 4. Install Node.js and WSL2

1. Install Node.js LTS. Open Windows Command Prompt or PowerShell and run:

```text
node -v
npm -v
```

Both commands should display version numbers. If Windows says a command is not recognized, reopen the terminal. If that does not help, reinstall Node.js.

2. Double-click `deploy_print3d.bat` in the project folder. If WSL Ubuntu is missing, the installer asks for administrator permission. Approve the Windows prompt. Restart Windows if asked.
3. Open **Ubuntu 24.04** from the Windows Start menu. On its first launch, create a Linux username and password. Nothing appears on screen while you type the password; this is normal. Remember it because you may need it to install Linux components.
4. After Ubuntu setup finishes, return to the project folder and double-click `deploy_print3d.bat` again.

## 5. Run the setup wizard

You can also type `cmd` into the project folder's File Explorer address bar and press Enter. In the command window, run:

```text
npm install
npm start
```

The wizard installs Linux and Python dependencies automatically. The first install may ask for your Ubuntu password; typed characters are not displayed.

Follow the prompts:

1. **Bot token:** Paste the token from BotFather. The input is hidden. Press Enter after pasting.
2. **Admin mode:** Choose group if you will manage orders in an admin group, or private chat if you will manage them privately.
3. **Telegram pairing:** In Telegram, privately message your bot with the `/setup one-time-code` shown in the terminal. For group mode, the wizard then asks you to send `/setup@YourBotUsername one-time-code` in the admin group using the same account. Send it as a new message. Never paste your token into Telegram.
4. **Google Form edit link:** Open your existing 3D-print order form. Confirm it has questions for Telegram ID, binding token, layer height, infill, material, and one STL file upload.
5. **Create a prefilled link:** In Google Forms, click **More** in the top-right corner, then **Pre-fill form**. Enter `123456789` in the Telegram ID question and `PRINT3D_BINDING_TOKEN` in the binding-token question. Fill any other required questions with sample values, click **Get link**, and copy it. See [Google's prefilled form instructions](https://support.google.com/docs/answer/2839588?hl=en). Paste the link into the setup window.
6. **Payment instructions:** Enter a short instruction customers will see. If needed, start with “Contact the administrator for payment details.”

The program saves your local configuration and starts the order service and a temporary public URL. Future starts reuse the saved settings.

## 6. Connect Google Apps Script

1. Keep the deployment window open. Look for the message that the setup script was copied to the clipboard. If it was not copied, use the private file path shown in the terminal and copy its contents. This file contains a webhook secret; do not share it.
2. Open the **existing Stage 1 Apps Script project** attached to the form. In the left sidebar, click **Add file** → **Script**.
3. Paste the copied contents into the new file and save.
4. Select `configurePrint3D` in the function list and click **Run**. If Google shows an authorization prompt, select the form owner's Google account and follow the prompts.

This small script only saves the service URL and secret. It does **not** replace the Stage 1 order-processing code and does not create form submission or retry triggers. Do not paste it into an empty Apps Script project that has no Stage 1 code.

Open the public address shown by the deployment window followed by `/healthz`, for example `https://your-assigned-name.trycloudflare.com/healthz`. The page should show:

```json
{"ok":true}
```

## 7. Test your first order

1. Confirm the bot is still running and the deployment window is open.
2. From a different Telegram account, open the bot, press **Start**, and choose **Place an order**.
3. Open the form link sent by the bot. Upload a small test `.stl`, enter the print settings, and submit. The Google file upload question may require the test customer to sign in to Google.
4. Wait for the new order notification in the admin group. Note the order number and check that the model link opens.
5. In the admin group, quote using the actual order number. For example:

```text
/quote 1 35.50
```

Replace `1` with the order number and `35.50` with your quote. The customer can then follow the bot's buttons to submit payment proof. Confirm payment only after you verify that the money arrived.

## Start and stop the bot

For later runs, double-click `deploy_print3d.bat` in the project folder or run `npm start`. Keep the window open while the service runs. Press Ctrl+C to stop it. Quick Tunnel may assign a new URL after every restart. When it changes, paste the newly generated script into the existing Apps Script project and run `configurePrint3D` again.

To change bot or form settings, run `npm run configure`, then run `npm start`.

## Common problems

| Problem | What to do |
|---|---|
| `node` or `npm` is not recognized | Install [Node.js LTS](https://nodejs.org/en/download) and reopen the terminal. |
| Windows asks for WSL/Ubuntu | Approve the installation and restart if asked. Open Ubuntu from the Start menu, create a username and password, then run deployment again. |
| Pairing times out | First open the bot and press **Start** from the admin account. Run `npm start` again and send the new one-time command as a new message. |
| No order notification arrives | Check that Stage 1 code, the form-submission trigger, and retry trigger are installed and authorized. Confirm you ran `configurePrint3D` in the existing script project. |
| The form stops working after a restart | The temporary tunnel URL changed. Update the configuration in the existing Apps Script project and run `configurePrint3D` again. |
| It says the bot is already running elsewhere | Close the old deployment and ID lookup windows. A bot token can only be polled by one service at a time. |

If you still need help, copy the last few lines from the terminal and remove any token, private link, or secret before sharing them.
