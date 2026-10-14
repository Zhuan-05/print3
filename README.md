# Print3D

**Language:** English | [简体中文](README.zh-CN.md)

A Telegram order and customer support system for 3D printing. Use npm to prepare and run the deployment, or double-click the Windows launcher. Node.js manages deployment; the order processing backend runs on Python, which is installed automatically.

## Beginner setup

Follow these steps in order. Node.js manages deployment; the order backend and its dependencies are prepared automatically.

| Step | What you need | Open directly |
|---|---|---|
| 1. Install Node.js | Install the current LTS release (version 22 or newer), then reopen your terminal | [Download Node.js](https://nodejs.org/en/download) |
| 2. Prepare the runtime | On Windows, install WSL2 and Ubuntu 24.04. On Linux, use Ubuntu/Debian and an account with installation permissions | [Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install) · [Ubuntu 24.04](https://apps.microsoft.com/detail/9nz3klhxdjp5) |
| 3. Create a Telegram bot | Create a dedicated bot with BotFather and copy its token. For group-based orders, create a group and add the bot | [Open Telegram BotFather](https://t.me/BotFather) |
| 4. Prepare the order form | Use a Google Form that already has the Stage 1 order-processing Apps Script and its submission/retry triggers installed and authorized. A Google account is required | [Google Forms](https://forms.google.com) · [Google Apps Script](https://script.google.com) |
| 5. Get the project | Cloning the private repository requires a GitHub account with access. You can also download the release archive | [Open the GitHub repository](https://github.com/Zhuan-05/print3) · [Download ZIP](https://github.com/Zhuan-05/print3/archive/refs/heads/main.zip) |

> **The Google Form is a prerequisite.** It must include Telegram ID, binding token, layer height, infill, material, and one STL upload field. The Stage 1 Apps Script and its triggers must already be installed and authorized. This repository does not include the complete Stage 1 `Code.gs`; a new blank form cannot receive orders by itself. Customers may need to sign in to Google to upload an STL.

Prepare a short payment instruction for customers, such as “Contact the administrator for payment details.” You do not need a DeepSeek or OpenAI API key. Quick Tunnel starts automatically, so you do not need a Cloudflare account or domain for a trial. Its URL may change after a restart.

### Install and start

**Windows:** If cloning from GitHub, make sure your account has access to the private repository.

```bash
git clone https://github.com/Zhuan-05/print3.git
cd print3
npm install
npm start
```

Alternatively, download the ZIP above, extract it, open a terminal in the `print3-main` folder, then run `npm install` and `npm start`. If Windows asks to install WSL, allow the administrator prompt. Open Ubuntu once to create a Linux username and password, then run the commands. You can also double-click `deploy_print3d.bat`.

**Ubuntu/Debian:** Open a terminal in the project folder and run:

```bash
npm install
npm start
```

Enter your Linux password if asked to install system components; password characters are not shown. Run Linux deployments as a regular user, not root. Keep the computer connected to the internet and prevent it from sleeping.

Follow the terminal prompts to enter the bot token, pair your Telegram account, provide the form link, and add payment instructions. For the initial Google setup, paste the generated script into the existing Apps Script project and run `configurePrint3D`.

| Command | Purpose |
|---|---|
| `npm start` | Install dependencies, configure on first run, and start. Later runs reuse the existing configuration. |
| `npm run setup` | Prepare the runtime without starting the bot. |
| `npm run configure` | Reconfigure the service. |
| `npm run build` | Create the shareable `dist/print3d-autodeploy.zip` archive. |
| `npm test` | Check the npm deployment entry point. |
| `npm run test:backend` | Install test dependencies and run backend tests without sending real messages. |

## First run

- On Windows, the launcher checks for Ubuntu on WSL. If none is installed, it requests administrator permission to install Ubuntu 24.04. Restart Windows if prompted, open Ubuntu once to create a Linux username and password, then run the launcher again. System installation and account authorization require your input.
- The launcher installs Linux dependencies, creates a Python environment, and downloads the pinned dependencies. The first Linux setup may ask for your sudo password; password characters are not displayed.
- Paste your bot token into the setup prompt. The input is hidden. Choose group or private-chat administration.
- Send the one-time `/setup` command shown in the terminal to your bot in a private chat. For group administration, send the displayed `/setup@YourBotUsername` command in the group using the same Telegram account. The setup reads your administrator and group IDs automatically. You do not need to look up IDs or edit `.env`. Anonymous group admins cannot pair.
- Paste the Google Form edit link. In Google Forms, select **Get pre-filled link**. Enter `123456789` for the Telegram ID field and `PRINT3D_BINDING_TOKEN` for the binding-token field. Fill other required fields with sample values, generate the link, and paste it into the terminal. Setup extracts the Form ID, public URL, and field IDs.
- Enter your payment instructions. Setup generates a secret, saves your configuration, and starts the backend and a temporary public tunnel.
- After startup, the setup script is copied to the Windows clipboard. In the **existing Stage 1 Apps Script**, add a script file, paste the contents, and run `configurePrint3D`. This sets `WEBHOOK_URL` and `WEBHOOK_SECRET`; it does not replace the order-processing code or install triggers. If clipboard access is unavailable, the terminal shows the private file path.
- Open the public URL shown in the terminal followed by `/healthz`; expect `{"ok":true}`. From a customer account, send `/start`, submit a test order, and confirm the administrator receives it.

## Later runs and configuration

Run `npm start` or double-click `deploy_print3d.bat` again. The launcher reuses your configuration and database. Keep the terminal open while the service runs; press Ctrl+C to stop it. Quick Tunnel URLs can change after a restart. When they do, paste the newly generated script into Google Apps Script and run it again.

To change the bot, form, or other settings, run `npm run configure`. With the BAT launcher, use `deploy_print3d.bat reconfigure`. After npm configuration finishes, run `npm start`. Regular starts do not overwrite a complete configuration. Reconfiguration preserves the existing database path and valid webhook secret. Back up your data before changing the bot or administrator.

## Production hosting

The automatic local deployment is intended for testing and demonstrations. Cloudflare Quick Tunnels use temporary URLs and do not guarantee production availability. For a stable deployment, provide an Ubuntu VPS, a fixed HTTPS domain, and a named Cloudflare Tunnel, then follow sections 6 and 8 in the [operations guide](docs/OPERATIONS.md). You must provide the VPS, domain, and account authorizations. The Windows launcher does not create a cloud server or an automatic startup task.

## Release and data

Share `dist/print3d-autodeploy.zip` instead of a configured project folder. The archive excludes `.env`, credentials, order databases, logs, and private Google configuration. Each business should use its own bot, form, and installation folder.

By default, the database is stored under `~/.local/share/print3d-data/<project-hash>/` on Linux or WSL, away from the Windows mounted drive. Existing configurations keep their current database path. The virtual environment and private Google configuration are under `~/.local/share/print3d-launcher/<project-hash>/`. See the [operations guide](docs/OPERATIONS.md) for online SQLite backups. That guide is currently in Chinese.

Troubleshooting: close an old launcher or ID tool if another instance is running. If Telegram cannot be reached, check the WSL or Linux network. If an order does not arrive, check that the Stage 1 script and triggers are installed and that the Google configuration has been applied. The launcher does not remove an existing Telegram webhook or change your proxy or firewall settings.

References: [Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install) · [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

## Project layout

- `package.json`: npm commands. `deploy_print3d.bat`: Windows launcher.
- `auto_setup.py`, `app/`, `scripts/`: setup wizard, order backend, and deployment tools.
- `manage.py`: order status, backup, and retry operations.
- `docs/`, `deploy/`: operations reference and Linux service configuration.
- `tests/`: automated tests.
- `dist/`: clean shareable release archive, generated with `npm run build`.

## License

This project is licensed under the [MIT License](LICENSE).
