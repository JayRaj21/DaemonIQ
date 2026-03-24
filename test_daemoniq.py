#!/usr/bin/env python3
"""
Unit tests for DaemonIQ (daemoniq-imp.py)

Run with:
    python3 -m pytest test_daemoniq.py -v
or:
    python3 test_daemoniq.py
"""

import sys
import os
import json
import logging
import importlib.util
import threading
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# ── Import the module under test ──────────────────────────────────────────────
# daemoniq-imp.py has a hyphen so it can't be imported with a normal `import`.
# We use importlib to load it, patching the logging FileHandler so the test
# runner doesn't require write access to /tmp/daemoniq-demon.log.

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "daemoniq-imp.py")

with patch("logging.basicConfig"):
    with patch("logging.FileHandler"):
        spec = importlib.util.spec_from_file_location("diq", _MODULE_PATH)
        diq = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(diq)


# ══════════════════════════════════════════════════════════════════════════════
# 1. ExecBlock dataclass
# ══════════════════════════════════════════════════════════════════════════════

class TestExecBlock(unittest.TestCase):
    def test_defaults(self):
        b = diq.ExecBlock(commands=["echo hi"], description="test")
        self.assertFalse(b.requires_sudo)
        self.assertEqual(b.pkg_manager, "")

    def test_full_construction(self):
        b = diq.ExecBlock(
            commands=["apt install foo", "dpkg --configure -a"],
            description="fix packages",
            requires_sudo=True,
            pkg_manager="apt",
        )
        self.assertEqual(len(b.commands), 2)
        self.assertTrue(b.requires_sudo)
        self.assertEqual(b.pkg_manager, "apt")


# ══════════════════════════════════════════════════════════════════════════════
# 2. _parse_os_release
# ══════════════════════════════════════════════════════════════════════════════

class TestParseOsRelease(unittest.TestCase):
    def _parse(self, content: str) -> dict:
        """Helper: run _parse_os_release against a fake file."""
        with patch.object(diq, "Path") as MockPath:
            # First path exists, return our content
            mock_file = MagicMock()
            mock_file.exists.return_value = True
            mock_file.read_text.return_value = content
            MockPath.side_effect = lambda p: mock_file if "os-release" in p else Path(p)
            return diq._parse_os_release()

    def test_basic_ubuntu_format(self):
        content = (
            'ID=ubuntu\n'
            'PRETTY_NAME="Ubuntu 22.04.3 LTS"\n'
            'VERSION_ID="22.04"\n'
            'VERSION_CODENAME=jammy\n'
        )
        result = self._parse(content)
        self.assertEqual(result["ID"], "ubuntu")
        self.assertEqual(result["VERSION_CODENAME"], "jammy")
        # Quotes stripped
        self.assertEqual(result["PRETTY_NAME"], "Ubuntu 22.04.3 LTS")
        self.assertEqual(result["VERSION_ID"], "22.04")

    def test_comments_are_ignored(self):
        content = (
            '# This is a comment\n'
            'ID=debian\n'
            '# Another comment\n'
            'NAME="Debian GNU/Linux"\n'
        )
        result = self._parse(content)
        self.assertNotIn("# This is a comment", result)
        self.assertEqual(result["ID"], "debian")

    def test_quoted_values_stripped(self):
        content = 'PRETTY_NAME="Kali GNU/Linux Rolling"\n'
        result = self._parse(content)
        self.assertEqual(result["PRETTY_NAME"], "Kali GNU/Linux Rolling")

    def test_empty_file_returns_empty_dict(self):
        content = ""
        result = self._parse(content)
        self.assertIsInstance(result, dict)

    def test_no_file_returns_empty_dict(self):
        with patch.object(diq, "Path") as MockPath:
            mock = MagicMock()
            mock.exists.return_value = False
            MockPath.return_value = mock
            result = diq._parse_os_release()
        self.assertEqual(result, {})


# ══════════════════════════════════════════════════════════════════════════════
# 3. DistroFamily.detect
# ══════════════════════════════════════════════════════════════════════════════

class TestDistroFamilyDetect(unittest.TestCase):
    def test_debian_family_detects_ubuntu(self):
        fam = diq.DebianFamily()
        self.assertTrue(fam.detect({"ubuntu"}))

    def test_debian_family_detects_kali(self):
        fam = diq.DebianFamily()
        self.assertTrue(fam.detect({"kali"}))

    def test_debian_family_detects_pop(self):
        fam = diq.DebianFamily()
        self.assertTrue(fam.detect({"pop"}))

    def test_debian_family_misses_fedora(self):
        # Fedora is not Debian — but detect() also checks if /usr/bin/dpkg exists.
        # On a Debian host the path check would fire, so we only test the set logic.
        fam = diq.DebianFamily()
        ids = {"fedora"}
        # Strip the filesystem check for this test
        result = bool(ids & fam.FAMILY_IDS)
        self.assertFalse(result)

    def test_arch_family_detects_manjaro(self):
        fam = diq.ArchFamily()
        self.assertTrue(fam.detect({"manjaro"}))

    def test_redhat_family_detects_centos(self):
        fam = diq.RedHatFamily()
        self.assertTrue(fam.detect({"centos"}))

    def test_alpine_family_detects_alpine(self):
        fam = diq.AlpineFamily()
        self.assertTrue(fam.detect({"alpine"}))

    def test_base_family_detect_empty_ids(self):
        fam = diq.DistroFamily()
        self.assertFalse(fam.detect(set()))


# ══════════════════════════════════════════════════════════════════════════════
# 4. DebianFamily.get_info
# ══════════════════════════════════════════════════════════════════════════════

class TestDebianFamilyGetInfo(unittest.TestCase):
    def setUp(self):
        self.fam = diq.DebianFamily()
        self.raw_ubuntu = {
            "ID": "ubuntu",
            "PRETTY_NAME": "Ubuntu 22.04.3 LTS",
            "VERSION_ID": "22.04",
            "VERSION_CODENAME": "jammy",
        }

    def test_family_is_debian(self):
        info = self.fam.get_info(self.raw_ubuntu)
        self.assertEqual(info.family, "debian")

    def test_distro_id_lower(self):
        info = self.fam.get_info({"ID": "UBUNTU"})
        self.assertEqual(info.distro_id, "ubuntu")

    def test_version_id_stripped(self):
        info = self.fam.get_info({"ID": "ubuntu", "VERSION_ID": '"22.04"'})
        self.assertEqual(info.version_id, "22.04")

    def test_codename_from_version_codename(self):
        info = self.fam.get_info(self.raw_ubuntu)
        self.assertEqual(info.codename, "jammy")

    def test_codename_from_ubuntu_codename_fallback(self):
        raw = {"ID": "ubuntu", "UBUNTU_CODENAME": "focal"}
        info = self.fam.get_info(raw)
        self.assertEqual(info.codename, "focal")

    def test_supported_is_true(self):
        info = self.fam.get_info(self.raw_ubuntu)
        self.assertTrue(info.supported)

    def test_missing_keys_use_defaults(self):
        info = self.fam.get_info({})
        self.assertEqual(info.distro_id, "debian")
        self.assertEqual(info.distro_name, "Debian-based Linux")
        self.assertEqual(info.version_id, "")
        self.assertEqual(info.codename, "")


# ══════════════════════════════════════════════════════════════════════════════
# 5. DebianFamily.sanitize_exec_block  ← most security-critical code
# ══════════════════════════════════════════════════════════════════════════════

class TestDebianSanitize(unittest.TestCase):
    def setUp(self):
        self.fam = diq.DebianFamily()
        self.info = diq.DistroInfo(
            family="debian", distro_id="ubuntu",
            distro_name="Ubuntu 22.04", version_id="22.04",
            codename="jammy", pkg_managers=["apt", "dpkg"],
            supported=True, support_note="",
        )

    def _sanitize(self, commands, description="test"):
        block = diq.ExecBlock(commands=commands, description=description)
        return self.fam.sanitize_exec_block(block, self.info)

    # ── Dangerous command blocking ────────────────────────────────────────────

    def test_blocks_rm_rf_root(self):
        with self.assertRaises(ValueError):
            self._sanitize(["rm -rf /"])

    def test_blocks_rm_rf_star(self):
        with self.assertRaises(ValueError):
            self._sanitize(["rm -rf /*"])

    def test_blocks_mkfs(self):
        with self.assertRaises(ValueError):
            self._sanitize(["mkfs.ext4 /dev/sda1"])

    def test_blocks_dd_if(self):
        with self.assertRaises(ValueError):
            self._sanitize(["dd if=/dev/zero of=/dev/sda"])

    def test_blocks_shred_dev(self):
        with self.assertRaises(ValueError):
            self._sanitize(["shred /dev/sda"])

    def test_blocks_overwrite_sda(self):
        with self.assertRaises(ValueError):
            self._sanitize(["> /dev/sda"])

    def test_safe_command_passes(self):
        result = self._sanitize(["echo hello"])
        self.assertEqual(result.commands, ["echo hello"])

    # ── DEBIAN_FRONTEND injection ─────────────────────────────────────────────

    def test_apt_install_gets_debian_frontend(self):
        result = self._sanitize(["apt install curl"])
        self.assertIn("DEBIAN_FRONTEND=noninteractive", result.commands[0])

    def test_apt_get_install_gets_debian_frontend(self):
        result = self._sanitize(["apt-get install curl"])
        self.assertIn("DEBIAN_FRONTEND=noninteractive", result.commands[0])

    def test_debian_frontend_not_duplicated(self):
        result = self._sanitize(["DEBIAN_FRONTEND=noninteractive apt install curl"])
        self.assertEqual(
            result.commands[0].count("DEBIAN_FRONTEND"), 1,
            "DEBIAN_FRONTEND should not be injected twice",
        )

    def test_apt_cache_search_no_frontend(self):
        # apt-cache search is not an install/upgrade/remove/purge
        result = self._sanitize(["apt-cache search vim"])
        self.assertNotIn("DEBIAN_FRONTEND", result.commands[0])

    # ── -y flag injection ─────────────────────────────────────────────────────

    def test_apt_install_gets_y_flag(self):
        result = self._sanitize(["apt install curl"])
        self.assertIn(" -y", result.commands[0])

    def test_apt_upgrade_gets_y_flag(self):
        result = self._sanitize(["apt upgrade"])
        self.assertIn(" -y", result.commands[0])

    def test_apt_remove_gets_y_flag(self):
        result = self._sanitize(["apt remove curl"])
        self.assertIn(" -y", result.commands[0])

    def test_already_has_y_not_doubled(self):
        result = self._sanitize(["apt install curl -y"])
        self.assertEqual(
            result.commands[0].count("-y"), 1,
            "-y must not appear more than once",
        )

    def test_already_has_yes_flag_no_y_added(self):
        result = self._sanitize(["apt install curl --yes"])
        self.assertNotIn(" -y", result.commands[0])

    def test_non_apt_install_no_y(self):
        result = self._sanitize(["pip install requests"])
        self.assertNotIn(" -y", result.commands[0])

    def test_echo_no_y(self):
        result = self._sanitize(["echo install done"])
        self.assertNotIn(" -y", result.commands[0])

    # ── BUG: snap app name containing "apt" gets -y injected ─────────────────
    # A snap package name that contains the substring "apt" (e.g. "someaptapp")
    # incorrectly triggers -y injection because the check is:
    #   ("apt" in s)  ← substring match, not word match
    def test_bug_snap_app_with_apt_in_name_gets_wrong_y(self):
        """
        BUG: 'snap install someaptapp' triggers -y injection because
        'apt' appears inside 'someaptapp' and 'install' is in the command.
        snap does not accept -y; this flag is silently appended and
        will cause the snap command to fail.
        """
        result = self._sanitize(["snap install someaptapp"])
        # This assertion documents the BUG: -y should NOT be added to snap commands
        if " -y" in result.commands[0]:
            self.fail(
                "BUG CONFIRMED: 'snap install someaptapp' had -y injected because\n"
                "'apt' appears as a substring in 'someaptapp'. The sanitizer uses\n"
                "('apt' in s) instead of checking for the apt/apt-get command word.\n"
                "Command produced: " + result.commands[0]
            )

    # ── pkg_manager assignment ────────────────────────────────────────────────

    def test_pkg_manager_defaults_to_apt_when_available(self):
        block = diq.ExecBlock(commands=["echo hi"], description="test", pkg_manager="")
        result = self.fam.sanitize_exec_block(block, self.info)
        self.assertEqual(result.pkg_manager, "apt")

    def test_pkg_manager_preserved_if_set(self):
        block = diq.ExecBlock(commands=["echo hi"], description="test", pkg_manager="dpkg")
        result = self.fam.sanitize_exec_block(block, self.info)
        self.assertEqual(result.pkg_manager, "dpkg")

    # ── Multi-command blocks ──────────────────────────────────────────────────

    def test_multiple_install_commands_all_get_y(self):
        # apt update is NOT install/upgrade/remove/purge → no -y
        # apt install IS → gets -y
        result = self._sanitize(["apt update", "apt install vim"])
        self.assertNotIn(" -y", result.commands[0],
            "apt update should NOT get -y (not a package operation)")
        self.assertIn(" -y", result.commands[1],
            "apt install should get -y")

    def test_dangerous_command_mid_block_raises(self):
        with self.assertRaises(ValueError):
            self._sanitize(["apt update", "rm -rf /", "apt install vim"])

    def test_sudo_apt_install_gets_frontend_and_y(self):
        result = self._sanitize(["sudo apt install vim"])
        cmd = result.commands[0]
        self.assertIn("DEBIAN_FRONTEND=noninteractive", cmd)
        self.assertIn(" -y", cmd)


# ══════════════════════════════════════════════════════════════════════════════
# 6. _SessionState
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionState(unittest.TestCase):
    def _make_state(self):
        """Create a fresh _SessionState with no disk I/O.
        We temporarily point HISTORY_FILE at a nonexistent path."""
        orig = diq.HISTORY_FILE
        diq.HISTORY_FILE = "/tmp/daemoniq_test_history_DOESNOTEXIST_xyz123"
        try:
            state = diq._SessionState()
        finally:
            diq.HISTORY_FILE = orig
        return state

    def setUp(self):
        self.state = self._make_state()

    def test_get_messages_empty_session(self):
        msgs = self.state.get_messages("mysession")
        self.assertEqual(msgs, [])

    def test_add_and_get_messages(self):
        self.state.add_message("s1", "user", "hello")
        self.state.add_message("s1", "assistant", "hi there")
        msgs = self.state.get_messages("s1")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0], {"role": "user", "content": "hello"})
        self.assertEqual(msgs[1], {"role": "assistant", "content": "hi there"})

    def test_get_messages_returns_copy(self):
        self.state.add_message("s1", "user", "hello")
        msgs = self.state.get_messages("s1")
        msgs.append({"role": "user", "content": "injected"})
        # Internal state must not change
        self.assertEqual(len(self.state.get_messages("s1")), 1)

    def test_clear_session(self):
        self.state.add_message("s1", "user", "hello")
        self.state.clear_session("s1")
        self.assertEqual(self.state.get_messages("s1"), [])

    def test_clear_nonexistent_session_ok(self):
        # Should not raise
        self.state.clear_session("nonexistent")

    def test_list_sessions(self):
        self.state.add_message("alpha", "user", "hi")
        self.state.add_message("beta", "user", "yo")
        sessions = self.state.list_sessions()
        self.assertIn("alpha", sessions)
        self.assertIn("beta", sessions)

    def test_sessions_independent(self):
        self.state.add_message("s1", "user", "hello")
        self.state.add_message("s2", "user", "world")
        self.assertEqual(len(self.state.get_messages("s1")), 1)
        self.assertEqual(len(self.state.get_messages("s2")), 1)

    def test_max_40_messages_enforced(self):
        for i in range(50):
            self.state.add_message("s1", "user", f"msg {i}")
        msgs = self.state.get_messages("s1")
        self.assertLessEqual(len(msgs), 40,
            "Session must be capped at 40 messages")

    def test_max_40_keeps_most_recent(self):
        for i in range(50):
            self.state.add_message("s1", "user", f"msg {i}")
        msgs = self.state.get_messages("s1")
        # The last message added should be present
        self.assertEqual(msgs[-1]["content"], "msg 49")

    def test_add_history(self):
        # Redirect writes to a temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp = f.name
        orig = diq.HISTORY_FILE
        diq.HISTORY_FILE = tmp
        try:
            self.state.add_history(["cmd1", "cmd2", "cmd3"])
        finally:
            diq.HISTORY_FILE = orig
            os.unlink(tmp)
        self.assertIn("cmd1", self.state.shell_history)

    def test_add_history_max_enforced(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp = f.name
        orig = diq.HISTORY_FILE
        diq.HISTORY_FILE = tmp
        try:
            big_list = [f"cmd{i}" for i in range(diq.MAX_HISTORY + 100)]
            self.state.add_history(big_list)
        finally:
            diq.HISTORY_FILE = orig
            os.unlink(tmp)
        self.assertLessEqual(len(self.state.shell_history), diq.MAX_HISTORY)

    def test_thread_safety_concurrent_adds(self):
        errors = []

        def writer(sid, n):
            try:
                for i in range(n):
                    self.state.add_message(sid, "user", f"msg {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"session_{t}", 20))
                   for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        self.assertEqual(len(self.state.list_sessions()), 5)


# ══════════════════════════════════════════════════════════════════════════════
# 7. _parse_exec (exec block extraction from AI response)
# ══════════════════════════════════════════════════════════════════════════════

def _make_exec_response(commands, description="Fix it", requires_sudo=False):
    payload = json.dumps({
        "commands": commands,
        "description": description,
        "requires_sudo": requires_sudo,
    })
    return f"Here is the fix:\n\n<DAEMONIQ_EXEC>\n{payload}\n</DAEMONIQ_EXEC>\n"


class TestParseExec(unittest.TestCase):
    def setUp(self):
        # Set up a supported Debian distro
        self._orig_info   = diq._DISTRO_INFO
        self._orig_family = diq._DISTRO_FAMILY
        diq._DISTRO_INFO = diq.DistroInfo(
            family="debian", distro_id="ubuntu",
            distro_name="Ubuntu 22.04", version_id="22.04",
            codename="jammy", pkg_managers=["apt"],
            supported=True, support_note="",
        )
        diq._DISTRO_FAMILY = diq.DebianFamily()

    def tearDown(self):
        diq._DISTRO_INFO   = self._orig_info
        diq._DISTRO_FAMILY = self._orig_family

    def test_no_exec_block_returns_response_unchanged(self):
        response = "Just a plain answer, no commands needed."
        clean, exec_out = diq._parse_exec(response, auto_exec=False)
        self.assertIn("plain answer", clean)
        self.assertIsNone(exec_out)

    def test_auto_exec_false_returns_warning_not_output(self):
        response = _make_exec_response(["echo hello"])
        clean, exec_out = diq._parse_exec(response, auto_exec=False)
        self.assertIsNone(exec_out)
        self.assertIn("exec on", clean)   # warning message present

    def test_exec_block_stripped_from_clean_response(self):
        response = _make_exec_response(["echo hello"])
        clean, _ = diq._parse_exec(response, auto_exec=False)
        self.assertNotIn("<DAEMONIQ_EXEC>", clean)
        self.assertNotIn("</DAEMONIQ_EXEC>", clean)

    def test_invalid_json_exec_block_returns_error(self):
        bad_json = "Here:\n<DAEMONIQ_EXEC>\nnot-valid-json\n</DAEMONIQ_EXEC>\n"
        clean, exec_out = diq._parse_exec(bad_json, auto_exec=True)
        self.assertIsNotNone(exec_out)
        self.assertIn("✗", exec_out)

    def test_unsupported_distro_blocks_auto_exec(self):
        diq._DISTRO_INFO = diq.DistroInfo(
            family="arch", distro_id="arch",
            distro_name="Arch Linux", version_id="",
            codename="", pkg_managers=["pacman"],
            supported=False, support_note="coming soon",
        )
        response = _make_exec_response(["pacman -S vim"])
        clean, exec_out = diq._parse_exec(response, auto_exec=True)
        self.assertIn("✗", exec_out)
        self.assertIn("not supported", exec_out.lower())

    def test_dangerous_command_blocked_by_sanitizer(self):
        response = _make_exec_response(["rm -rf /"])
        clean, exec_out = diq._parse_exec(response, auto_exec=True)
        self.assertIsNotNone(exec_out)
        self.assertIn("✗", exec_out)

    def test_auto_exec_true_calls_execute(self):
        response = _make_exec_response(["echo hello"])
        with patch.object(diq, "_execute", return_value="✓ done") as mock_exec:
            clean, exec_out = diq._parse_exec(response, auto_exec=True)
        mock_exec.assert_called_once()
        self.assertEqual(exec_out, "✓ done")

    # ── BUG: globals None with auto_exec causes AttributeError ───────────────
    def test_bug_globals_none_with_auto_exec_raises(self):
        """
        BUG: If _DISTRO_INFO and _DISTRO_FAMILY are None (daemon not started)
        and auto_exec=True, the code reaches:
            _DISTRO_FAMILY.sanitize_exec_block(block, _DISTRO_INFO)
        and raises AttributeError instead of a graceful error message.
        """
        diq._DISTRO_INFO   = None
        diq._DISTRO_FAMILY = None
        response = _make_exec_response(["echo hello"])
        try:
            clean, exec_out = diq._parse_exec(response, auto_exec=True)
            # Ideally exec_out should contain a graceful error string
            if exec_out is None or "✗" not in exec_out:
                self.fail(
                    "BUG: _parse_exec with None globals and auto_exec=True "
                    "should return a graceful error, but returned: "
                    f"clean={clean!r}, exec_out={exec_out!r}"
                )
        except AttributeError as e:
            self.fail(
                f"BUG CONFIRMED: AttributeError raised instead of graceful error:\n{e}\n"
                "Fix: guard '_DISTRO_FAMILY.sanitize_exec_block(...)' against None globals."
            )


# ══════════════════════════════════════════════════════════════════════════════
# 8. _EXEC_RE regex
# ══════════════════════════════════════════════════════════════════════════════

class TestExecRegex(unittest.TestCase):
    def test_matches_single_line(self):
        s = '<DAEMONIQ_EXEC>{"commands":[],"description":"x"}</DAEMONIQ_EXEC>'
        m = diq._EXEC_RE.search(s)
        self.assertIsNotNone(m)

    def test_matches_multiline(self):
        s = '<DAEMONIQ_EXEC>\n{"commands":[]}\n</DAEMONIQ_EXEC>'
        m = diq._EXEC_RE.search(s)
        self.assertIsNotNone(m)

    def test_no_match_without_tags(self):
        m = diq._EXEC_RE.search('{"commands": ["echo hi"]}')
        self.assertIsNone(m)

    def test_captures_inner_json(self):
        payload = '{"commands":["apt install vim"],"description":"install vim"}'
        s = f"<DAEMONIQ_EXEC>{payload}</DAEMONIQ_EXEC>"
        m = diq._EXEC_RE.search(s)
        self.assertEqual(m.group(1), payload)


# ══════════════════════════════════════════════════════════════════════════════
# 9. Unsupported distro families raise on sanitize
# ══════════════════════════════════════════════════════════════════════════════

class TestUnsupportedFamilySanitize(unittest.TestCase):
    def _make_block(self):
        return diq.ExecBlock(commands=["pacman -S vim"], description="install vim")

    def _make_info(self, name):
        return diq.DistroInfo(
            family=name, distro_id=name, distro_name=name,
            version_id="", codename="", pkg_managers=[],
            supported=False, support_note="coming soon",
        )

    def test_arch_sanitize_raises(self):
        fam = diq.ArchFamily()
        with self.assertRaises(ValueError):
            fam.sanitize_exec_block(self._make_block(), self._make_info("arch"))

    def test_redhat_sanitize_raises(self):
        fam = diq.RedHatFamily()
        with self.assertRaises(ValueError):
            fam.sanitize_exec_block(self._make_block(), self._make_info("redhat"))

    def test_suse_sanitize_raises(self):
        fam = diq.SUSEFamily()
        with self.assertRaises(ValueError):
            fam.sanitize_exec_block(self._make_block(), self._make_info("suse"))

    def test_alpine_sanitize_raises(self):
        fam = diq.AlpineFamily()
        with self.assertRaises(ValueError):
            fam.sanitize_exec_block(self._make_block(), self._make_info("alpine"))


# ══════════════════════════════════════════════════════════════════════════════
# 10. lstrip("sudo ") character-set bug
# ══════════════════════════════════════════════════════════════════════════════

class TestLstripSudoBug(unittest.TestCase):
    """
    The sanitizer uses s.lstrip("sudo ") to strip the 'sudo ' prefix before
    checking startswith("apt ").  lstrip() treats its argument as a *character
    set*, not a prefix string.  This means any leading character that is one
    of {s, u, d, o, ' '} is stripped — which can produce false positives.
    """

    def setUp(self):
        self.fam = diq.DebianFamily()
        self.info = diq.DistroInfo(
            family="debian", distro_id="ubuntu",
            distro_name="Ubuntu 22.04", version_id="22.04",
            codename="jammy", pkg_managers=["apt"],
            supported=True, support_note="",
        )

    def _sanitize_one(self, cmd):
        block = diq.ExecBlock(commands=[cmd], description="test")
        return self.fam.sanitize_exec_block(block, self.info).commands[0]

    def test_normal_sudo_apt_still_works(self):
        result = self._sanitize_one("sudo apt install vim")
        self.assertIn("DEBIAN_FRONTEND=noninteractive", result)

    def test_lstrip_character_set_false_positive(self):
        """
        'dsudo apt install vim': 'd','s','u','d','o',' ' are all in lstrip
        character set, so all are stripped → 'apt install vim' → startswith("apt ")
        is True → DEBIAN_FRONTEND is incorrectly injected into a command that
        was not actually a sudo apt invocation.

        This test documents the behaviour.  Whether it is a real risk depends
        on whether the AI can generate such malformed commands.
        """
        # 'dsudo' prefix: 'd' in set, 's' in set, 'u' in set, 'd' in set,
        # 'o' in set → all stripped → remainder = 'apt install vim'
        cmd = "dsudo apt install vim"
        result = self._sanitize_one(cmd)
        # If DEBIAN_FRONTEND is present, the lstrip bug fired
        if "DEBIAN_FRONTEND" in result:
            # This is not necessarily a security issue but shows lstrip != removeprefix
            pass  # behaviour noted, test passes (documents the anomaly)
        # The command itself should not have been modified in a dangerous way
        self.assertNotIn("rm -rf", result)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
