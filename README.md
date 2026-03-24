# DaemonIQ

A Linux troubleshooting assistant that runs as a background process on your machine. Describe a problem in plain English — it diagnoses it, suggests a fix, and can apply the fix if you ask it to.

No cloud API. No account required. Runs entirely on your hardware using a local AI model via [Ollama](https://ollama.com).

---

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/JayRaj21/DaemonIQ/master/install.sh | bash
```

Open a new terminal when it finishes, then run `daemoniq`. A short setup wizard runs on first launch to choose between Imp (lighter, 4GB+ RAM) and Sovereign (best quality, 9GB+ RAM).

No `curl`? See [INSTALL_GUIDE.md](INSTALL_GUIDE.md).

---

## Usage

Start an interactive session:

```bash
daemoniq
```

Ask a single question without opening a session:

```bash
daemoniq "why does sudo apt upgrade keep failing?"
```

Ask a question and have the fix applied automatically:

```bash
daemoniq --exec "fix the dpkg lock error"
```

### Example session

```
you@daemoniq:~$ apt gives "dpkg was interrupted, you must manually run dpkg --configure -a"

⚠ Diagnosis: a previous package operation was interrupted before it could finish,
  leaving dpkg in an inconsistent state.

→ Fix:
  $ sudo dpkg --configure -a
  $ sudo apt install -f

Type "run the fix" to apply this now, or "exec on" to apply fixes automatically going forward.
```

---

## System context

At startup, DaemonIQ scans your machine and carries that information into every conversation. You do not need to describe your setup — it already knows your distro, kernel, loaded drivers, GPU, network hardware, and recent kernel errors from `dmesg`.

Built-in knowledge covers `apt`, `dpkg`, `pip`, `snap`, and `flatpak`; NVIDIA, AMD, and Intel GPU drivers; Wi-Fi firmware for Broadcom, Realtek, Intel, and Atheros chipsets; ALSA, PulseAudio, and PipeWire audio; DKMS workflows; Secure Boot and MOK enrollment; and firmware updates via `fwupdmgr`.

---

## Commands

### Starting DaemonIQ

| Command | Description |
|---------|-------------|
| `daemoniq` | Start an interactive session |
| `daemoniq "question"` | Ask a single question and exit |
| `daemoniq --exec "question"` | Ask and automatically apply the fix |
| `daemoniq --no-color` | Disable colour output |

### Inside a session

| Command | Description |
|---------|-------------|
| `exec on` | Apply fixes automatically when suggested |
| `exec off` | Show fixes without applying them (default) |
| `sandbox on` | [dev] Test fixes in Docker before applying |
| `sandbox off` | Disable sandbox mode |
| `clear` | Wipe the conversation history and start fresh |
| `history` | Show your last 20 recorded shell commands |
| `info` | Show status, distro, model, and package managers |
| `hardware` | Show detected hardware, drivers, and kernel errors |
| `help` | Show the help menu |
| `close` | Close this session (program keeps running in background) |
| `stop` | Shut down the program completely |

> `close` also accepts `quit` and `q`. `stop` also accepts `end`.

### Managing the background process

| Command | Description |
|---------|-------------|
| `daemoniq start` | Start the background process |
| `daemoniq stop` | Stop the background process |
| `daemoniq restart` | Stop and restart the background process |
| `daemoniq logs` | Stream the live log output |

### Configuration and information

| Command | Description |
|---------|-------------|
| `daemoniq info` | Show status, distro, model, and package managers |
| `daemoniq hardware` | Show hardware snapshot — GPU, drivers, dmesg errors |
| `daemoniq history` | Show the last 50 recorded shell commands |
| `daemoniq setup` | Re-run the setup wizard |

### Updates and maintenance

| Command | Description |
|---------|-------------|
| `daemoniq version` | Show the installed version |
| `daemoniq update` | Show instructions for applying a patch |
| `daemoniq update /path/to/patch.py` | Apply a downloaded patch file |
| `daemoniq rollback` | Restore the previous version |
| `daemoniq uninstall` | Remove DaemonIQ from this machine |

---

## Quick reference

```
daemoniq                     Start a session
daemoniq "question"          Ask a single question
daemoniq --exec "question"   Ask and auto-apply the fix

daemoniq start               Start the background process
daemoniq stop                Stop the background process
daemoniq restart             Restart the background process
daemoniq logs                View live logs
daemoniq info                Show status and system info
daemoniq hardware            Show hardware and driver info
daemoniq history             Show recorded shell commands
daemoniq setup               Re-run setup wizard
daemoniq version             Show installed version
daemoniq update              Apply a patch
daemoniq rollback            Restore previous version
daemoniq uninstall           Remove DaemonIQ

Inside a session:
  exec on / off      Apply or show fixes
  sandbox on / off   [dev] Test fixes in Docker before applying
  clear              Wipe conversation history
  history            Show shell command history
  info               Show status and system info
  hardware           Show hardware and driver info
  help               Show the help menu
  close              Close this session
  stop               Shut down completely
```

---

## Notes

- Requires Python 3.8+ and [Ollama](https://ollama.com)
- A GPU is not required — DaemonIQ runs on CPU. If a GPU is present, Ollama will use it automatically.
- Nothing is installed system-wide — all files live under `~/.daemoniq-demon/`
- Full installation instructions: [INSTALL_GUIDE.md](INSTALL_GUIDE.md)
