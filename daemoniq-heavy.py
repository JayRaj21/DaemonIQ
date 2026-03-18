#!/usr/bin/env python3
"""
DaemonIQ — Linux Troubleshooting Assistant (Qwen2.5 / Ollama edition)
Single-file edition: daemon + CLI + distro detection all in one.
Uses Qwen2.5 via Ollama — best open-source model for technical/code tasks,
no API key or internet required after initial model download.

Usage:
  daemoniq                        Interactive REPL (auto-starts daemon)
  daemoniq "apt gives lock error" One-shot question
  daemoniq --exec "fix broken pkg" Ask and auto-apply fix
  daemoniq start | stop | restart | status | logs | distro | history

Requires: Python 3.8+, Ollama running locally (https://ollama.com).
No API key needed. Recommended: 16GB+ RAM for 14B, 32GB+ for 32B.
"""

# ══════════════════════════════════════════════════════════════════════════════
# BRANDING — change these when the product is renamed, nothing else needs to
# ══════════════════════════════════════════════════════════════════════════════

PRODUCT_NAME    = "DaemonIQ"
PRODUCT_TAGLINE = "Linux Troubleshooting Assistant"
PRODUCT_VERSION = "0.2.1"
CLI_COMMAND     = "daemoniq"
DAEMON_LABEL    = "daemoniq-daemon"
AI_PERSONA      = PRODUCT_NAME

ASCII_BANNER_LINES = [
    r" ____                               ___ ___  ",
    r"|  _ \  __ _  ___ _ __ ___   ___  |_ _/ _ \ ",
    r"| | | |/ _` |/ _ \ '_ ` _ \ / _ \  | | | | |",
    r"| |_| | (_| |  __/ | | | | | (_) | | | |_| |",
    r"|____/ \__,_|\___|_| |_| |_|\___/ |___\__\_\\",
]

# ── Runtime paths (all derived from DAEMON_LABEL) ────────────────────────────
import os as _os
SOCKET_PATH  = f"/tmp/{DAEMON_LABEL}.sock"
PID_FILE     = f"/tmp/{DAEMON_LABEL}.pid"
LOG_FILE     = f"/tmp/{DAEMON_LABEL}.log"
HISTORY_FILE = _os.path.expanduser(f"~/.{DAEMON_LABEL}_history")
INSTALL_DIR  = _os.path.expanduser(f"~/.{DAEMON_LABEL}")

# ══════════════════════════════════════════════════════════════════════════════
# STDLIB IMPORTS
# ══════════════════════════════════════════════════════════════════════════════

import os
import sys
import json
import socket
import signal
import logging
import threading
import subprocess
import shutil
import time
import re
import argparse
from dataclasses import dataclass
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# DISTRO DETECTION
# Extend _FAMILIES at the bottom of this section to add new distro support.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DistroInfo:
    family:       str
    distro_id:    str
    distro_name:  str
    version_id:   str
    codename:     str
    pkg_managers: list
    supported:    bool
    support_note: str

@dataclass
class ExecBlock:
    commands:      list
    description:   str
    requires_sudo: bool = False
    pkg_manager:   str  = ""


class DistroFamily:
    name       = "unknown"
    FAMILY_IDS: set = set()

    def detect(self, ids: set) -> bool:
        return bool(ids & self.FAMILY_IDS)

    def get_info(self, raw: dict) -> DistroInfo:
        raise NotImplementedError

    def build_system_prompt_section(self, info: DistroInfo) -> str:
        raise NotImplementedError

    def sanitize_exec_block(self, block: ExecBlock, info: DistroInfo) -> ExecBlock:
        return block


# ── Debian/Ubuntu/Mint/Pop!_OS/Kali/etc. ─────────────────────────────────────

_DEBIAN_IDS = {
    "debian",
    "ubuntu", "ubuntu-server", "kubuntu", "xubuntu", "lubuntu",
    "ubuntu-mate", "ubuntu-budgie", "ubuntu-studio",
    "pop", "elementary", "zorin", "neon",
    "linuxmint", "mint", "lmde",
    "kali", "kali-linux", "parrot", "parrotos",
    "raspbian", "raspios",
    "deepin", "mx", "antix", "devuan", "pureos",
    "tails", "whonix", "armbian", "proxmox",
}

_DEBIAN_ERROR_PATTERNS = [
    ("dpkg was interrupted",        "interrupted dpkg — database is in a broken state"),
    ("lock.*frontend",              "apt/dpkg lock held by another process"),
    ("lock.*dpkg",                  "dpkg lock held by another process"),
    ("Unable to acquire.*lock",     "package manager lock conflict"),
    ("E: Could not get lock",       "package manager lock conflict"),
    ("Sub-process.*dpkg.*returned", "dpkg post-install script failure"),
    ("held broken packages",        "dependency conflict — held broken packages"),
    ("unmet dependencies",          "unresolved dependency tree"),
    ("404.*Not Found",              "repository URL is stale or unreachable"),
    ("NO_PUBKEY",                   "missing GPG signing key for a repository"),
    ("GPG error",                   "repository GPG verification failure"),
    ("Hash Sum mismatch",           "corrupted or out-of-date package cache"),
    ("no installation candidate",   "package name not found in any enabled repo"),
    ("dpkg: error processing",      "package installation/removal script error"),
    ("pip.*externally-managed",     "pip blocked by PEP 668 (use venv or --break-system-packages)"),
    ("ModuleNotFoundError",         "Python module missing — may need pip install"),
    ("EXTERNALLY-MANAGED",          "pip blocked by PEP 668 (use venv or pipx)"),
    ("snap.*error",                 "snap package manager error"),
    ("Permission denied",           "insufficient file permissions or missing sudo"),
    ("command not found",           "binary not installed or not in PATH"),
    ("Segmentation fault",          "program crashed (segfault) — possible corrupt binary or library"),
    ("error while loading shared",  "missing or incompatible shared library (.so)"),
    ("SIGABRT",                     "program aborted — likely an assertion failure or libc error"),
]

class DebianFamily(DistroFamily):
    name       = "debian"
    FAMILY_IDS = _DEBIAN_IDS

    _PM_CHECKS = [
        ("apt",     "/usr/bin/apt"),
        ("apt-get", "/usr/bin/apt-get"),
        ("dpkg",    "/usr/bin/dpkg"),
        ("snap",    "/usr/bin/snap"),
        ("flatpak", "/usr/bin/flatpak"),
        ("pip",     None),
        ("pip3",    None),
        ("pipx",    None),
        ("npm",     None),
        ("cargo",   None),
    ]

    def detect(self, ids: set) -> bool:
        return bool(ids & self.FAMILY_IDS) or \
               Path("/usr/bin/dpkg").exists() or \
               Path("/var/lib/dpkg").exists()

    def get_info(self, raw: dict) -> DistroInfo:
        pkg_managers = []
        for name, path in self._PM_CHECKS:
            if (path and Path(path).exists()) or (not path and shutil.which(name)):
                pkg_managers.append(name)
        return DistroInfo(
            family       = "debian",
            distro_id    = raw.get("ID", "debian").lower(),
            distro_name  = raw.get("PRETTY_NAME", raw.get("NAME", "Debian-based Linux")),
            version_id   = raw.get("VERSION_ID", "").strip('"'),
            codename     = (raw.get("VERSION_CODENAME") or raw.get("UBUNTU_CODENAME") or
                            raw.get("DEBIAN_CODENAME") or "").lower(),
            pkg_managers = pkg_managers,
            supported    = True,
            support_note = "",
        )

    def build_system_prompt_section(self, info: DistroInfo) -> str:
        pm_list = ", ".join(info.pkg_managers) or "apt, dpkg"
        err_lines = "\n".join(f"  - `{p}` → {c}" for p, c in _DEBIAN_ERROR_PATTERNS)
        return f"""## System Context
- Distro:   {info.distro_name}
- Family:   Debian / APT-based
- Codename: {info.codename or "unknown"}
- Package managers: {pm_list}

## Debian/Ubuntu expertise

### APT & DPKG
- `apt` vs `apt-get` vs `aptitude` — when to use each
- `dpkg -i`, `dpkg --configure -a`, `dpkg --audit`
- Sources list: `/etc/apt/sources.list` and `/etc/apt/sources.list.d/`
- PPAs: `add-apt-repository`, signing keys, `signed-by` (apt-key deprecated)
- APT pinning: `/etc/apt/preferences.d/`
- Cache: `apt clean`, `apt autoclean`, `apt autoremove`
- Held packages: `apt-mark hold/unhold`, `dpkg --get-selections`
- Lock files: `/var/lib/dpkg/lock-frontend`, `/var/cache/apt/archives/lock`

### Known error patterns
{err_lines}

### Python packaging
- PEP 668 / EXTERNALLY-MANAGED → use `python3 -m venv`, `pipx`, or `--break-system-packages`
- Prefer `python3-<pkg>` apt packages for system tools; pip inside venvs for dev

### Snap & Flatpak
- Snap: `snap install/remove/refresh/list/logs`
- Flatpak: `flatpak install/uninstall/update`, `flatpak remote-list`

### Shared libraries
- `ldd`, `ldconfig -p | grep <lib>`, `apt-file search <missing.so>`

### Driver management on Debian/Ubuntu
You have deep knowledge of the full Linux driver stack:

#### Kernel modules
- `lsmod` — list loaded modules, `modinfo <module>` — module details
- `modprobe <module>` — load a module, `modprobe -r <module>` — unload
- `modprobe -v <module>` — verbose load (shows dependencies)
- `/etc/modprobe.d/` — persistent module config, blacklisting
- `dmesg | grep -i <device>` — find device errors in kernel log
- `journalctl -k` — kernel log via systemd

#### DKMS (Dynamic Kernel Module Support)
- `dkms status` — list all DKMS modules and their build status
- `dkms install <module>/<version>` — build and install a module
- `dkms remove <module>/<version> --all` — remove a DKMS module
- `apt install linux-headers-$(uname -r)` — install matching kernel headers (required for DKMS)
- Common DKMS packages: `nvidia-dkms-*`, `virtualbox-dkms`, `zfs-dkms`, `broadcom-sta-dkms`

#### GPU drivers
- NVIDIA: `ubuntu-drivers list`, `ubuntu-drivers autoinstall`, `apt install nvidia-driver-<ver>`
  - Check: `nvidia-smi`, `lspci | grep -i nvidia`
  - Issues: check `/var/log/Xorg.0.log`, `dmesg | grep nvidia`
  - Secure Boot conflict: needs MOK enrollment via `mokutil`
- AMD: drivers are in-kernel (amdgpu), firmware in `firmware-amd-graphics` / `amdgpu-dkms`
  - Check: `lspci | grep -i amd`, `dmesg | grep amdgpu`
- Intel: in-kernel (i915), firmware in `intel-microcode`, `firmware-misc-nonfree`
  - Check: `lspci | grep -i intel`, `dmesg | grep i915`

#### Wi-Fi and network drivers
- `lspci -nnk | grep -A3 -i network` — identify NIC and current driver
- `lsusb` — find USB network adapters
- Common problematic chipsets and their packages:
  - Broadcom: `broadcom-sta-dkms` or `firmware-brcm80211`
  - Realtek: `firmware-realtek` or `r8168-dkms`
  - Intel Wi-Fi: `firmware-iwlwifi`
  - Atheros: `firmware-atheros`
- `rfkill list` — check if Wi-Fi is software/hardware blocked
- `rfkill unblock wifi` — unblock software-blocked Wi-Fi
- `iw dev`, `iwconfig` — Wi-Fi interface status

#### Audio drivers
- ALSA: `aplay -l` (list devices), `alsamixer` (levels), `alsactl restore`
- PulseAudio: `pactl info`, `pulseaudio --kill && pulseaudio --start`
- PipeWire: `pw-cli info`, `systemctl --user status pipewire`
- Firmware: `firmware-sof-signed` for Intel Sound Open Firmware
- Check: `dmesg | grep -i snd`, `lspci | grep -i audio`

#### Printer drivers
- CUPS: `lpstat -a`, `lpstat -p -d`, `cupsctl`
- `apt install cups printer-driver-*`
- GUI: `system-config-printer`

#### Firmware (non-module drivers)
- `apt install firmware-linux-nonfree firmware-linux-free` — broad firmware package
- `fwupdmgr get-updates && fwupdmgr update` — firmware updates via LVFS
- `dmesg | grep -i firmware` — find firmware load failures

#### Secure Boot and driver signing
- `mokutil --sb-state` — check if Secure Boot is enabled
- `mokutil --list-enrolled` — list enrolled signing keys
- Third-party drivers (NVIDIA, VirtualBox) need MOK key enrollment when Secure Boot is on
- `update-secureboot-policy --enroll-key` (Ubuntu) — automated MOK enrollment

#### Safe execution rules for driver commands
When emitting DAEMONIQ_EXEC blocks for driver operations:
- Always install `linux-headers-$(uname -r)` before DKMS operations
- Use `--no-install-recommends` sparingly — driver packages often need recommends
- Never unload a module for the active GPU or network interface without warning
- Prefer `ubuntu-drivers autoinstall` over manual driver selection on Ubuntu
- After kernel module changes, always suggest a reboot

### UX recommendations (when asked)
Suggest: nala, unattended-upgrades, needrestart, debsums, btop, ncdu, tldr,
`alias update='sudo apt update && sudo apt upgrade'`
"""

    def sanitize_exec_block(self, block: ExecBlock, info: DistroInfo) -> ExecBlock:
        BLOCKED = ["rm -rf /", "rm -rf /*", "mkfs", "dd if=", "> /dev/sda", "shred /dev"]
        safe = []
        for cmd in block.commands:
            s = cmd.strip()
            for danger in BLOCKED:
                if danger in s:
                    raise ValueError(
                        f"Blocked dangerous command: `{s}`\n"
                        f"{PRODUCT_NAME} will not execute commands that could destroy system data."
                    )
            # Inject DEBIAN_FRONTEND=noninteractive for apt commands
            if ("apt-get" in s or s.lstrip("sudo ").startswith("apt ")) and \
               "DEBIAN_FRONTEND" not in s and \
               any(k in s for k in ("install", "upgrade", "dist-upgrade", "remove", "purge")):
                s = f"DEBIAN_FRONTEND=noninteractive {s}"
            # Inject -y for unattended apt runs
            if any(k in s for k in ("install", "upgrade", "remove", "purge")) and \
               ("apt" in s) and " -y" not in s and "--yes" not in s:
                s += " -y"
            safe.append(s)
        return ExecBlock(
            commands      = safe,
            description   = block.description,
            requires_sudo = block.requires_sudo,
            pkg_manager   = block.pkg_manager or ("apt" if "apt" in info.pkg_managers else ""),
        )


# ── Future family stubs ───────────────────────────────────────────────────────
# To add a new distro: copy one of these stubs, populate FAMILY_IDS and the
# three methods, then add an instance to _FAMILIES below.

def _coming_soon_info(raw, family_id, name, pm_names, note):
    return DistroInfo(
        family=family_id, distro_id=raw.get("ID", family_id).lower(),
        distro_name=raw.get("PRETTY_NAME", name), version_id=raw.get("VERSION_ID", ""),
        codename="", pkg_managers=[p for p in pm_names if shutil.which(p)],
        supported=False, support_note=note,
    )

def _coming_soon_exec(block, info):
    raise ValueError(f"Automatic fix execution is not yet supported on {info.distro_name}.")

class RedHatFamily(DistroFamily):
    name = "redhat"
    FAMILY_IDS = {"rhel", "centos", "fedora", "rocky", "almalinux", "ol", "scientific", "amzn"}
    def get_info(self, raw):
        return _coming_soon_info(raw, "redhat", "RHEL-based Linux", ["dnf","yum","rpm"],
            "RHEL/Fedora/CentOS support is coming soon. General Linux help is still available.")
    def build_system_prompt_section(self, info):
        return f"## System Context\n- Distro: {info.distro_name}\n- Family: RHEL/RPM (coming soon)\n"
    def sanitize_exec_block(self, block, info): _coming_soon_exec(block, info)

class ArchFamily(DistroFamily):
    name = "arch"
    FAMILY_IDS = {"arch", "manjaro", "endeavouros", "artix", "garuda", "cachyos"}
    def get_info(self, raw):
        return _coming_soon_info(raw, "arch", "Arch-based Linux", ["pacman","yay","paru"],
            "Arch Linux support is coming soon. General Linux help is still available.")
    def build_system_prompt_section(self, info):
        return f"## System Context\n- Distro: {info.distro_name}\n- Family: Arch/Pacman (coming soon)\n"
    def sanitize_exec_block(self, block, info): _coming_soon_exec(block, info)

class SUSEFamily(DistroFamily):
    name = "suse"
    FAMILY_IDS = {"opensuse", "opensuse-leap", "opensuse-tumbleweed", "sles", "sled"}
    def get_info(self, raw):
        return _coming_soon_info(raw, "suse", "SUSE-based Linux", ["zypper","rpm"],
            "openSUSE/SLES support is coming soon. General Linux help is still available.")
    def build_system_prompt_section(self, info):
        return f"## System Context\n- Distro: {info.distro_name}\n- Family: SUSE/Zypper (coming soon)\n"
    def sanitize_exec_block(self, block, info): _coming_soon_exec(block, info)

class AlpineFamily(DistroFamily):
    name = "alpine"
    FAMILY_IDS = {"alpine"}
    def get_info(self, raw):
        return _coming_soon_info(raw, "alpine", "Alpine Linux", ["apk"],
            "Alpine Linux support is coming soon. General Linux help is still available.")
    def build_system_prompt_section(self, info):
        return f"## System Context\n- Distro: {info.distro_name}\n- Family: Alpine/APK (coming soon)\n"
    def sanitize_exec_block(self, block, info): _coming_soon_exec(block, info)


# ── Registry (add new family instances here) ──────────────────────────────────
_FAMILIES = [DebianFamily(), RedHatFamily(), ArchFamily(), SUSEFamily(), AlpineFamily()]


def _parse_os_release() -> dict:
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        if Path(path).exists():
            result = {}
            for line in Path(path).read_text(errors="replace").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip().strip('"')
            return result
    return {}


def detect_distro():
    raw     = _parse_os_release()
    all_ids = {raw.get("ID", "").lower()} | set(raw.get("ID_LIKE", "").lower().split())
    for family in _FAMILIES:
        if family.detect(all_ids):
            return family.get_info(raw), family
    # Unknown distro fallback
    info = DistroInfo(
        family="unknown", distro_id=raw.get("ID","unknown").lower(),
        distro_name=raw.get("PRETTY_NAME","Unknown Linux"),
        version_id=raw.get("VERSION_ID",""), codename="",
        pkg_managers=[], supported=False,
        support_note=(
            f"Your Linux distribution is not yet fully supported by {PRODUCT_NAME}. "
            "General troubleshooting help is still available, but "
            "automatic fix execution is disabled."
        ),
    )
    stub = DistroFamily()
    stub.build_system_prompt_section = lambda i: f"## System Context\n- Distro: {i.distro_name} (unsupported)\n"
    stub.sanitize_exec_block = lambda b, i: (_ for _ in ()).throw(
        ValueError("Automatic fix execution is not supported on this distribution.")
    )
    return info, stub


# ══════════════════════════════════════════════════════════════════════════════
# DAEMON — background server (Unix socket, session state, Ollama + Qwen2.5)
# ══════════════════════════════════════════════════════════════════════════════

MAX_HISTORY  = 500

# ── Qwen2.5 / Ollama configuration ────────────────────────────────────────────
# Pull your chosen size with: ollama pull qwen2.5:<tag>
#
# Size guide — pick the largest that fits your RAM:
#   qwen2.5:3b    ~2GB   RAM  — minimum viable, fast on CPU
#   qwen2.5:7b    ~5GB   RAM  — good quality, runs on most machines
#   qwen2.5:14b   ~9GB   RAM  — recommended: strong technical reasoning
#   qwen2.5:32b   ~20GB  RAM  — near-GPT4 quality, needs 24GB+ RAM
#   qwen2.5:72b   ~45GB  RAM  — best quality, needs 48GB+ RAM or GPU
#
# Qwen2.5 is particularly strong at:
#   - Code understanding and shell command diagnosis
#   - Technical error analysis
#   - Following structured output formats (DAEMONIQ_EXEC blocks)
OLLAMA_HOST  = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:14b"   # change tag to match your hardware (see above)

# Extended context window — Qwen2.5 supports up to 32k tokens
OLLAMA_CTX   = 8192   # increase to 16384 or 32768 if you have spare RAM

_DISTRO_INFO   = None
_DISTRO_FAMILY = None

BASE_PROMPT = f"""You are {AI_PERSONA} — an expert Linux system troubleshooting assistant \
running as a background daemon on the user's machine.

Your capabilities:
1. Diagnose problems with installing, upgrading, removing, and running programs.
2. Suggest clear, actionable fixes with explanations.
3. When asked to "apply", "run", or "execute" a fix, output a DAEMONIQ_EXEC block \
so the daemon can run it safely on the user's system.
4. Analyze shell command history for patterns, errors, or inefficiencies.
5. Recommend UX and workflow improvements when asked.

## Response format
Use plain text with markdown code blocks for commands.
When you want to EXECUTE commands, include exactly one JSON block:

<DAEMONIQ_EXEC>
{{"commands": ["cmd1", "cmd2"], "description": "Brief description", "requires_sudo": false}}
</DAEMONIQ_EXEC>

Rules:
- Only emit DAEMONIQ_EXEC when the user explicitly asks to apply/run/execute a fix.
- Run commands sequentially; stop on first non-zero exit.
- Never include interactive commands (nano, vim, less, etc.).
- Prefer idempotent commands. Explain what each command does before the block.
- Lead with diagnosis, then the fix. Be concise but thorough.
- Use: ✓ success  ✗ error  ⚠ warning  → step
- Always produce well-structured responses. Use the DAEMONIQ_EXEC block format exactly as specified when executing fixes.
"""


# ══ HARDWARE & DRIVER CONTEXT ════════════════════════════════════════════════
# Scans the system for hardware and driver state at daemon startup.
# Results are cached in hardware_snapshot.json and injected into every
# AI request so the model always knows what is in the machine.
# ═════════════════════════════════════════════════════════════════════════════

HARDWARE_SNAPSHOT_FILE = os.path.join(INSTALL_DIR, "hardware_snapshot.json")

# Commands that are safe to run for read-only hardware discovery
_HW_COMMANDS = {
    "pci_devices":     ["lspci", "-vmm"],
    "usb_devices":     ["lsusb"],
    "loaded_modules":  ["lsmod"],
    "kernel_version":  ["uname", "-r"],
    "kernel_cmdline":  ["cat", "/proc/cmdline"],
    "dmesg_errors":    ["dmesg", "--level=err,warn", "--notime"],
    "gpu_info":        ["lspci", "-nnk", "-d", "::0300"],  # VGA/3D controllers
    "network_hw":      ["lspci", "-nnk", "-d", "::0200"],  # Network controllers
    "audio_hw":        ["lspci", "-nnk", "-d", "::0401"],  # Audio devices
    "block_devices":   ["lsblk", "-o", "NAME,MODEL,TRAN,SIZE"],
    "cpu_info":        ["grep", "-m4", "model name\|cpu MHz\|siblings\|cpu cores", "/proc/cpuinfo"],
    "memory_info":     ["grep", "MemTotal\|MemAvailable", "/proc/meminfo"],
    "firmware_info":   ["dmesg", "-t", "-l", "err"],
}

# Optional commands — only run if the tool exists
_HW_OPTIONAL = {
    "ubuntu_drivers":      ["ubuntu-drivers", "list"],
    "nvidia_smi":          ["nvidia-smi", "-q", "-d", "NAME,DRIVER_VERSION,UTILIZATION"],
    "amd_gpu":             ["cat", "/sys/class/drm/card0/device/vendor"],
    "rfkill":              ["rfkill", "list"],
    "bluetooth":           ["bluetoothctl", "show"],
    "printer_drivers":     ["lpstat", "-a"],
    "dkms_status":         ["dkms", "status"],
    "kernel_modules_avail":["apt-cache", "search", "--names-only", "linux-modules"],
}


def _run_cmd(args: list, timeout: int = 8) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        r = subprocess.run(
            args, capture_output=True, text=True,
            timeout=timeout, errors="replace"
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _scan_hardware() -> dict:
    """
    Collect hardware and driver state. Returns a dict that is both saved
    to hardware_snapshot.json and injected into the system prompt.
    """
    snapshot = {"scanned_at": __import__("datetime").datetime.now().isoformat()}

    # Required commands
    for key, cmd in _HW_COMMANDS.items():
        result = _run_cmd(cmd)
        if result:
            snapshot[key] = result

    # Optional commands — skip silently if tool not present
    for key, cmd in _HW_OPTIONAL.items():
        if shutil.which(cmd[0]):
            result = _run_cmd(cmd)
            if result:
                snapshot[key] = result

    # Derive a plain-English hardware summary for the prompt
    summary_lines = []

    if "kernel_version" in snapshot:
        summary_lines.append(f"Kernel: {snapshot['kernel_version']}")

    # GPU detection
    gpu_raw = snapshot.get("gpu_info", "")
    if "nvidia" in gpu_raw.lower():
        summary_lines.append("GPU: NVIDIA detected")
    elif "amd" in gpu_raw.lower() or "radeon" in gpu_raw.lower():
        summary_lines.append("GPU: AMD/Radeon detected")
    elif "intel" in gpu_raw.lower():
        summary_lines.append("GPU: Intel integrated graphics detected")

    # Wi-Fi / network
    net_raw = snapshot.get("network_hw", "")
    if net_raw:
        for line in net_raw.splitlines():
            if line.strip():
                summary_lines.append(f"Network HW: {line.strip()}")
                break

    # DKMS
    if "dkms_status" in snapshot:
        summary_lines.append(f"DKMS modules: {snapshot['dkms_status']}")

    # ubuntu-drivers
    if "ubuntu_drivers" in snapshot:
        summary_lines.append(f"Recommended drivers (ubuntu-drivers): {snapshot['ubuntu_drivers']}")

    # nvidia-smi
    if "nvidia_smi" in snapshot:
        for line in snapshot["nvidia_smi"].splitlines():
            if "Driver Version" in line:
                summary_lines.append(f"NVIDIA driver: {line.strip()}")
                break

    snapshot["summary"] = "\n".join(summary_lines)

    # Save to disk
    try:
        json.dump(snapshot, open(HARDWARE_SNAPSHOT_FILE, "w"), indent=2)
        log.info(f"Hardware snapshot saved ({len(snapshot)} fields)")
    except Exception as e:
        log.warning(f"Could not save hardware snapshot: {e}")

    return snapshot


# Global hardware snapshot — populated at daemon startup
_HW_SNAPSHOT: dict = {}

def _build_system_prompt(shell_history: list) -> str:
    parts = [BASE_PROMPT]

    # Inject user-declared distro from setup config (highest priority context)
    try:
        cfg = json.load(open(CONFIG_FILE))
        distro_label = cfg.get("distro_label", "")
        distro_key   = cfg.get("distro_key", "")
        if distro_label and distro_label != "Other / Not listed":
            parts.append(
                f"## User's Linux Distribution\n"
                f"The user is running **{distro_label}** (id: {distro_key}). "
                f"Tailor all advice, package manager commands, and file paths to this distro."
            )
    except Exception:
        pass

    if _DISTRO_INFO and _DISTRO_FAMILY:
        parts.append(_DISTRO_FAMILY.build_system_prompt_section(_DISTRO_INFO))
        if not _DISTRO_INFO.supported:
            parts.append(
                f"\n⚠ SUPPORT NOTE: {_DISTRO_INFO.support_note}\n"
                "Do NOT emit DAEMONIQ_EXEC blocks for this distribution."
            )

    # Inject hardware snapshot if available
    if _HW_SNAPSHOT:
        hw_parts = ["## Hardware & Driver Context"]
        if _HW_SNAPSHOT.get("summary"):
            hw_parts.append(_HW_SNAPSHOT["summary"])
        if _HW_SNAPSHOT.get("dmesg_errors"):
            # Only include last 20 lines of dmesg errors to keep prompt size sane
            dmesg_tail = "\n".join(_HW_SNAPSHOT["dmesg_errors"].splitlines()[-20:])
            hw_parts.append(f"\nRecent kernel errors/warnings (dmesg):\n```\n{dmesg_tail}\n```")
        if _HW_SNAPSHOT.get("loaded_modules"):
            # First 30 lines of lsmod is enough for context
            lsmod_head = "\n".join(_HW_SNAPSHOT["loaded_modules"].splitlines()[:30])
            hw_parts.append(f"\nLoaded kernel modules (lsmod, first 30):\n```\n{lsmod_head}\n```")
        if _HW_SNAPSHOT.get("dkms_status"):
            hw_parts.append(f"\nDKMS module status:\n```\n{_HW_SNAPSHOT['dkms_status']}\n```")
        if _HW_SNAPSHOT.get("ubuntu_drivers"):
            hw_parts.append(f"\nRecommended drivers (ubuntu-drivers list):\n```\n{_HW_SNAPSHOT['ubuntu_drivers']}\n```")
        parts.append("\n".join(hw_parts))

    if shell_history:
        recent = shell_history[-50:]
        parts.append(
            f"\n## User's recent shell history ({len(recent)} commands)\n"
            "```bash\n" + "\n".join(recent) + "\n```"
        )
    return "\n\n".join(parts)


# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(DAEMON_LABEL)


# ── Session state ─────────────────────────────────────────────────────────────
class _SessionState:
    def __init__(self):
        self._lock         = threading.Lock()
        self.conversations = {}
        self.shell_history = []
        self._load_history()

    def _load_history(self):
        if Path(HISTORY_FILE).exists():
            try:
                lines = [l.strip() for l in open(HISTORY_FILE) if l.strip()]
                self.shell_history = lines
                log.info(f"Loaded {len(lines)} history entries")
            except Exception as e:
                log.warning(f"Could not load history: {e}")

    def add_history(self, commands: list):
        with self._lock:
            self.shell_history.extend(commands)
            self.shell_history = self.shell_history[-MAX_HISTORY:]
            try:
                open(HISTORY_FILE, "w").write("\n".join(self.shell_history) + "\n")
            except Exception as e:
                log.warning(f"Could not save history: {e}")

    def get_messages(self, sid: str) -> list:
        with self._lock:
            return self.conversations.setdefault(sid, []).copy()

    def add_message(self, sid: str, role: str, content: str):
        with self._lock:
            msgs = self.conversations.setdefault(sid, [])
            msgs.append({"role": role, "content": content})
            if len(msgs) > 40:
                self.conversations[sid] = msgs[-40:]

    def clear_session(self, sid: str):
        with self._lock:
            self.conversations.pop(sid, None)

    def list_sessions(self) -> list:
        with self._lock:
            return list(self.conversations.keys())


_state = _SessionState()


# ── Ollama API ────────────────────────────────────────────────────────────────
def _check_ollama() -> tuple[bool, str]:
    """Return (available, message). Checks Ollama is running and model is pulled."""
    import urllib.request, urllib.error
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        models = [m["name"].split(":")[0] for m in data.get("models", [])]
        # Qwen2.5 tags look like "qwen2.5:14b" — match on prefix too
        base = OLLAMA_MODEL.split(":")[0]
        matched = any(
            m == OLLAMA_MODEL or m == base or m.startswith(base + ":")
            for m in models + [m["name"] for m in data.get("models", [])]
        )
        if not matched:
            return False, (
                f"Model '{OLLAMA_MODEL}' is not pulled yet.\n"
                f"  Run: ollama pull {OLLAMA_MODEL}\n"
                f"  Or choose a smaller size: ollama pull qwen2.5:7b\n"
                f"  Available models: {', '.join(models) or 'none'}"
            )
        return True, "ok"
    except urllib.error.URLError:
        return False, (
            f"Ollama is not running. Start it with: ollama serve\n"
            f"  Install Ollama: https://ollama.com/download"
        )
    except Exception as e:
        return False, f"Could not reach Ollama: {e}"

def _call_api(sid: str, message: str, api_key: str = "") -> str:
    """Call Qwen2.5 via Ollama. api_key is unused but kept for interface compatibility."""
    import urllib.request
    try:
        _state.add_message(sid, "user", message)

        messages = [{"role": "system", "content": _build_system_prompt(_state.shell_history)}]
        messages += _state.get_messages(sid)

        payload = json.dumps({
            "model":    OLLAMA_MODEL,
            "messages": messages,
            "stream":   False,
            "options":  {
                "num_predict": 1024,
                "temperature": 0.15,    # Qwen2.5 benefits from slightly lower temp
                "top_p":       0.9,     # nucleus sampling for more coherent output
                "num_ctx":     OLLAMA_CTX,  # extended context window
                "repeat_penalty": 1.1,  # reduce repetition in long responses
            },
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        # Qwen2.5 larger models can be slower — generous timeout
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())

        reply = data.get("message", {}).get("content", "")
        if not reply:
            reply = "✗ Empty response from Ollama."
        _state.add_message(sid, "assistant", reply)
        return reply
    except Exception as e:
        log.error(f"Qwen2.5/Ollama error: {e}")
        return f"✗ Ollama error: {e}"


# ── Command executor ───────────────────────────────────────────────────────────
def _execute(block: ExecBlock) -> str:
    lines = [f"⚡ Executing: {block.description}", "─" * 50]
    for cmd in block.commands:
        lines.append(f"$ {cmd}")
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=120,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
            )
            if r.stdout.strip(): lines.append(r.stdout.strip())
            if r.stderr.strip(): lines.append(f"[stderr] {r.stderr.strip()}")
            lines.append(f"→ exit code: {r.returncode} {'✓' if r.returncode == 0 else '✗'}")
            _state.add_history([cmd])
            if r.returncode != 0:
                lines.append("⚠ Non-zero exit — stopping.")
                break
        except subprocess.TimeoutExpired:
            lines.append("✗ Timed out after 120s"); break
        except Exception as e:
            lines.append(f"✗ Error: {e}"); break
        lines.append("")
    return "\n".join(lines)


_EXEC_RE = re.compile(r"<DAEMONIQ_EXEC>\s*(.*?)\s*</DAEMONIQ_EXEC>", re.DOTALL)

def _parse_exec(response: str, auto_exec: bool):
    m = _EXEC_RE.search(response)
    if not m:
        return response, None
    clean = _EXEC_RE.sub("", response).strip()
    if not auto_exec:
        clean += (
            f"\n\n⚠ Fix commands ready. Use `exec on` in the REPL or `--exec` flag to apply, "
            f"or type `run the fix`."
        )
        return clean, None
    if _DISTRO_INFO and not _DISTRO_INFO.supported:
        return clean, f"✗ Auto-execution not supported on {_DISTRO_INFO.distro_name} yet."
    try:
        raw = json.loads(m.group(1))
        block = ExecBlock(
            commands=raw.get("commands", []),
            description=raw.get("description", ""),
            requires_sudo=raw.get("requires_sudo", False),
        )
    except json.JSONDecodeError as e:
        return clean, f"✗ Could not parse exec block: {e}"
    try:
        block = _DISTRO_FAMILY.sanitize_exec_block(block, _DISTRO_INFO)
    except ValueError as e:
        return clean, f"✗ Execution blocked: {e}"
    return clean, _execute(block)


# ── Socket protocol ───────────────────────────────────────────────────────────
_END = b"\n##END##\n"

def _recv(conn):
    data = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk: break
        data += chunk
        if data.endswith(_END):
            return json.loads(data[:-len(_END)].decode())
    return json.loads(data.decode())

def _send(conn, obj):
    conn.sendall(json.dumps(obj).encode() + _END)


# ── Client handler ────────────────────────────────────────────────────────────
def _handle_client(conn):
    try:
        req = _recv(conn)
        cmd = req.get("cmd", "chat")
        sid = req.get("session", "default")
        key = req.get("api_key", "")

        if cmd == "ping":
            _send(conn, {"status": "ok", "pid": os.getpid()})

        elif cmd == "chat":
            ok, msg = _check_ollama()
            if not ok:
                _send(conn, {"error": msg}); return
            log.info(f"[{sid}] {req.get('message','')[:80]}")
            raw_reply = _call_api(sid, req.get("message", ""))
            clean, exec_out = _parse_exec(raw_reply, req.get("auto_exec", False))
            _send(conn, {"reply": clean, "exec_output": exec_out, "session": sid})

        elif cmd == "history_import":
            cmds = req.get("commands", [])
            _state.add_history(cmds)
            _send(conn, {"status": f"Imported {len(cmds)} commands"})

        elif cmd == "history_get":
            _send(conn, {"history": _state.shell_history[-100:]})

        elif cmd == "session_clear":
            _state.clear_session(sid)
            _send(conn, {"status": f"Session '{sid}' cleared"})

        elif cmd == "sessions_list":
            _send(conn, {"sessions": _state.list_sessions()})

        elif cmd == "distro_info":
            if _DISTRO_INFO:
                _send(conn, {
                    "family": _DISTRO_INFO.family, "distro_id": _DISTRO_INFO.distro_id,
                    "distro_name": _DISTRO_INFO.distro_name, "version_id": _DISTRO_INFO.version_id,
                    "codename": _DISTRO_INFO.codename, "pkg_managers": _DISTRO_INFO.pkg_managers,
                    "supported": _DISTRO_INFO.supported, "support_note": _DISTRO_INFO.support_note,
                })
            else:
                _send(conn, {"error": "Distro not yet detected"})

        elif cmd == "status":
            _send(conn, {
                "pid": os.getpid(), "sessions": len(_state.list_sessions()),
                "history_entries": len(_state.shell_history), "log": LOG_FILE,
                "distro": _DISTRO_INFO.distro_name if _DISTRO_INFO else "unknown",
                "supported": _DISTRO_INFO.supported if _DISTRO_INFO else False,
                "ai_backend": f"Ollama / Qwen2.5 ({OLLAMA_MODEL}, ctx={OLLAMA_CTX})",
                "hw_summary": _HW_SNAPSHOT.get("summary", "not scanned"),
            })

        elif cmd == "hardware":
            _send(conn, {"snapshot": _HW_SNAPSHOT})

        else:
            _send(conn, {"error": f"Unknown command: {cmd}"})

    except Exception as e:
        log.error(f"Client handler error: {e}")
        try: _send(conn, {"error": str(e)})
        except: pass
    finally:
        conn.close()


# ── Server loop ───────────────────────────────────────────────────────────────
def _run_server():
    open(PID_FILE, "w").write(str(os.getpid()))
    Path(SOCKET_PATH).unlink(missing_ok=True)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o600)
    srv.listen(10)

    label = (f"{_DISTRO_INFO.distro_name} "
             f"[{'SUPPORTED' if _DISTRO_INFO.supported else 'LIMITED'}]"
             if _DISTRO_INFO else "unknown distro")
    log.info(f"{PRODUCT_NAME} daemon started (PID {os.getpid()}) — {label}")

    def _shutdown(sig, frame):
        log.info("Shutting down...")
        srv.close()
        Path(SOCKET_PATH).unlink(missing_ok=True)
        Path(PID_FILE).unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_handle_client, args=(conn,), daemon=True).start()
        except OSError:
            break


def _daemonize():
    if os.fork() > 0: sys.exit(0)
    os.setsid()
    if os.fork() > 0: sys.exit(0)
    sys.stdout.flush(); sys.stderr.flush()
    with open(os.devnull) as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(LOG_FILE, "a") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


def _start_daemon_process(foreground=False):
    global _DISTRO_INFO, _DISTRO_FAMILY, _HW_SNAPSHOT
    _DISTRO_INFO, _DISTRO_FAMILY = detect_distro()
    _HW_SNAPSHOT = _scan_hardware()
    if not foreground:
        _daemonize()
    _run_server()


# ══════════════════════════════════════════════════════════════════════════════
# CLI — terminal client and interactive REPL
# ══════════════════════════════════════════════════════════════════════════════

# ── ANSI colours ──────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m";  BOLD   = "\033[1m";  DIM    = "\033[2m"
    GREEN  = "\033[38;5;82m";  LGREEN = "\033[38;5;120m"
    YELLOW = "\033[38;5;220m"; RED    = "\033[38;5;196m"
    CYAN   = "\033[38;5;51m";  WHITE  = "\033[97m"
    DGRAY  = "\033[38;5;238m"; MGRAY  = "\033[38;5;245m"

def _no_color():
    for a in [x for x in vars(C) if not x.startswith("_")]:
        setattr(C, a, "")

if not sys.stdout.isatty():
    _no_color()

def _banner() -> str:
    art = "\n".join(f" {C.GREEN}{C.BOLD}{l}{C.RESET}" for l in ASCII_BANNER_LINES)
    sub = f" {C.MGRAY}{PRODUCT_TAGLINE} — v{PRODUCT_VERSION}{C.RESET}"
    return f"\n{art}\n{sub}\n"

def _sep():
    print(f"{C.DGRAY}{'─' * min(shutil.get_terminal_size((80,20)).columns, 80)}{C.RESET}")


# ── Socket communication ──────────────────────────────────────────────────────
def _request(req: dict, timeout: int = 90) -> dict:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(SOCKET_PATH)
        s.sendall(json.dumps(req).encode() + _END)
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk: break
            data += chunk
            if data.endswith(_END):
                data = data[:-len(_END)]; break
        s.close()
        return json.loads(data.decode())
    except FileNotFoundError:
        return {"error": f"Daemon not running. Start with: {CLI_COMMAND} start"}
    except ConnectionRefusedError:
        return {"error": f"Daemon not responding. Try: {CLI_COMMAND} restart"}
    except socket.timeout:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": str(e)}


def _daemon_running() -> bool:
    if not Path(SOCKET_PATH).exists(): return False
    try: return _request({"cmd": "ping"}, timeout=3).get("status") == "ok"
    except: return False


# ── Daemon lifecycle ──────────────────────────────────────────────────────────
def _start_daemon(foreground=False):
    if _daemon_running():
        print(f"{C.YELLOW}⚠ Daemon already running{C.RESET}"); return True
    try:
        if foreground:
            os.execv(sys.executable, [sys.executable, __file__, "_daemon_fg"])
        else:
            subprocess.Popen(
                [sys.executable, __file__, "_daemon_bg"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            for _ in range(20):
                time.sleep(0.3)
                if _daemon_running():
                    pid = Path(PID_FILE).read_text().strip() if Path(PID_FILE).exists() else "?"
                    print(f"{C.GREEN}✓ {PRODUCT_NAME} daemon started (PID {pid}){C.RESET}")
                    print(f"{C.DIM}  Logs: tail -f {LOG_FILE}{C.RESET}")
                    return True
            print(f"{C.RED}✗ Daemon failed to start. Check: tail {LOG_FILE}{C.RESET}")
            return False
    except Exception as e:
        print(f"{C.RED}✗ Could not start daemon: {e}{C.RESET}"); return False

def _stop_daemon():
    if not Path(PID_FILE).exists():
        print(f"{C.YELLOW}⚠ No PID file found{C.RESET}"); return
    try:
        pid = int(Path(PID_FILE).read_text().strip())
        os.kill(pid, 15)
        print(f"{C.GREEN}✓ Daemon stopped (PID {pid}){C.RESET}")
    except ProcessLookupError:
        print(f"{C.YELLOW}⚠ Process not found, cleaning up...{C.RESET}")
        for f in [PID_FILE, SOCKET_PATH]: Path(f).unlink(missing_ok=True)
    except Exception as e:
        print(f"{C.RED}✗ {e}{C.RESET}")


# ── Display helpers ───────────────────────────────────────────────────────────
def _show_hardware():
    """Display the hardware snapshot collected at daemon startup."""
    if not _daemon_running():
        # Try loading from disk if daemon isn't running
        try:
            snap = json.load(open(HARDWARE_SNAPSHOT_FILE))
        except Exception:
            print(f"{C.RED}✗ Daemon not running and no cached snapshot found.{C.RESET}")
            print(f"  Start the daemon first: {C.CYAN}{CLI_COMMAND} start{C.RESET}")
            return
    else:
        r = _request({"cmd": "hardware"})
        if "error" in r:
            print(f"{C.RED}✗ {r['error']}{C.RESET}"); return
        snap = r.get("snapshot", {})

    if not snap:
        print(f"{C.YELLOW}⚠ No hardware data available yet.{C.RESET}")
        return

    print(f"\n{C.CYAN}{C.BOLD}Hardware & Driver Snapshot{C.RESET}")
    print(f"{C.DIM}Scanned: {snap.get('scanned_at', 'unknown')}{C.RESET}\n")

    sections = [
        ("kernel_version",  "Kernel"),
        ("cpu_info",        "CPU"),
        ("memory_info",     "Memory"),
        ("gpu_info",        "GPU / Display"),
        ("network_hw",      "Network Hardware"),
        ("audio_hw",        "Audio Hardware"),
        ("usb_devices",     "USB Devices"),
        ("block_devices",   "Block Devices"),
        ("loaded_modules",  "Loaded Modules"),
        ("dkms_status",     "DKMS Modules"),
        ("ubuntu_drivers",  "Recommended Drivers"),
        ("nvidia_smi",      "NVIDIA Status"),
        ("rfkill",          "RF/Wi-Fi Kill Switch"),
        ("dmesg_errors",    "Kernel Errors (dmesg)"),
    ]

    for key, label in sections:
        val = snap.get(key, "")
        if not val:
            continue
        print(f"{C.CYAN}{C.BOLD}{label}{C.RESET}")
        # Truncate long outputs for display
        lines = val.splitlines()
        if len(lines) > 15:
            for line in lines[:15]:
                print(f"  {C.MGRAY}{line}{C.RESET}")
            print(f"  {C.DIM}... ({len(lines) - 15} more lines — see daemon log for full output){C.RESET}")
        else:
            for line in lines:
                print(f"  {C.MGRAY}{line}{C.RESET}")
        print()


def _show_status():
    if not _daemon_running():
        print(f"{C.RED}✗ Daemon is NOT running{C.RESET}")
        print(f"  Start with: {C.CYAN}{CLI_COMMAND} start{C.RESET}"); return
    r = _request({"cmd": "status"})
    if "error" in r: print(f"{C.RED}✗ {r['error']}{C.RESET}"); return
    badge = f"{C.GREEN}[full support]{C.RESET}" if r.get("supported") else f"{C.YELLOW}[limited support]{C.RESET}"
    print(f"{C.GREEN}✓ Daemon running{C.RESET}  PID: {C.BOLD}{r.get('pid')}{C.RESET}")
    print(f"  Distro:    {C.CYAN}{r.get('distro','?')}{C.RESET}  {badge}")
    print(f"  Sessions:  {C.CYAN}{r.get('sessions',0)}{C.RESET}")
    print(f"  History:   {C.CYAN}{r.get('history_entries',0)} commands{C.RESET}")
    print(f"  Log:       {C.DIM}{r.get('log')}{C.RESET}")
    print(f"  AI:        {C.CYAN}{r.get('ai_backend', 'Ollama')}{C.RESET}")

def _show_distro():
    if not _daemon_running():
        print(f"{C.RED}✗ Daemon not running{C.RESET}"); return
    r = _request({"cmd": "distro_info"})
    if "error" in r: print(f"{C.RED}✗ {r['error']}{C.RESET}"); return
    badge = f"{C.GREEN}✓ Fully supported{C.RESET}" if r.get("supported") else f"{C.YELLOW}⚠ Limited support{C.RESET}"
    print(f"\n{C.CYAN}{C.BOLD}Detected System{C.RESET}")
    print(f"  Name:      {C.WHITE}{r.get('distro_name')}{C.RESET}")
    print(f"  Family:    {C.CYAN}{r.get('family')}{C.RESET}")
    print(f"  ID:        {r.get('distro_id')}")
    print(f"  Version:   {r.get('version_id') or 'n/a'}")
    print(f"  Codename:  {r.get('codename') or 'n/a'}")
    print(f"  Pkg mgrs:  {C.CYAN}{', '.join(r.get('pkg_managers',[]) or ['none detected'])}{C.RESET}")
    print(f"  Support:   {badge}")
    if r.get("support_note"):
        print(f"\n  {C.YELLOW}{r['support_note']}{C.RESET}")

def _print_reply(reply: str, exec_output=None):
    in_code = False
    for line in reply.split("\n"):
        if line.startswith("```"):
            in_code = not in_code
            print(f"{C.DGRAY}{line}{C.RESET}"); continue
        if in_code:
            print(f"{C.LGREEN}{line}{C.RESET}"); continue
        if line.startswith(("# ","## ","### ")):
            print(f"\n{C.CYAN}{C.BOLD}{line}{C.RESET}")
        elif line.startswith("✓"):  print(f"{C.GREEN}{line}{C.RESET}")
        elif line.startswith("✗"):  print(f"{C.RED}{line}{C.RESET}")
        elif line.startswith("⚠"):  print(f"{C.YELLOW}{line}{C.RESET}")
        elif line.startswith("→"):  print(f"{C.CYAN}{line}{C.RESET}")
        elif line.startswith(("- ","* ")): print(f"  {C.GREEN}›{C.RESET} {line[2:]}")
        else: print(line)

    if exec_output:
        print(f"\n{C.YELLOW}{'─'*60}{C.RESET}")
        print(f"{C.YELLOW}{C.BOLD}EXECUTION OUTPUT{C.RESET}")
        print(f"{C.YELLOW}{'─'*60}{C.RESET}")
        for line in exec_output.split("\n"):
            if line.startswith("$"):       print(f"{C.GREEN}{C.BOLD}{line}{C.RESET}")
            elif "✓" in line:              print(f"{C.GREEN}{line}{C.RESET}")
            elif "✗" in line or "error" in line.lower(): print(f"{C.RED}{line}{C.RESET}")
            elif line.startswith(("⚡","─")): print(f"{C.CYAN}{line}{C.RESET}")
            else:                          print(f"{C.MGRAY}{line}{C.RESET}")


# ── Shell history auto-import ─────────────────────────────────────────────────
def _get_shell_history() -> list:
    for path in ("~/.bash_history", "~/.zsh_history", "~/.local/share/fish/fish_history"):
        p = Path(os.path.expanduser(path))
        if p.exists():
            try:
                cmds = []
                for l in p.read_text(errors="replace").split("\n"):
                    l = l.strip()
                    if l.startswith(": ") and ";" in l: l = l.split(";",1)[-1]  # zsh timestamps
                    if l.startswith("- cmd: "): l = l[7:]                        # fish format
                    if l and not l.startswith("#"): cmds.append(l)
                return cmds[-MAX_HISTORY:]
            except: pass
    return []


# ── Interactive REPL ──────────────────────────────────────────────────────────
def _repl(session: str, api_key: str = "", auto_exec: bool = False):
    print(_banner())

    dr = _request({"cmd": "distro_info"})
    if "error" not in dr:
        badge = f"{C.GREEN}[full support]{C.RESET}" if dr.get("supported") else f"{C.YELLOW}[limited support]{C.RESET}"
        pms   = ", ".join(dr.get("pkg_managers",[]) or ["none detected"])
        print(f"{C.MGRAY}Session: {C.CYAN}{session}{C.RESET}  |  "
              f"{C.WHITE}{dr.get('distro_name')}{C.RESET} {badge}  |  "
              f"pkg: {C.CYAN}{pms}{C.RESET}")
        if not dr.get("supported") and dr.get("support_note"):
            print(f"{C.YELLOW}⚠ {dr['support_note']}{C.RESET}")
    print(f"{C.MGRAY}Model: {C.CYAN}{OLLAMA_MODEL}{C.RESET} (ctx {OLLAMA_CTX})  |  Type {C.CYAN}help{C.MGRAY} for commands  |  {C.CYAN}Ctrl+C{C.MGRAY} to exit{C.RESET}")
    _sep()

    hist = _get_shell_history()
    if hist:
        _request({"cmd": "history_import", "commands": hist})
        print(f"{C.DIM}📜 Auto-imported {len(hist)} shell history entries{C.RESET}\n")

    while True:
        try:
            user_input = input(
                f"{C.GREEN}you@{CLI_COMMAND}{C.RESET}{C.DGRAY}:{C.RESET}{C.CYAN}~{C.RESET}$ "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.MGRAY}Goodbye. {PRODUCT_NAME} daemon keeps running in background.{C.RESET}")
            break

        if not user_input: continue

        # ── Built-in commands ──────────────────────────────────────────────
        if user_input in ("exit", "quit", "q"):
            print(f"{C.MGRAY}Exiting. Use '{CLI_COMMAND} stop' to halt the daemon.{C.RESET}")
            break

        elif user_input == "help":
            print(f"""
{C.CYAN}{C.BOLD}{PRODUCT_NAME} REPL Commands:{C.RESET}
  {C.GREEN}help{C.RESET}             Show this help
  {C.GREEN}status{C.RESET}           Show daemon status
  {C.GREEN}distro{C.RESET}           Show distro & package manager info
  {C.GREEN}history{C.RESET}          Show imported shell history (last 20)
  {C.GREEN}clear{C.RESET}            Clear current session context
  {C.GREEN}exec on/off{C.RESET}      Toggle auto-execution of suggested fixes
  {C.GREEN}exit / quit{C.RESET}      Exit REPL (daemon stays running)

{C.CYAN}Example prompts:{C.RESET}
  "sudo apt upgrade gives E: dpkg was interrupted..."
  "analyze my history for problems"
  "how do I fix broken dependencies?"
  "give me UX improvement tips"
  "run the fix" / "apply it"  (requires exec on)
""")
        elif user_input == "status":   _show_status()
        elif user_input == "distro":   _show_distro()
        elif user_input == "clear":
            _request({"cmd": "session_clear", "session": session})
            print(f"{C.GREEN}✓ Session context cleared{C.RESET}")
        elif user_input == "exec on":
            auto_exec = True
            print(f"{C.GREEN}✓ Auto-execution ON — fixes will run automatically{C.RESET}")
        elif user_input == "exec off":
            auto_exec = False
            print(f"{C.YELLOW}⚠ Auto-execution OFF{C.RESET}")
        elif user_input == "history":
            r = _request({"cmd": "history_get"})
            hist = r.get("history", [])
            if hist:
                print(f"\n{C.CYAN}Last {min(20,len(hist))} commands:{C.RESET}")
                for c in hist[-20:]: print(f"  {C.DGRAY}${C.RESET} {c}")
            else:
                print(f"{C.YELLOW}No history imported yet{C.RESET}")

        else:
            # ── Send to daemon ─────────────────────────────────────────────
            print(f"\n{C.DIM}thinking...{C.RESET}", end="\r", flush=True)
            r = _request({
                "cmd": "chat", "message": user_input,
                "session": session, "auto_exec": auto_exec,
            })
            print(" " * 20, end="\r")
            if "error" in r:
                print(f"{C.RED}✗ {r['error']}{C.RESET}")
            else:
                print(f"\n{C.GREEN}{C.BOLD}{PRODUCT_NAME}{C.RESET} {C.DGRAY}━━{C.RESET}")
                _print_reply(r.get("reply",""), r.get("exec_output"))

        print(); _sep(); print()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

# ══ FIRST-RUN SETUP WIZARD ══════════════════════════════════════════════════
# Guides through backend/model selection and saves to config.json.
# Triggered automatically on first run, or manually: daemoniq setup
# ════════════════════════════════════════════════════════════════════════════

CONFIG_FILE = os.path.join(INSTALL_DIR, "config.json")
ENV_FILE    = os.path.join(INSTALL_DIR, "env")


def _load_config() -> dict:
    try:
        return json.load(open(CONFIG_FILE))
    except Exception:
        return {}


def _save_config(cfg: dict):
    os.makedirs(INSTALL_DIR, exist_ok=True)
    json.dump(cfg, open(CONFIG_FILE, "w"), indent=2)
    lines = []
    if cfg.get("groq_key"):
        lines.append(f"GROQ_API_KEY={cfg['groq_key']}")
    with open(ENV_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(ENV_FILE, 0o600)


def _save_to_shell(var: str, val: str):
    shell = os.environ.get("SHELL", "")
    rc = (os.path.expanduser("~/.zshrc") if "zsh" in shell
          else os.path.expanduser("~/.config/fish/config.fish") if "fish" in shell
          else os.path.expanduser("~/.bashrc"))
    try:
        existing = open(rc).read() if os.path.exists(rc) else ""
        lines = [l for l in existing.splitlines() if not l.startswith(f"export {var}=")]
        lines.append(f"export {var}={val}")
        open(rc, "w").write("\n".join(lines) + "\n")
        return rc
    except Exception:
        return None


def _ollama_running() -> bool:
    import urllib.request, urllib.error
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


def _start_ollama_bg():
    subprocess.Popen(["ollama", "serve"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(3)


def _ollama_models() -> list:
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _pull_model(model: str) -> bool:
    print(f"\n{C.DIM}  Pulling {model} — this may take a few minutes...{C.RESET}\n")
    return subprocess.run(["ollama", "pull", model]).returncode == 0


def _install_ollama() -> bool:
    import urllib.request
    print(f"\n{C.DIM}  Downloading Ollama installer...{C.RESET}")
    try:
        with urllib.request.urlopen("https://ollama.com/install.sh", timeout=30) as r:
            script = r.read().decode()
        return subprocess.run(["bash", "-s"], input=script, text=True, timeout=300).returncode == 0
    except Exception as e:
        print(f"{C.RED}  Could not install Ollama: {e}{C.RESET}")
        return False


def _patch_script_model(script_name: str, old_pattern: str, new_model: str):
    path = os.path.join(INSTALL_DIR, script_name)
    if not os.path.exists(path):
        return
    content = open(path).read()
    content = re.sub(old_pattern, f'OLLAMA_MODEL = "{new_model}"', content, flags=re.MULTILINE)
    open(path, "w").write(content)


def run_setup():
    print(_banner())
    print(f"{C.CYAN}{C.BOLD}  Welcome to {PRODUCT_NAME}!{C.RESET}")
    print(f"  Answer a couple of quick questions and you're ready to go.\n")
    _sep()

    cfg = _load_config()

    # ── Step 1: Distro ────────────────────────────────────────────────────────
    # Auto-detect from /etc/os-release, let user confirm or correct it.

    DISTROS = [
        ("ubuntu",   "Ubuntu"),
        ("debian",   "Debian"),
        ("mint",     "Linux Mint"),
        ("pop",      "Pop!_OS"),
        ("kali",     "Kali Linux"),
        ("fedora",   "Fedora"),
        ("rhel",     "RHEL / CentOS / Rocky"),
        ("arch",     "Arch Linux"),
        ("manjaro",  "Manjaro"),
        ("opensuse", "openSUSE"),
        ("alpine",   "Alpine Linux"),
        ("other",    "Other / Not listed"),
    ]

    def _detect_distro_id() -> str:
        """Read /etc/os-release and return a normalised distro key."""
        try:
            raw = {}
            for line in open("/etc/os-release").read().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    raw[k.strip()] = v.strip().strip('"')
            id_val  = raw.get("ID", "").lower()
            id_like = raw.get("ID_LIKE", "").lower()
            combined = id_val + " " + id_like
            # Map to our list keys
            for key, _ in DISTROS:
                if key in combined:
                    return key
        except Exception:
            pass
        return ""

    detected = _detect_distro_id()

    print(f"\n{C.CYAN}{C.BOLD}  Step 1 of 2 — What Linux distro are you using?{C.RESET}\n")
    for i, (key, label) in enumerate(DISTROS, 1):
        marker = f"  {C.YELLOW}← detected{C.RESET}" if key == detected else ""
        print(f"  {C.CYAN}{i:>2}){C.RESET} {label}{marker}")
    print()

    # Build default from detection
    default_idx = next((i for i, (k, _) in enumerate(DISTROS, 1) if k == detected), None)
    prompt_hint = f"1-{len(DISTROS)}, default {default_idx}" if default_idx else f"1-{len(DISTROS)}"

    while True:
        try:
            raw_choice = input(f"  {C.GREEN}Your distro [{prompt_hint}]:{C.RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.YELLOW}  Setup cancelled. Run '{CLI_COMMAND} setup' any time.{C.RESET}\n")
            return
        if raw_choice == "" and default_idx:
            distro_idx = default_idx
            break
        if raw_choice.isdigit() and 1 <= int(raw_choice) <= len(DISTROS):
            distro_idx = int(raw_choice)
            break
        print(f"  Please enter a number between 1 and {len(DISTROS)}.")

    distro_key, distro_label = DISTROS[distro_idx - 1]
    cfg["distro_key"]   = distro_key
    cfg["distro_label"] = distro_label
    print(f"  {C.GREEN}✓{C.RESET} Got it — {C.WHITE}{distro_label}{C.RESET}\n")

    print()
    _sep()

    # ── Step 2: Pick a tier ───────────────────────────────────────────────────
    print(f"\n{C.CYAN}{C.BOLD}  Step 2 of 2 — How would you like to run {PRODUCT_NAME}?{C.RESET}\n")
    print(f"  {C.CYAN}{C.BOLD}1) Cloud  {C.RESET}{C.GREEN}[Recommended]{C.RESET}")
    print( "     Fast and accurate. Needs a free account but no local setup.")
    print(f"     {C.DIM}(Groq - runs llama-3.3-70b-versatile on their servers){C.RESET}")
    print()
    print(f"  {C.CYAN}{C.BOLD}2) Local - Light{C.RESET}")
    print( "     Runs on your machine. No account needed, works offline.")
    print( "     Good on most computers with at least 4GB of free RAM.")
    print(f"     {C.DIM}(Ollama - runs Llama 3 locally){C.RESET}")
    print()
    print(f"  {C.CYAN}{C.BOLD}3) Local - Heavy{C.RESET}")
    print( "     Runs on your machine. Best local quality, works offline.")
    print( "     Needs at least 9GB of free RAM.")
    print(f"     {C.DIM}(Ollama - runs Qwen2.5 locally){C.RESET}")
    print()

    while True:
        try:
            choice = input(f"  {C.GREEN}Your choice [1-3, default 1]:{C.RESET} ").strip() or "1"
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.YELLOW}  Setup cancelled. Run '{CLI_COMMAND} setup' to configure later.{C.RESET}\n")
            return
        if choice in ("1", "2", "3"):
            break
        print("  Please enter 1, 2, or 3.")

    backend = {"1": "groq", "2": "ollama", "3": "qwen"}[choice]
    cfg["backend"] = backend

    # ── Step 2: Any additional config needed for the chosen tier ──────────────
    print()
    _sep()

    if backend == "groq":
        print(f"\n{C.CYAN}{C.BOLD}  One last thing - your free Groq API key{C.RESET}\n")
        print(f"  1. Go to {C.CYAN}https://console.groq.com{C.RESET} and sign up (free, no card needed)")
        print( "  2. Click API Keys in the sidebar and create a new key")
        print( "  3. Paste it below\n")

        existing_key = os.environ.get("GROQ_API_KEY", cfg.get("groq_key", ""))
        if existing_key:
            print(f"  {C.GREEN}✓{C.RESET} You already have a GROQ_API_KEY set - nothing to do.\n")
            cfg["groq_key"] = existing_key
        else:
            try:
                key = input(f"  {C.GREEN}Paste your key (gsk_...):{C.RESET} ").strip()
            except (KeyboardInterrupt, EOFError):
                key = ""
            if key:
                cfg["groq_key"] = key
                rc = _save_to_shell("GROQ_API_KEY", key)
                os.environ["GROQ_API_KEY"] = key
                print(f"  {C.GREEN}✓{C.RESET} Key saved{f' to {rc}' if rc else ''}.\n")
            else:
                print(f"  {C.YELLOW}⚠{C.RESET} No key entered.")
                print( "  Add it later: export GROQ_API_KEY=gsk_...\n")

        cfg["groq_model"]    = "llama-3.3-70b-versatile"
        cfg["active_script"] = "daemoniq-cloud.py"

    else:
        is_qwen  = (backend == "qwen")
        model    = "qwen2.5:14b" if is_qwen else "llama3"
        target   = "daemoniq-heavy.py" if is_qwen else "daemoniq-light.py"
        pattern  = (r'OLLAMA_MODEL = "qwen2.5:14b"' if is_qwen
                    else r'OLLAMA_MODEL = "llama3"')
        size_str = "~9GB" if is_qwen else "~4GB"

        print(f"\n{C.CYAN}{C.BOLD}  Setting up local mode ({model}, {size_str}){C.RESET}\n")
        print(f"  {PRODUCT_NAME} needs Ollama to run AI models on your machine.\n")

        if not shutil.which("ollama"):
            print(f"  {C.YELLOW}⚠{C.RESET} Ollama is not installed yet.")
            try:
                ans = input("  Install it now? [Y/n] ").strip().lower() or "y"
            except (KeyboardInterrupt, EOFError):
                ans = "n"
            if ans != "n":
                if _install_ollama():
                    print(f"  {C.GREEN}✓{C.RESET} Ollama installed.\n")
                else:
                    print(f"  {C.RED}✗{C.RESET} Install failed.")
                    print( "  Install manually: https://ollama.com/download")
                    print(f"  Then run: ollama pull {model} && {CLI_COMMAND} setup\n")
                    _save_config(cfg); return
            else:
                print( "  Install later: https://ollama.com/download")
                print(f"  Then run: ollama pull {model} && {CLI_COMMAND} setup\n")
                _save_config(cfg); return
        else:
            print(f"  {C.GREEN}✓{C.RESET} Ollama is installed.\n")

        if not _ollama_running():
            print(f"  {C.DIM}Starting Ollama service...{C.RESET}")
            _start_ollama_bg()

        _patch_script_model(target, pattern, model)
        cfg["ollama_model"]  = model
        cfg["active_script"] = target

        pulled = _ollama_models()
        base   = model.split(":")[0]
        if any(base in m for m in pulled):
            print(f"  {C.GREEN}✓{C.RESET} {model} is already downloaded.\n")
        else:
            print(f"  The {model} model ({size_str}) needs to be downloaded once.")
            try:
                ans = input(f"  Download it now? [Y/n] ").strip().lower() or "y"
            except (KeyboardInterrupt, EOFError):
                ans = "n"
            if ans != "n":
                if _pull_model(model):
                    print(f"  {C.GREEN}✓{C.RESET} {model} downloaded and ready.\n")
                else:
                    print(f"  {C.YELLOW}⚠{C.RESET} Download failed. Try: ollama pull {model}\n")
            else:
                print(f"  {C.DIM}Download later: ollama pull {model}{C.RESET}\n")

    _save_config(cfg)
    _sep()

    tier   = {"groq": "Cloud", "ollama": "Local - Light", "qwen": "Local - Heavy"}[backend]
    mdl    = cfg.get("groq_model") or cfg.get("ollama_model", "")
    distro = cfg.get("distro_label", "Unknown")
    print(f"\n  {C.GREEN}{C.BOLD}You're all set!{C.RESET}\n")
    print(f"  Distro: {C.CYAN}{distro}{C.RESET}")
    print(f"  Mode:   {C.CYAN}{tier}{C.RESET}")
    print(f"  Model:  {C.CYAN}{mdl}{C.RESET}")
    print(f"\n  Run {C.CYAN}{CLI_COMMAND}{C.RESET} to start.")
    print(f"  Run {C.CYAN}{CLI_COMMAND} setup{C.RESET} any time to change your settings.\n")


# ══ VERSION CONTROL ══════════════════════════════════════════════════════════
# Tracks the installed version, checks for updates from a remote manifest,
# backs up before upgrading, and records a local changelog.
# ════════════════════════════════════════════════════════════════════════════

# Remote URL where the version manifest is hosted.
# Update this to your real repo URL before publishing.
UPDATE_BASE_URL = "https://raw.githubusercontent.com/JayRaj21/DaemonIQ/master"

VERSION_FILE    = os.path.join(INSTALL_DIR, "version.json")
BACKUP_DIR      = os.path.join(INSTALL_DIR, "backups")
CHANGELOG_FILE  = os.path.join(INSTALL_DIR, "changelog.md")


def _fetch_url(url: str, timeout: int = 10) -> str | None:
    """Download a URL and return its text content, or None on failure."""
    import urllib.request, urllib.error
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode(errors="replace")
    except Exception as e:
        log.debug(f"Fetch failed for {url}: {e}")
        return None


def _read_version_file() -> dict:
    """Read the local version tracking file."""
    try:
        return json.load(open(VERSION_FILE))
    except Exception:
        return {}


def _write_version_file(data: dict):
    os.makedirs(INSTALL_DIR, exist_ok=True)
    json.dump(data, open(VERSION_FILE, "w"), indent=2)


def _backup_current(variant_filename: str) -> str | None:
    """
    Back up the currently installed script before an upgrade.
    Returns the backup path, or None if backup failed.
    Keeps only the 5 most recent backups to avoid disk bloat.
    """
    import shutil as _shutil
    os.makedirs(BACKUP_DIR, exist_ok=True)
    src = os.path.join(INSTALL_DIR, variant_filename)
    if not os.path.exists(src):
        return None

    import datetime
    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest    = os.path.join(BACKUP_DIR, f"{variant_filename}.{PRODUCT_VERSION}.{ts}.bak")
    try:
        _shutil.copy2(src, dest)
        # Prune old backups — keep newest 5 per variant
        pattern = f"{variant_filename}."
        all_baks = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.startswith(pattern)],
            reverse=True,
        )
        for old in all_baks[5:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception:
                pass
        return dest
    except Exception as e:
        log.warning(f"Backup failed: {e}")
        return None


def _append_changelog(version: str, notes: str):
    """Append an entry to the local changelog file."""
    import datetime
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"\n## v{version} — {ts}\n{notes}\n"
    try:
        with open(CHANGELOG_FILE, "a") as f:
            f.write(line)
    except Exception:
        pass


def _parse_semver(v: str) -> tuple:
    """Parse 'X.Y.Z' into (X, Y, Z) ints for comparison. Returns (0,0,0) on error."""
    try:
        parts = v.strip().lstrip("v").split(".")
        return tuple(int(p) for p in parts[:3])
    except Exception:
        return (0, 0, 0)


def run_uninstall():
    """
    Completely remove DaemonIQ from this machine.
    Stops the daemon, removes all installed files, the launcher,
    the PATH entry, and the systemd service if present.
    """
    import shutil as _shutil

    print(f"\n  {C.CYAN}{C.BOLD}Uninstall {PRODUCT_NAME}{C.RESET}\n")
    print(f"  This will remove:")
    print(f"  {C.DIM}  All scripts and config:   {INSTALL_DIR}{C.RESET}")
    print(f"  {C.DIM}  The daemoniq command:      ~/.local/bin/{CLI_COMMAND}{C.RESET}")
    print(f"  {C.DIM}  The PATH entry in your shell config{C.RESET}")
    print(f"  {C.DIM}  The systemd service (if installed){C.RESET}")
    print()

    try:
        ans = input(f"  {C.RED}Are you sure? This cannot be undone. [y/N]:{C.RESET} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {C.DIM}Uninstall cancelled.{C.RESET}\n")
        return
    if ans != "y":
        print(f"  {C.DIM}Uninstall cancelled.{C.RESET}\n")
        return

    print()

    # 1. Stop the daemon
    if _daemon_running():
        _stop_daemon()
        print(f"  {C.GREEN}✓{C.RESET} Daemon stopped")
    else:
        Path(SOCKET_PATH).unlink(missing_ok=True)
        Path(PID_FILE).unlink(missing_ok=True)

    # 2. Disable and remove systemd service
    svc_file = os.path.expanduser(f"~/.config/systemd/user/{DAEMON_LABEL}.service")
    if os.path.exists(svc_file):
        try:
            subprocess.run(["systemctl", "--user", "disable", "--now", DAEMON_LABEL],
                           capture_output=True)
            os.remove(svc_file)
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
            print(f"  {C.GREEN}✓{C.RESET} systemd service removed")
        except Exception as e:
            print(f"  {C.YELLOW}⚠{C.RESET} Could not remove systemd service: {e}")

    # 3. Remove the launcher
    launcher = os.path.expanduser(f"~/.local/bin/{CLI_COMMAND}")
    if os.path.exists(launcher):
        os.remove(launcher)
        print(f"  {C.GREEN}✓{C.RESET} Removed ~/.local/bin/{CLI_COMMAND}")

    # 4. Remove install directory (scripts, config, backups, snapshots)
    if os.path.exists(INSTALL_DIR):
        _shutil.rmtree(INSTALL_DIR)
        print(f"  {C.GREEN}✓{C.RESET} Removed {INSTALL_DIR}")

    # 5. Remove PATH entry from shell config
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        rc_candidates = [os.path.expanduser("~/.zshrc")]
    elif "fish" in shell:
        rc_candidates = [os.path.expanduser("~/.config/fish/config.fish")]
    else:
        rc_candidates = [
            os.path.expanduser("~/.bashrc"),
            os.path.expanduser("~/.bash_profile"),
        ]

    for rc in rc_candidates:
        if not os.path.exists(rc):
            continue
        try:
            lines    = open(rc).readlines()
            filtered = [
                l for l in lines
                if not (("local/bin" in l) and ("PATH" in l or "fish_add_path" in l))
            ]
            if len(filtered) < len(lines):
                open(rc, "w").writelines(filtered)
                print(f"  {C.GREEN}✓{C.RESET} Removed PATH entry from {rc}")
        except Exception as e:
            print(f"  {C.YELLOW}⚠{C.RESET} Could not clean {rc}: {e}")

    print(f"\n  {C.GREEN}{C.BOLD}DaemonIQ has been fully removed.{C.RESET}")
    print(f"  {C.DIM}Open a new terminal to complete the removal.{C.RESET}\n")


def run_version():
    """Show the currently installed version and variant."""
    vdata = _read_version_file()
    print(f"\n  {C.CYAN}{C.BOLD}{PRODUCT_NAME}{C.RESET}  v{PRODUCT_VERSION}")
    print(f"  Variant:     {C.CYAN}{os.path.basename(__file__)}{C.RESET}")
    if vdata.get("last_updated"):
        print(f"  Last update: {C.DIM}{vdata['last_updated']}{C.RESET}")
    if vdata.get("last_check"):
        print(f"  Last check:  {C.DIM}{vdata['last_check']}{C.RESET}")
    if os.path.exists(CHANGELOG_FILE):
        print(f"  Changelog:   {C.DIM}{CHANGELOG_FILE}{C.RESET}")
    # Check for backups
    if os.path.exists(BACKUP_DIR):
        baks = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".bak")]
        if baks:
            print(f"  Backups:     {C.DIM}{len(baks)} backup(s) in {BACKUP_DIR}{C.RESET}")
    print()


def run_update(force: bool = False):
    """
    Check for an available update and apply it if one is found.

    The remote manifest is a JSON file at UPDATE_BASE_URL/manifest.json:
    {
        "version": "0.2.0",
        "variants": {
            "daemoniq-cloud.py":  "daemoniq-cloud.py",
            "daemoniq-light.py":  "daemoniq-light.py",
            "daemoniq-heavy.py":  "daemoniq-heavy.py"
        },
        "changelog": "- Fixed apt lock detection\n- Added Arch Linux support",
        "min_python": "3.8"
    }
    """
    import datetime, shutil as _shutil

    print(f"\n  {C.DIM}Checking for updates...{C.RESET}")

    # Fetch remote manifest
    manifest_url = f"{UPDATE_BASE_URL}/manifest.json"
    raw = _fetch_url(manifest_url)

    # Record check time regardless of outcome
    vdata = _read_version_file()
    vdata["last_check"] = datetime.datetime.now().isoformat()
    _write_version_file(vdata)

    if raw is None:
        print(f"  {C.YELLOW}⚠{C.RESET} Could not reach update server.")
        print(f"  {C.DIM}Check your internet connection or try again later.{C.RESET}\n")
        return

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  {C.RED}✗{C.RESET} Update manifest is malformed. Please report this.\n")
        return

    remote_version = manifest.get("version", "0.0.0")
    changelog_notes = manifest.get("changelog", "No notes provided.")

    # Compare versions
    if not force and _parse_semver(remote_version) <= _parse_semver(PRODUCT_VERSION):
        print(f"  {C.GREEN}✓{C.RESET} Already up to date — v{PRODUCT_VERSION} is the latest.\n")
        return

    # Determine which variant file this is
    this_filename = os.path.basename(__file__)
    variants      = manifest.get("variants", {})
    remote_file   = variants.get(this_filename)

    if not remote_file:
        print(f"  {C.YELLOW}⚠{C.RESET} No update available for variant '{this_filename}'.")
        print(f"  {C.DIM}Remote manifest does not list this variant.{C.RESET}\n")
        return

    print(f"  {C.CYAN}Update available:{C.RESET} v{PRODUCT_VERSION} → v{remote_version}")
    print(f"\n  {C.BOLD}What's new in v{remote_version}:{C.RESET}")
    for line in changelog_notes.strip().splitlines():
        print(f"    {line}")
    print()

    # Confirm
    try:
        ans = input(f"  {C.GREEN}Install update? [y/N]:{C.RESET} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {C.YELLOW}Update cancelled.{C.RESET}\n")
        return
    if ans != "y":
        print(f"  {C.DIM}Skipped. Run '{CLI_COMMAND} update' again when you're ready.{C.RESET}\n")
        return

    # Back up current version
    backup_path = _backup_current(this_filename)
    if backup_path:
        print(f"  {C.DIM}Backed up current version → {backup_path}{C.RESET}")
    else:
        print(f"  {C.YELLOW}⚠{C.RESET} Could not create backup — proceeding anyway.")

    # Download new version
    download_url = f"{UPDATE_BASE_URL}/{remote_file}"
    print(f"  {C.DIM}Downloading {download_url}...{C.RESET}")
    new_content = _fetch_url(download_url, timeout=30)

    if not new_content:
        print(f"  {C.RED}✗{C.RESET} Download failed. Your current version is unchanged.")
        print(f"  {C.DIM}Try again later or download manually from: {UPDATE_BASE_URL}{C.RESET}\n")
        return

    # Validate the downloaded file is parseable Python before replacing
    try:
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            ast_mod = __import__("ast")
            ast_mod.parse(new_content)
    except SyntaxError as e:
        print(f"  {C.RED}✗{C.RESET} Downloaded file has a syntax error: {e}")
        print(f"  {C.DIM}This is a server-side problem. Your current version is unchanged.{C.RESET}\n")
        return

    # Write the new version
    install_path = os.path.join(INSTALL_DIR, this_filename)
    try:
        open(install_path, "w").write(new_content)
        os.chmod(install_path, 0o755)
    except Exception as e:
        print(f"  {C.RED}✗{C.RESET} Could not write update: {e}\n")
        # Try to restore backup
        if backup_path and os.path.exists(backup_path):
            _shutil.copy2(backup_path, install_path)
            print(f"  {C.YELLOW}⚠{C.RESET} Restored from backup.")
        return

    # Record update
    import datetime
    vdata["last_updated"] = datetime.datetime.now().isoformat()
    vdata["previous_version"] = PRODUCT_VERSION
    vdata["current_version"]  = remote_version
    _write_version_file(vdata)
    _append_changelog(remote_version, changelog_notes)

    print(f"  {C.GREEN}✓{C.RESET} Updated to v{remote_version}.")
    print(f"  {C.DIM}Restart the daemon to apply: {CLI_COMMAND} restart{C.RESET}\n")


def run_rollback():
    """Restore the most recent backup of the current variant."""
    import shutil as _shutil

    this_filename = os.path.basename(__file__)
    if not os.path.exists(BACKUP_DIR):
        print(f"  {C.YELLOW}⚠{C.RESET} No backups found.\n")
        return

    pattern  = f"{this_filename}."
    all_baks = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith(pattern)],
        reverse=True,
    )
    if not all_baks:
        print(f"  {C.YELLOW}⚠{C.RESET} No backups found for {this_filename}.\n")
        return

    latest   = all_baks[0]
    bak_path = os.path.join(BACKUP_DIR, latest)

    print(f"\n  Most recent backup: {C.CYAN}{latest}{C.RESET}")
    try:
        ans = input(f"  {C.GREEN}Restore this backup? [y/N]:{C.RESET} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(); return
    if ans != "y":
        print(f"  {C.DIM}Rollback cancelled.{C.RESET}\n")
        return

    install_path = os.path.join(INSTALL_DIR, this_filename)
    try:
        _shutil.copy2(bak_path, install_path)
        os.chmod(install_path, 0o755)
        print(f"  {C.GREEN}✓{C.RESET} Rolled back. Restart the daemon: {CLI_COMMAND} restart\n")
    except Exception as e:
        print(f"  {C.RED}✗{C.RESET} Rollback failed: {e}\n")


def main():
    # Internal: daemon bootstrap modes (called by subprocess)
    if len(sys.argv) == 2 and sys.argv[1] == "_daemon_bg":
        _start_daemon_process(foreground=False); return
    if len(sys.argv) == 2 and sys.argv[1] == "_daemon_fg":
        _start_daemon_process(foreground=True); return

    parser = argparse.ArgumentParser(
        prog=CLI_COMMAND,
        description=f"{PRODUCT_NAME} — {PRODUCT_TAGLINE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Examples:\n"
            f"  {CLI_COMMAND} start                   Start the background daemon\n"
            f"  {CLI_COMMAND}                         Open interactive REPL\n"
            f"  {CLI_COMMAND} \"apt lock error\"        One-shot question\n"
            f"  {CLI_COMMAND} --exec \"fix broken pkg\"  Ask and auto-apply fix\n"
            f"  {CLI_COMMAND} --session work           Use a named session\n"
            f"  {CLI_COMMAND} status                   Check daemon health\n"
            f"  {CLI_COMMAND} distro                   Show distro info\n"
            f"  {CLI_COMMAND} stop                     Stop the daemon\n"
            f"  {CLI_COMMAND} logs                     Tail daemon logs"
        ),
    )
    parser.add_argument("message",    nargs="?",           help="One-shot message (skips REPL)")
    parser.add_argument("--session",  "-s", default="default", help="Session name")
    parser.add_argument("--exec",     dest="auto_exec", action="store_true", help="Auto-apply suggested fixes")
    parser.add_argument("--no-color", action="store_true", help="Disable colour output")
    args, _ = parser.parse_known_args()

    if args.no_color: _no_color()

    api_key = ""  # unused in local mode — Ollama needs no key

    SUBCMDS = {"start","stop","restart","status","logs","history","sessions","distro","setup","hardware","version","update","rollback","uninstall"}

    if args.message in SUBCMDS:
        cmd = args.message
        if cmd == "start":
            _start_daemon()
        elif cmd == "stop":
            _stop_daemon()
        elif cmd == "restart":
            _stop_daemon(); time.sleep(1); _start_daemon()
        elif cmd == "status":
            _show_status()
        elif cmd == "distro":
            if not _daemon_running():
                print(f"{C.YELLOW}⚡ Starting {PRODUCT_NAME} daemon...{C.RESET}")
                _start_daemon()
            _show_distro()
        elif cmd == "logs":
            os.execvp("tail", ["tail", "-f", LOG_FILE])
        elif cmd == "history":
            if not _daemon_running(): print(f"{C.RED}✗ Daemon not running{C.RESET}"); return
            r = _request({"cmd": "history_get"})
            for c in r.get("history", [])[-50:]: print(c)
        elif cmd == "sessions":
            if not _daemon_running(): print(f"{C.RED}✗ Daemon not running{C.RESET}"); return
            r = _request({"cmd": "sessions_list"})
            for s in r.get("sessions", []): print(s)
        elif cmd == "setup":
            run_setup()
        elif cmd == "hardware":
            _show_hardware()
        elif cmd == "version":
            run_version()
        elif cmd == "update":
            run_update()
        elif cmd == "rollback":
            run_rollback()
        elif cmd == "uninstall":
            run_uninstall()
        return

    # Ensure daemon is running
    if not _daemon_running():
        print(f"{C.YELLOW}⚡ Starting {PRODUCT_NAME} daemon...{C.RESET}")
        if not _start_daemon(): sys.exit(1)

    # No API key needed — check Ollama is reachable instead
    ok_ollama, ollama_msg = _check_ollama()
    if not ok_ollama:
        print(f"{C.RED}✗ Ollama not available:{C.RESET}")
        for line in ollama_msg.split("\n"):
            print(f"  {line}")
        sys.exit(1)

    # One-shot mode
    if args.message:
        print(f"{C.DIM}thinking...{C.RESET}", end="\r", flush=True)
        r = _request({
            "cmd": "chat", "message": args.message,
            "session": args.session, "auto_exec": args.auto_exec,
        })
        print(" " * 20, end="\r")
        if "error" in r: print(f"{C.RED}✗ {r['error']}{C.RESET}"); sys.exit(1)
        _print_reply(r.get("reply",""), r.get("exec_output"))
        return

    # Interactive REPL
    _repl(args.session, api_key, args.auto_exec)


if __name__ == "__main__":
    main()
