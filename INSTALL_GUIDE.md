# DaemonIQ — Installation Guide

## Requirements

- Linux (Debian/Ubuntu fully supported; other distros can diagnose but not auto-apply fixes)
- Python 3.8 or newer
- [Ollama](https://ollama.com) — installed automatically during setup if not present

**A GPU is not required.** DaemonIQ runs entirely on your CPU. If you do have a GPU, Ollama will use it automatically to speed things up — but if you don't, everything works the same, just a little slower.

Check your Python version:

```bash
python3 --version
```

If it is below 3.8 or missing entirely, see [Installing Python](#installing-python).

---

## Installing

### Option A — Single command

```bash
curl -fsSL https://raw.githubusercontent.com/JayRaj21/DaemonIQ/master/install.sh | bash
```

The script checks for Python, downloads the DaemonIQ files, creates the `daemoniq` command in `~/.local/bin`, and adds it to your PATH. The only prompt it asks is whether you want the demon to start automatically at login.

When it finishes, **open a new terminal** before running `daemoniq`. This is necessary for the PATH change to take effect.

### Option B — Manual download

Download `install.sh`, `daemoniq-imp.py`, and `daemoniq-sovereign.py` into the same directory, then run:

```bash
bash install.sh
```

The installer looks for the script files in the same directory, so no internet connection is needed.

---

## First launch

Running `daemoniq` for the first time starts a short setup wizard. It asks two questions.

**Question 1 — which model tier?**

```
1) Imp      Runs on most machines with 4GB+ RAM.
             Uses Llama 3 via Ollama (~4GB download).

2) Demon   Best local quality. Needs 9GB+ RAM.
             Uses Qwen2.5 via Ollama.
```

If you are unsure, choose Imp. It works on most machines and the quality is good enough for the majority of troubleshooting tasks. You can switch later with `daemoniq setup`.

**Question 2 — RAM size (Demon only)**

Qwen2.5 comes in several sizes. The wizard maps your RAM to the right one:

| Your RAM | Model used | Download size |
|----------|-----------|---------------|
| 8–12 GB  | qwen2.5:7b  | ~5 GB |
| 12–24 GB | qwen2.5:14b | ~9 GB (recommended) |
| 24 GB+   | qwen2.5:32b | ~20 GB |
| Not sure | qwen2.5:7b  | ~5 GB |

**You do not need a GPU for any of these.** Ollama runs on CPU by default. If your machine has a compatible GPU (NVIDIA, AMD, or Apple Silicon), Ollama will detect and use it automatically for faster responses. If not, the model runs on CPU — responses will be a bit slower, but the quality is identical.

If you are unsure whether your machine can handle Sovereign, choose Imp — it works well on almost any modern laptop or desktop.

---

## Ollama

Both Imp and Sovereign use Ollama to run the AI model locally on your machine. If Ollama is not installed, the setup wizard will offer to install it for you. To install it manually:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

To pull a model manually instead of through the wizard:

```bash
ollama pull llama3          # Imp
ollama pull qwen2.5:14b     # Sovereign — adjust tag to match your RAM
```

Ollama resumes interrupted downloads, so if a large model download fails partway through, simply run the pull command again.

---

## Changing your setup

To switch between Imp and Sovereign, change your distro selection, or swap models:

```bash
daemoniq setup
```

---

## Installing Python

**Debian / Ubuntu / Mint / Pop!\_OS**
```bash
sudo apt update && sudo apt install python3
```

**Fedora**
```bash
sudo dnf install python3
```

**Arch / Manjaro**
```bash
sudo pacman -S python
```

After installing, close and reopen your terminal before running the installer again.

---

## Troubleshooting

**`command not found: daemoniq` after a successful install**

The PATH change written by the installer only takes effect in new terminals. Open a new terminal window, or reload your config manually:

```bash
source ~/.bashrc    # bash
source ~/.zshrc     # zsh
```

**`daemoniq` starts but immediately exits with a Python error**

Check the demon log:

```bash
daemoniq logs
```

**Ollama is not running**

```bash
ollama serve
```

To start it automatically on login:

```bash
systemctl --user enable --now ollama
```

**Slow or interrupted model download**

Run the pull command again — Ollama resumes from where it stopped:

```bash
ollama pull llama3
ollama pull qwen2.5:14b
```

**Something else**

```bash
daemoniq logs
```

The log file at `/tmp/daemoniq-demon.log` records everything the demon does and is usually the fastest way to diagnose unexpected behaviour.

---

## Uninstalling

```bash
daemoniq uninstall
```

This stops the demon, removes all installed files, deletes the `daemoniq` command, disables the systemd service if one was created, and removes the PATH entry from your shell config. Open a new terminal afterwards to confirm the command is gone.

---

## File locations

All files are installed to your home directory. Nothing is written system-wide.

| Path | Contents |
|------|---------|
| `~/.daemoniq-demon/` | Scripts, config, backups, hardware snapshot |
| `~/.daemoniq-demon/config.json` | Your setup choices |
| `~/.daemoniq-demon/hardware_snapshot.json` | Hardware scan from last demon start |
| `~/.daemoniq-demon/backups/` | Pre-patch backups (up to 5 per variant) |
| `~/.local/bin/daemoniq` | The shell command |
| `/tmp/daemoniq-demon.log` | Demon log (cleared on reboot) |
| `/tmp/daemoniq-demon.sock` | Unix socket (cleared on reboot) |
