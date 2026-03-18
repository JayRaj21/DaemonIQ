# DaemonIQ — Installation Guide

This guide walks through installing DaemonIQ step by step. If something goes wrong,
there is a section at the bottom for common problems.

---

## Before you start

DaemonIQ needs **Python 3.8 or newer**. Most Linux systems already have this.
To check, open a terminal and run:

```bash
python3 --version
```

If you see `Python 3.8` or higher, you're good. If you get "command not found"
or a version below 3.8, see [Installing Python](#installing-python) below.

---

## Option A — One command (recommended)

Open a terminal and paste this:

```bash
curl -fsSL https://raw.githubusercontent.com/JayRaj21/DaemonIQ/master/install.sh | bash
```

The installer will:
1. Check that Python is installed
2. Download the DaemonIQ scripts
3. Create a `daemoniq` command you can run from anywhere
4. Add it to your PATH so the terminal can find it
5. Optionally set it up to start automatically when you log in

When it finishes, open a **new terminal** (this is important — it reloads your PATH)
and type `daemoniq` to start.

---

## Option B — Download the files manually

Use this if the one-line install doesn't work, or if you prefer not to pipe scripts
directly to bash.

**Step 1:** Download these four files into the same folder:
- `install.sh`
- `daemoniq-cloud.py`
- `daemoniq-heavy.py`
- `daemoniq-light.py`

**Step 2:** Open a terminal in that folder and run:

```bash
bash install.sh
```

---

## First run — the setup wizard

The first time you run `daemoniq`, it will ask you two questions:

### Question 1: How much do you want to run on your own machine?

```
  1) Cloud    — Nothing runs locally. Uses the Groq API (free).
  2) Light    — Runs on your machine. Works on most computers.
  3) Heavy    — Runs on your machine. Best local quality.
```

**Not sure which to pick?**

| | Cloud | Light | Heavy |
|---|---|---|---|
| Needs internet? | Yes (to answer questions) | Only to download once | Only to download once |
| Needs an account? | Yes (free, at groq.com) | No | No |
| Needs a powerful computer? | No | No (4GB+ RAM) | Yes (9GB+ RAM) |
| Quality? | Best | Good | Very good |
| Speed? | Very fast | Depends on your hardware | Slower on older hardware |

→ **If you're unsure, pick Cloud (1).** It's the easiest, it's free, and it works on any computer.

---

### Question 2 (Cloud only): Your Groq API key

Groq is the service that runs the AI model. It's free to use.

1. Go to **https://console.groq.com**
2. Click "Sign Up" — it takes about a minute and doesn't need a credit card
3. Once logged in, click **API Keys** in the left menu
4. Click **Create API Key**, give it any name, and copy it
5. Paste it into the setup wizard when asked

Your key looks like: `gsk_abc123...`

The key is saved to your shell config so you only need to do this once.

---

### Question 2 (Heavy only): How much RAM does your machine have?

Qwen2.5 comes in different sizes. Bigger = better quality but needs more RAM.
Pick the one that matches your machine:

| Choice | RAM needed | Download size |
|--------|-----------|---------------|
| 8–12 GB | 8 GB | ~5 GB |
| 12–24 GB | 12 GB | ~9 GB ← recommended |
| 24 GB+ | 24 GB | ~20 GB |
| Not sure | — | ~5 GB (safe default) |

---

## Changing your setup later

You can always switch between Cloud, Light, and Heavy by running:

```bash
daemoniq setup
```

---

## Installing Python

If `python3 --version` says "command not found":

**Ubuntu / Debian / Mint / Pop!_OS:**
```bash
sudo apt update && sudo apt install python3
```

**Fedora:**
```bash
sudo dnf install python3
```

**Arch / Manjaro:**
```bash
sudo pacman -S python
```

After installing, close and reopen your terminal, then run the DaemonIQ installer again.

---

## Light and Heavy: installing Ollama

The Light and Heavy options use **Ollama** to run AI models on your machine.
The setup wizard will offer to install it for you automatically.

If you prefer to install it yourself first:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

After installing, you can pull a model manually if you want:

```bash
ollama pull llama3        # for Light
ollama pull qwen2.5:14b   # for Heavy (recommended size)
```

Or just let the DaemonIQ setup wizard do it for you.

---

## Troubleshooting

**"command not found: daemoniq" after installing**

The terminal needs to reload your PATH. Either:
- Open a new terminal window, or
- Run `source ~/.bashrc` (or `source ~/.zshrc` if you use zsh)

---

**"Python not found" even though I just installed it**

Close your terminal completely and open a new one, then try again.

---

**The Groq key isn't working**

- Make sure you copied the full key including the `gsk_` prefix
- Check your key is still valid at https://console.groq.com/keys
- Re-run `daemoniq setup` to enter it again

---

**Ollama model download is very slow or fails**

Large models can be several GB. If the download fails partway through, just run it again:
```bash
ollama pull llama3         # Light
ollama pull qwen2.5:14b    # Heavy
```
Ollama resumes interrupted downloads automatically.

---

**"Ollama is not running"**

Start it manually:
```bash
ollama serve
```

Or set it to start automatically:
```bash
systemctl --user enable --now ollama
```

---

**Something else went wrong**

Check the DaemonIQ log for clues:
```bash
daemoniq logs
```

---

## Uninstalling

Run this single command:

```bash
daemoniq uninstall
```

It will ask for confirmation, then remove everything — the daemon, all scripts,
the `daemoniq` command, the auto-start service if installed, and the PATH entry
from your shell config. Open a new terminal afterwards and it will be fully gone.

---

## What gets installed where

| Location | What it is |
|----------|-----------|
| `~/.daemoniq-daemon/` | All DaemonIQ scripts and config |
| `~/.daemoniq-daemon/config.json` | Your setup choices (backend, model) |
| `~/.local/bin/daemoniq` | The command you type |
| `/tmp/daemoniq-daemon.sock` | Internal socket (deleted on reboot) |
| `/tmp/daemoniq-daemon.log` | Log file (deleted on reboot) |

Nothing is installed system-wide. Everything stays in your home directory.
