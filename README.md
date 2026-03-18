# DaemonIQ

**A Linux troubleshooting assistant that lives in your terminal.**

Paste an error message. Get a diagnosis, a fix, and optionally have it apply the fix for you.

---

## Install

Open a terminal and run this:

```bash
curl -fsSL https://raw.githubusercontent.com/JayRaj21/DaemonIQ/main/install.sh | bash
```

Then open a **new terminal** and type:

```bash
daemoniq
```

The setup wizard will walk you through the rest.

> **Don't have `curl`?** See the [Installation Guide](INSTALL_GUIDE.md) for alternatives.

---

## What it does

```
you@daemoniq:~$ sudo apt upgrade gives "dpkg was interrupted, you must manually run..."
```
```
⚠ Diagnosis: dpkg was interrupted mid-install, leaving the package database in a broken state.

→ Fix: Run dpkg --configure -a to finish any interrupted installs, then retry.

  $ sudo dpkg --configure -a
  $ sudo apt upgrade

Type "run the fix" to apply this, or "exec on" to always apply fixes automatically.
```

**Other things you can ask:**
- `"why does pip install keep failing?"`
- `"analyze my command history for problems"`
- `"my Wi-Fi driver disappeared after a kernel update"`
- `"give me tips to improve my Linux workflow"`
- `"run the fix"` — applies the last suggested fix automatically

---

## What it knows about your system

DaemonIQ scans your machine at startup and carries that context into every conversation.
You never have to tell it what GPU you have or which kernel you're running.

**It automatically detects:**
- Your Linux distro and available package managers
- GPU, network, and audio hardware
- Loaded kernel modules and DKMS module status
- Recent kernel errors from `dmesg`
- Recommended drivers (via `ubuntu-drivers` if available)
- Your shell command history

**It has built-in knowledge of:**
- Package managers — `apt`, `dpkg`, `pip`, `snap`, `flatpak`
- GPU drivers — NVIDIA (with DKMS), AMD, Intel
- Wi-Fi drivers — Broadcom, Realtek, Intel, Atheros firmware
- Audio — ALSA, PulseAudio, PipeWire, SOF firmware
- Kernel modules — `modprobe`, blacklisting, DKMS workflows
- Secure Boot — MOK enrollment for third-party drivers
- Firmware updates — `fwupdmgr`, `firmware-linux-nonfree`

---

## Command reference

### Starting DaemonIQ

| Command | What it does |
|---------|-------------|
| `daemoniq` | Open the interactive assistant (REPL) |
| `daemoniq "your question"` | Ask a single question and get an answer, then exit |
| `daemoniq --exec "your question"` | Ask a question and automatically apply the suggested fix |
| `daemoniq --session work "question"` | Ask a question in a named session (keeps separate history) |
| `daemoniq --no-color` | Disable coloured output (useful when piping or logging) |

---

### Inside the interactive assistant (REPL)

Once you're inside the assistant, you can type questions naturally or use these built-in commands:

| Command | What it does |
|---------|-------------|
| `help` | Show available REPL commands |
| `exec on` | Automatically run fixes when the assistant suggests them |
| `exec off` | Show suggested fixes without running them (default) |
| `history` | Show the last 20 shell commands that were imported |
| `clear` | Clear the current conversation so the assistant starts fresh |
| `status` | Show whether the daemon is running and which backend is active |
| `distro` | Show the detected distro and available package managers |
| `exit` or `quit` | Leave the assistant (the background daemon keeps running) |

---

### Managing the daemon

DaemonIQ runs a small background process that handles conversations and keeps history between sessions.

| Command | What it does |
|---------|-------------|
| `daemoniq start` | Start the background daemon manually |
| `daemoniq stop` | Stop the background daemon |
| `daemoniq restart` | Stop and restart the daemon |
| `daemoniq status` | Show the daemon's PID, distro, active backend, and hardware summary |
| `daemoniq logs` | Stream the daemon log in real time (`tail -f`) |

---

### Configuration and information

| Command | What it does |
|---------|-------------|
| `daemoniq setup` | Re-run the setup wizard — change your distro, backend, or model |
| `daemoniq distro` | Show your detected Linux distro and available package managers |
| `daemoniq hardware` | Show detected hardware, loaded drivers, and kernel errors |
| `daemoniq history` | Print the last 50 shell commands the daemon has on record |
| `daemoniq sessions` | List all active named sessions |
| `daemoniq version` | Show the installed version and last update time |
| `daemoniq update` | Check for and install the latest update |
| `daemoniq rollback` | Restore the previous version if an update causes problems |
| `daemoniq uninstall` | Completely remove DaemonIQ from your machine |

---

### Sessions

Sessions let you keep separate conversation histories — useful if you're working on multiple things at once.

```bash
daemoniq --session work "pip install is broken"
daemoniq --session homelab "how do I open port 8080?"
daemoniq sessions   # see all active sessions
```

Each session remembers the full conversation so the assistant has context from earlier in that session. The default session is called `default`.

---

### Quick reference card

```
daemoniq                          Open the assistant
daemoniq "question"               One-shot question
daemoniq --exec "question"        Ask + auto-apply fix
daemoniq --session NAME "q"       Use a named session

daemoniq setup                    Change backend / distro / model
daemoniq start / stop / restart   Manage the background daemon
daemoniq status                   Health check
daemoniq logs                     Watch the daemon log
daemoniq distro                   Show distro info
daemoniq hardware                 Show hardware & driver snapshot
daemoniq history                  Show recorded shell history
daemoniq sessions                 List active sessions
daemoniq version                  Show installed version
daemoniq update                   Check for and install updates
daemoniq rollback                 Restore the previous version
daemoniq uninstall                Remove DaemonIQ from this machine

Inside the assistant:
  exec on / off                   Toggle auto-apply
  clear                           Reset conversation
  history                         Show shell history
  status / distro                 System info
  exit                            Leave (daemon keeps running)
```

---

## Need help installing?

See **[INSTALL_GUIDE.md](INSTALL_GUIDE.md)** for step-by-step instructions, including:
- What to do if the one-line install doesn't work
- How to install Python if it's missing
- What each setup option (Cloud / Light / Heavy) means
- How to uninstall

---

> **Note:** "DaemonIQ" is a working name. To rename the product, edit the `BRANDING`
> block at the top of any variant script — all paths, prompts, and display strings
> update automatically.
