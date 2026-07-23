# 🎵 Apex All-in-One Telegram Bot

> **Ultra-fast Music + Admin + Anti-spam + AI Chat + Games — Ek bot mein sab kuch!**
> Stack: Python 3.12 · Pyrofork · PyTgCalls 2.3.3 · heroku-26 · Standard-2X

---

## 🚀 One-Click Deploy

| Platform | Button |
|----------|--------|
| **Heroku** (Recommended) | [![Deploy on Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/thomasir/4st_music&branch=main) |
| **Railway** | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/thomasir/4st_music) |

> ⚠️ **Repo must be PUBLIC on GitHub** for the deploy button to work!
> Settings → (scroll down) → Danger Zone → Change visibility → Make public

---

## ✏️ Edit Code Online

| Action | Link |
|--------|------|
| 📝 **Edit on GitHub** | [github.com/thomasir/4st_music/edit/main](https://github.com/thomasir/4st_music/edit/main) |
| 🖥️ **GitHub Codespaces** | [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/thomasir/4st_music) |
| ⚡ **Gitpod** | [![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/thomasir/4st_music) |

---

## 🍪 Cookies Setup (YouTube ke liye)

```
cookies/
├── README.txt   ← Full guide yahan hai
└── youtube.txt  ← YAHAN rakho (ye file GitHub par NAHI jaayegi)
```

### Local (VPS/PC):
1. Chrome → youtube.com login karo
2. Extension: **"Get cookies.txt LOCALLY"** (Chrome Web Store)
3. youtube.com → Export → naam badlo `youtube.txt` → `cookies/` folder mein daalo

### Heroku par (optional):
1. `youtube.txt` Notepad mein kholo → Ctrl+A → Ctrl+C
2. Heroku → **Settings** → **Config Vars**
3. `YOUTUBE_COOKIES` = paste → Add

> ✅ `cookies/*.txt` .gitignore mein hai — GitHub par kabhi nahi jaayega. Normal public
> videos ke liye cookies zaroori nahi hain; age-restricted videos ke liye valid,
> fresh cookies use karo.

---

## ✨ Features

| Category | Commands |
|----------|----------|
| 🎵 Music | `/play` `/vplay` `/pause` `/resume` `/skip` `/stop` `/vol` `/queue` `/np` |
| 👮 Admin | `/ban` `/unban` `/kick` `/mute` `/unmute` `/warn` `/clearwarn` `/promote` `/demote` `/pin` |
| 👋 Welcome | Custom welcome/goodbye · `{mention}` `{name}` `{chat}` |
| 🛡️ Anti-Spam | Flood control · Anti-raid auto-lock |
| 🚫 Filter | `/addfilter` `/rmfilter` `/filters` |
| 📝 Notes | `#notename` · `/savenote` `/delnote` `/notes` |
| 📢 Broadcast | `/broadcast` (owner only) |
| 🎮 Games | `/truth` `/dare` `/wyr` `/trivia` |
| 🔨 GBan | `/gban` `/ungban` `/gbans` |
| 📊 Stats | `/stats` `/topusers` |
| 🔧 Utility | `/translate` `/shorten` `/paste` `/weather` `/id` `/ping` |
| 🤖 AI Chat | `/ai` · Reply to bot |
| 😂 Fun | `/joke` `/shayari` `/quote` `/meme` `/flip` `/dice` `/8ball` |

---

## 🔑 Config Vars (Heroku)

| Variable | Required | Default |
|----------|----------|------------|
| `API_ID` | ✅ | — |
| `API_HASH` | ✅ | — |
| `BOT_TOKEN` | ✅ | — |
| `SESSION_STRING` | ✅ | — |
| `OWNER_ID` | ✅ | — |
| `OWNER_USERNAME` | ⚪ | — |
| `LOG_CHANNEL` | ⚪ | — |
| `YOUTUBE_COOKIES` | ⚪ | — |
| `VOLUME_BOOST` | ⚪ | `10.0` |

> ⚠️ API credentials must only exist in deployment config vars. The old public
> defaults have been removed. If those credentials were ever used, rotate the
> Telegram API hash and bot token before deploying this version.

---

## 📱 SESSION_STRING kaise banao

**Apne PC par run karo:**

```bash
pip install pyrofork
python3 SESSION_STRING_HELPER.py
```

> ⚠️ **DOOSRA Telegram account use karo** — main account nahi. Yeh VC mein join hone wala assistant hai.

---

## 🛠 Group Setup

1. Bot ko **Admin** banao: Delete Messages + Ban Users + Manage Voice Chats + Invite Users
2. **Voice Chat start karo**: Group Settings → Voice Chats → Start
3. **Log Channel** mein bot ko admin banao

---

## 🏗 Tech Stack

| Component | Version |
|-----------|---------|
| Python | 3.12.10 |
| Pyrofork | 2.3.69 |
| TgCrypto | 1.2.5 |
| PyTgCalls | 2.3.3 |
| yt-dlp | latest |
| Heroku Stack | heroku-26 |
| Heroku Dyno | Standard-2X |

---

## 👑 Owner & Support

- **Owner**: [@TheY_CaIl_mE_OG](https://t.me/TheY_CaIl_mE_OG)
- **Support**: [Apex Association](https://t.me/ApexAssociation)
- **Repo**: [github.com/thomasir/4st_music](https://github.com/thomasir/4st_music)

> ⚠️ Educational purposes only. Follow Telegram ToS & YouTube ToS.
