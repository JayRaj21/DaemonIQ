# DaemonIQ

A Linux troubleshooting assistant that runs as a background demon on your machine. Describe a problem in plain English — it diagnoses it, suggests a fix, and can apply the fix if you ask it to. It runs as a background demon, always ready.

No cloud API. No account required. Runs entirely on your hardware using a local AI model via [Ollama](https://ollama.com).

---

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/JayRaj21/DaemonIQ/master/install.sh | bash
```

Open a new terminal when it finishes, then run `daemoniq`. A short setup wizard runs on first launch to choose between Imp (lighter, 4GB+ RAM) and Demon (best quality, 9GB+ RAM).

No `curl`? See [INSTALL_GUIDE.md](INSTALL_GUIDE.md).

---

## How To Use It

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

### Interactive session

| Command | Description |
|---------|-------------|
| `daemoniq` | Start an interactive session |
| `daemoniq "question"` | One-shot question, no session |
| `daemoniq --exec "question"` | Ask and automatically apply the fix |
| `daemoniq --session NAME "question"` | Ask within a named session |
| `daemoniq --no-color` | Disable colour output |

### Inside a session

| Command | Description |
|---------|-------------|
| `exec on` | Apply fixes automatically when suggested |
| `exec off` | Show fixes without applying them (default) |
| `clear` | Clear conversation history for this session |
| `history` | Show the last 20 recorded shell commands |
| `status` | Show demon status and active backend |
| `distro` | Show detected distro and package managers |
| `help` | List available commands |
| `exit` | End the session (demon continues running) |

### Demon management

| Command | Description |
|---------|-------------|
| `daemoniq start` | Start the demon |
| `daemoniq stop` | Stop the demon |
| `daemoniq restart` | Restart the demon |
| `daemoniq status` | Show PID, distro, backend, and hardware summary |
| `daemoniq logs` | Stream the demon log (`tail -f`) |

### Configuration

| Command | Description |
|---------|-------------|
| `daemoniq setup` | Re-run the setup wizard |
| `daemoniq distro` | Show detected distro and package managers |
| `daemoniq hardware` | Show hardware snapshot — GPU, drivers, dmesg errors |
| `daemoniq history` | Show the last 50 recorded shell commands |
| `daemoniq sessions` | List active named sessions |

### Updates and maintenance

| Command | Description |
|---------|-------------|
| `daemoniq version` | Show the installed version |
| `daemoniq update` | Show instructions for applying a patch |
| `daemoniq update /path/to/patch.py` | Apply a downloaded patch file |
| `daemoniq rollback` | Restore the previous version |
| `daemoniq uninstall` | Remove DaemonIQ from this machine |

### Sessions

Sessions maintain separate conversation histories, which is useful when working across different machines or projects at once:

```bash
daemoniq --session server "nginx won't start after the last upgrade"
daemoniq --session laptop "bluetooth keeps disconnecting"
daemoniq sessions
```

The default session is named `default`.

---

## Quick reference

```
daemoniq                           Start a session
daemoniq "question"                One-shot question
daemoniq --exec "question"         Ask and apply fix
daemoniq --session NAME "q"        Named session

daemoniq setup                     Re-run setup
daemoniq start / stop / restart    Demon control
daemoniq status / logs             Demon info
daemoniq distro / hardware         System info
daemoniq history / sessions        History and sessions
daemoniq version / update          Version and patching
daemoniq rollback / uninstall      Recovery and removal

In a session:
  exec on / off    Toggle auto-apply
  clear            Reset conversation
  exit             End session
```

---

## Notes

- Requires Python 3.8+ and [Ollama](https://ollama.com)
- Nothing is installed system-wide — all files live under `~/.daemoniq-demon/`
- "DaemonIQ" is a working name. To rename it, edit the `BRANDING` block at the top of any variant script
- Full installation instructions: [INSTALL_GUIDE.md](INSTALL_GUIDE.md)
