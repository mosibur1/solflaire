
---

<h1 align="center">Solflarekingdom Bot</h1>

<p align="center">
<strong>Boost your productivity with Solflarekingdom – your friendly automation tool that handles key tasks with ease!</strong>
</p>

<p align="center" style="display: flex; justify-content: center; gap: 8px; flex-wrap: wrap;">
  <a href="https://codeberg.org/livexords/ddai-bot/actions" style="display: inline-block;">
    <img src="https://img.shields.io/badge/build-passed-brightgreen" alt="Build Status" />
  </a>
  <a href="https://t.me/livexordsscript" style="display: inline-block;">
    <img src="https://img.shields.io/badge/Telegram-Join%20Group-2CA5E0?logo=telegram&style=flat" alt="Telegram Group" />
  </a>
</p>

---

## 🚀 About the Bot

Solflarekingdom Bot is your automation buddy designed to simplify daily operations. This bot takes over repetitive tasks so you can focus on what really matters. With Solflarekingdom Bot, you get:

---

# 🎯 **✨ Core Bot Features**

- **Auto Daily Claim 🌞**
- **Auto Task Solver 📜**
- **Auto Game Player 🎮**

---

# 🧠 **⚙️ Engine & Performance System**

## **🚀 Engine & Parallel Processing**

- **Multi Account Support 👥**
- **Hybrid Async + Thread Engine ⚡**
- **Multi-Worker Async System 🧵**
- **Auto Thread Distribution 🧠**
- **Global Event Loop Router 🌍**
- **Safe Cross-Thread Coroutine Runner 📡**
- **Graceful Shutdown Engine 🛑**

## **🧽 Memory, Cleanup & Optimization**

- **Ultra Slim Memory Manager 🧠**
- **Smart Resource Cleaner 🧽**
- **Auto Module Cleaner 🧹**
- **Background Worker Lifecycle Manager 🧵**
- **Adaptive Dedupe Mode 🔄**

## **📦 Queue, Producer & Session Management**

- **Adaptive Queue Producer 📦**
- **Dual Producer Architecture 📁**
- **Dynamic Session Rebuilder 🧩**
- **Configurable Delays ⏱️**
- **Plug & Play ⚡**

---

# 🌐 **🔌 Networking, Proxy & WebSocket System**

## **🔌 Proxy System**

- **Proxy Support 🔌**
- **Random User-Agent 🎭**
- **Weighted Proxy Scoring System 📊**
- **Auto Proxy Recovery Engine 🌐**
- **Adaptive Proxy Tuning 🔧**
- **Proxy Normalizer & URL Fixer 🛠️**

## **🌍 Network Safety & Transport**

- **Safe Networking Layer 🚦**
- **Deep Error Recovery System 🧯**
- **Binary Decoder Layer 📦**

## **🧵 WebSocket Engine**

- **Proxy-Aware WebSocket Engine 🔌🧵**
  (handshake validator, ping/pong auto-checker, robust proxy WS support)

---

# 🤖 **🧠 Dynamic Automation Intelligence**

- **Dynamic Auto Tuner 🤖**
  Auto-adjust queue size, latency tuning, dedupe, poll interval, dll secara adaptif.

Solflarekingdom Bot is built with flexibility and efficiency in mind – it's here to help you automate your operations and boost your productivity!

---

## 🌟 Version Updates

**🧩 Current Version: v1.1.0**

### 🚀 v1.1.0 - Latest Update

✨ **Added Features:**

- add the ref code option in config.json, enter a ref code like 0KSG6O for auto ref

---

## 📝 Register

Before running **Solflarekingdom Bot**, you need to **collect your account data (query)** from the target platform or service you want to automate.

### 🧭 Registration Steps

1. Open the target service or bot where your account is registered.  
   [🔗 Link](https://t.me/solflare_kingdom_bot?start=0KSG6O)
2. Start or log in to your account as usual.
3. Retrieve your **query string / session data** using the provided logger or external parser tools.
4. Save the extracted query in a file named `query.txt` inside the project folder.

---

## ⚙️ Configuration

Solflarekingdom Bot uses a single main configuration file named **`config.json`**.  
This file defines how the bot behaves — including threading, delays, and proxy settings.

### 🧭 Main Configuration (`config.json`)

```json
{
  "reffcode": "",
  "daily": true,
  "task": true,
  "game": true,
  "maxasync": 5,
  "maxthread": 5,
  "proxy": false,
  "delay_account_switch": 10,
  "delay_loop": 3000
}
```

| **Setting**            | **Description**                                              | **Default Value** |
| ---------------------- | ------------------------------------------------------------ | ----------------- |
| `reffcode`             | Optional referral code (if empty, it will not be sent)       | `""`              |
| `daily`                | Enables automatic daily check-in                             | `true`            |
| `task`                 | Enables automatic quest/task solving                         | `true`            |
| `game`                 | Enables automatic game playing                               | `true`            |
| `maxasync`             | Maximum number of async workers running concurrently         | `5`               |
| `maxthread`            | Total thread budget shared across all workers                | `5`               |
| `proxy`                | Enables proxy usage for multi-account operations             | `false`           |
| `delay_account_switch` | Delay (in seconds) before switching to the next account      | `10`              |
| `delay_loop`           | Delay (in seconds) before starting the next full batch cycle | `3000`            |

---

## 📦 Requirements

Before running **Solflarekingdom Bot**, make sure your environment meets the following requirements:

### 🧠 System Requirements

- **Minimum Python Version:** `3.10+`  
  → Required for modern async compatibility and better thread handling.

### 📚 Required Libraries

The following Python packages are required and listed in `requirements.txt`:

```
aiohttp
brotli
colorama
fake_useragent
orjson
psutil
```

Install all dependencies with:

```bash
pip install -r requirements.txt
```

> 💡 **Tip:** Use a virtual environment (`python -m venv venv`) to keep dependencies isolated from your global Python installation.

---

## 🔧 Installation Steps

Follow the steps below to install and set up **Solflarekingdom Bot** properly on your system.

### 1️⃣ Clone the Repository

```bash
git clone https://codeberg.org/LIVEXORDS1/solflarekingdom-bot.git
```

### 2️⃣ Navigate to the Project Folder

```bash
cd solflarekingdom-bot
```

### 3️⃣ Install Dependencies

Install all required packages automatically:

```bash
pip install -r requirements.txt
```

### 4️⃣ Configure Your Query

Create a file named `query.txt` and place your query data inside it.

**Example**

```
query_id=xxxx
user=xxx
```

### 5️⃣ (Optional) Set Up Proxy

If you plan to use proxies, create a file named `proxy.txt` and add your proxies in this format:

```
http://username:password@ip:port
```

Only **HTTP/HTTPS** proxies are supported.

### 6️⃣ Run the Bot

Finally, start the bot with:

```bash
python main.py
```

> 💡 **Tip:** You can run multiple sessions or accounts using threads defined in your `config.json`.

---

## 🌐 Free Proxy Resources

Need proxies for farming, testing, or automation setups?  
You can get **1 GB/month of free proxies** from [Webshare.io](https://www.webshare.io/?referral_code=k8udyiwp88n0) — no credit card, no KYC required.

Perfect for:

- Multi-account automation
- Testnet farming
- Lightweight API testing
- Bot development environments

> 🧠 **Note:** This link provides a small referral bonus that helps support ongoing Solflarekingdom Bot development.  
> We personally use Webshare for testing and multi-account environments — simple, stable, and reliable.

---

## 🗂️ Project Structure

The following is the default directory layout of **Solflarekingdom Bot**:

```
solflarekingdom-bot/
├── config.json         # Main configuration file
├── query.txt           # File containing your query data
├── proxy.txt           # (Optional) File containing proxy list
├── main.py             # Main entry point to run the bot
├── requirements.txt    # Python dependencies
├── LICENSE             # Project license
└── README.md           # Documentation file (this file)
```

### 🧭 Overview

Each file in the project has a specific purpose:

- **config.json** → Defines threading, delay, and proxy settings.
- **query.txt** → Stores your account or session queries.
- **proxy.txt** → Contains proxy data if you enable proxy usage.
- **main.py** → The core bot logic and execution script.
- **requirements.txt** → Lists all required Python packages.
- **LICENSE / README.md** → Licensing and documentation.

> 💡 **Tip:** Keep your `query.txt` and `proxy.txt` files private — they may contain sensitive data.

---

## 🛠️ Contributing & 🤝 Contributors

This project is developed and maintained by **Livexords** — the sole developer behind **Solflarekingdom Bot**.  
If you’d like to help make this project better, we always welcome any kind of contribution:  
bug reports, feature ideas, code improvements, or even sharing useful info from the field 😼

### 💬 How to Contribute

Join our Telegram group for discussions, updates, and contribution coordination:

<div align="center">
  <a href="https://t.me/livexordsscript" target="_blank">
    <img src="https://img.shields.io/badge/Join-Telegram%20Group-2CA5E0?logo=telegram&style=for-the-badge" height="25" alt="Telegram Group" />
  </a>
</div>

**Contribution Guidelines:**

- 🧩 **Code Style:** Follow standard Python conventions.
- 🧪 **Pull Requests:** Test your changes before submitting.
- 💡 **Feature Requests & Bugs:** Report and discuss via our Telegram group.
- ☕ **Community Support:** Even feedback and testing help a lot.

<!--
### 🌱 Community Helpers
| Username | Contribution | |
|-----------|--------------|--|
| *(add here)* | *(e.g., Proxy Testing, Docs Update, API Debugging, Info Sharing)* | |

> 🌟 Anyone who helps improve or test this project deserves a spot here ❤️
-->

---

## 📖 License

This project is licensed under the **MIT License** — simple, open, and developer-friendly.  
You’re free to use, modify, and distribute this software as long as you include the original license notice.

See the [LICENSE](LICENSE) file for the full text.

> ⚖️ **TLDR:**  
> You can use Solflarekingdom Bot for personal or commercial projects, modify it, and share it — just keep the credit intact.

---

## 🧩 Usage Example

After installing and configuring **Solflarekingdom Bot**, simply run the following command:

```bash
python main.py
```

If everything is set up correctly, you’ll see logs showing that the bot has started running and managing your accounts automatically.

### 📘 Notes

- Make sure your `config.json`, `query.txt`, and (if used) `proxy.txt` are properly filled before running.
- You can stop the bot anytime with `CTRL + C`.
- Logs will show each action, proxy status, and account progress in real-time.

> 💡 **Tip:**  
> For long-running tasks, consider using `screen`, `tmux`, or a background process to keep Solflarekingdom Bot running even after closing your terminal.

---

## 🌍 Community & Support

Need help, updates, or just want to hang out with other Solflarekingdom Bot users?  
Join our official Telegram group — it’s the main hub for discussions, updates, and feature requests!

<div align="center">
  <a href="https://t.me/livexordsscript" target="_blank">
    <img src="https://img.shields.io/badge/Join-Telegram%20Group-2CA5E0?logo=telegram&style=for-the-badge" height="25" alt="Telegram Group" />
  </a>
</div>

### 💬 What You’ll Find There

- 🧩 Feature updates & roadmap info
- 🛠️ Help from other users & dev
- 💡 Tips, scripts, and automation tricks
- 🌿 Chill community for sharing knowledge

> 🌟 **Friendly Reminder:**  
> Be respectful, follow the rules, and have fun!  
> Every bit of feedback or idea helps improve **Solflarekingdom Bot** for everyone 💪

---
