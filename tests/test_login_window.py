"""`pyhood authorize --window`: a window for the user to log in, opened by an agent."""

from __future__ import annotations

import os
import stat
import subprocess
import sys

import pytest

from pyhood import login_window, onboarding


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point the credential folder at a temp directory."""
    monkeypatch.setattr("pyhood.auth.DEFAULT_TOKEN_DIR", tmp_path)
    return tmp_path


class Recorder:
    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        self.lines.append(str(line))

    @property
    def text(self):
        return "\n".join(self.lines)


class Clock:
    """Time that moves only when something sleeps."""

    def __init__(self):
        self.now = 0.0
        self.on_sleep = None

    def sleep(self, seconds):
        self.now += seconds
        if self.on_sleep:
            self.on_sleep(self.now)

    def __call__(self):
        return self.now


class Opener:
    def __init__(self, works=True):
        self.works = works
        self.opened = []

    def __call__(self, script):
        self.opened.append(script)
        return self.works


def run(home, opener, clock=None, logged_in=False, wait=5, wall=lambda: 1000.0):
    clock = clock or Clock()
    out = Recorder()
    code = login_window.login_in_window(
        wait=wait, out=out, opener=opener, saved_login_works=lambda: logged_in,
        sleep=clock.sleep, clock=clock, now=wall,
    )
    return code, out.text


def finish_after(home, seconds, code="0"):
    """A user who finishes the login in the window after `seconds`."""
    def on_sleep(now):
        if now >= seconds:
            (home / "login-window" / "status").write_text(f"{code}\n")
    return on_sleep


# ── Already logged in ────────────────────────────────────────────────


class TestAlreadyLoggedIn:
    def test_opens_no_window(self, home):
        opener = Opener()

        code, text = run(home, opener, logged_in=True)

        assert code == 0
        assert opener.opened == []
        assert "pyhood is already authorized. No window was needed." in text

    def test_clears_what_an_earlier_run_left(self, home):
        folder = home / "login-window"
        folder.mkdir()
        (folder / "login.command").write_text("old")
        (folder / "status").write_text("0")

        run(home, Opener(), logged_in=True)

        assert list(folder.iterdir()) == []


# ── Opening the window ───────────────────────────────────────────────


class TestOpening:
    def test_opens_a_window_and_tells_the_agent_what_to_say(self, home):
        opener = Opener()

        _, text = run(home, opener)

        assert opener.opened == [home / "login-window" / "login.command"]
        assert (
            'A terminal window titled "pyhood Authorization" has opened on the user\'s screen.'
            in text
        )
        assert "type your Robinhood username and password in that window" in text
        assert "then approve the request in the Robinhood app on your phone." in text
        assert "Never ask for, read or type their password." in text

    def test_the_script_and_its_folder_are_the_owners_alone(self, home):
        run(home, Opener())

        folder = home / "login-window"
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
        assert stat.S_IMODE((folder / "login.command").stat().st_mode) == 0o700

    def test_no_window_falls_back_to_the_user_running_it(self, home):
        code, text = run(home, Opener(works=False))

        assert code == 2
        assert "Could not open a terminal window here." in text
        assert "    pyhood authorize" in text
        assert "--window" not in text
        assert "Never ask for, read or type their password." in text
        assert not (home / "login-window" / "login.command").exists()

    def test_no_window_does_not_wait(self, home):
        clock = Clock()

        run(home, Opener(works=False), clock=clock)

        assert clock.now == 0


# ── Waiting for the user ─────────────────────────────────────────────


class TestWaiting:
    def test_returns_when_the_user_finishes(self, home):
        clock = Clock()
        clock.on_sleep = finish_after(home, 2)

        code, text = run(home, Opener(), clock=clock, wait=60)

        assert code == 0
        assert "Authorized." in text
        assert "Check it with: pyhood verify" in text
        assert clock.now < 5

    def test_cleans_up_after_the_user_finishes(self, home):
        clock = Clock()
        clock.on_sleep = finish_after(home, 1)

        run(home, Opener(), clock=clock)

        assert list((home / "login-window").iterdir()) == []

    def test_a_login_that_failed_is_reported(self, home):
        clock = Clock()
        clock.on_sleep = finish_after(home, 1, code="1")

        code, text = run(home, Opener(), clock=clock)

        assert code == 1
        assert "The authorization in the window did not finish." in text
        assert "pyhood authorize --window" in text
        assert "Authorized." not in text

    def test_a_closed_window_is_reported(self, home):
        clock = Clock()
        clock.on_sleep = finish_after(home, 1, code="130")

        code, _ = run(home, Opener(), clock=clock)

        assert code == 1

    def test_a_result_it_cannot_read_is_not_a_login(self, home):
        clock = Clock()
        clock.on_sleep = finish_after(home, 1, code="???")

        code, _ = run(home, Opener(), clock=clock)

        assert code == 1

    def test_a_result_half_written_is_waited_for(self, home):
        clock = Clock()

        def on_sleep(now):
            status = home / "login-window" / "status"
            status.write_text("" if now < 2 else "0\n")

        clock.on_sleep = on_sleep

        code, _ = run(home, Opener(), clock=clock)

        assert code == 0

    def test_gives_up_waiting_and_says_to_run_it_again(self, home):
        clock = Clock()

        code, text = run(home, Opener(), clock=clock, wait=5)

        assert code == 3
        assert 5 <= clock.now < 6
        assert "The user has not finished yet." in text
        assert "It will not open a second window:" in text
        assert "    pyhood authorize --window" in text

    def test_says_how_long_it_waits(self, home):
        _, text = run(home, Opener(), wait=90)

        assert "Waiting up to 90 seconds" in text


# ── Run again while the window is open ───────────────────────────────


class TestRunAgain:
    def test_does_not_open_a_second_window(self, home):
        opener = Opener()
        run(home, opener)

        code, text = run(home, opener, wall=lambda: os.path.getmtime(
            home / "login-window" / "login.command") + 30)

        assert len(opener.opened) == 1
        assert 'The "pyhood Authorization" window is already open' in text
        assert code == 3

    def test_picks_up_a_login_finished_in_the_first_window(self, home):
        opener = Opener()
        run(home, opener)
        clock = Clock()
        clock.on_sleep = finish_after(home, 1)

        code, _ = run(home, opener, clock=clock, wall=lambda: os.path.getmtime(
            home / "login-window" / "login.command") + 30)

        assert code == 0
        assert len(opener.opened) == 1

    def test_a_window_left_long_ago_is_opened_again(self, home):
        opener = Opener()
        run(home, opener)
        much_later = os.path.getmtime(home / "login-window" / "login.command") + 16 * 60

        run(home, opener, wall=lambda: much_later)

        assert len(opener.opened) == 2

    def test_a_login_that_failed_meanwhile_is_reported_not_reopened(self, home):
        """A window the user closed should not pop back up by itself."""
        opener = Opener()
        run(home, opener)
        soon = os.path.getmtime(home / "login-window" / "login.command") + 30
        (home / "login-window" / "status").write_text("130\n")

        code, text = run(home, opener, wall=lambda: soon)

        assert code == 1
        assert len(opener.opened) == 1
        assert "The authorization in the window did not finish." in text
        assert "already open" not in text

    def test_after_a_failure_is_reported_the_next_run_opens_a_window(self, home):
        opener = Opener()
        run(home, opener)
        (home / "login-window" / "status").write_text("1\n")
        run(home, opener)

        run(home, opener)

        assert len(opener.opened) == 2


# ── The script the window runs ───────────────────────────────────────


@pytest.mark.skipif(os.name == "nt", reason="the window script is a shell script")
class TestScript:
    def run_script(self, tmp_path, monkeypatch, login):
        monkeypatch.setattr(login_window, "_login_command", lambda: ["sh", "-c", login])
        status = tmp_path / "status"
        script = tmp_path / "login.command"
        script.write_text(login_window.script_text(status))
        done = subprocess.run(
            ["sh", str(script)], capture_output=True, text=True, timeout=20,
            env={"PATH": "/usr/bin:/bin", "TERM": "dumb"},
        )
        return status, done

    def test_is_valid_shell(self, tmp_path):
        script = tmp_path / "login.command"
        script.write_text(login_window.script_text(tmp_path / "it's a status"))

        done = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)

        assert done.returncode == 0, done.stderr

    def test_writes_the_logins_exit_code(self, tmp_path, monkeypatch):
        status, done = self.run_script(tmp_path, monkeypatch, "exit 0")

        assert status.read_text().strip() == "0"

    def test_writes_a_failure(self, tmp_path, monkeypatch):
        status, done = self.run_script(tmp_path, monkeypatch, "exit 1")

        assert status.read_text().strip() == "1"

    def test_tells_the_login_it_is_in_the_window(self, tmp_path, monkeypatch):
        _, done = self.run_script(
            tmp_path, monkeypatch, f'echo "in window: ${onboarding.IN_WINDOW_VARIABLE}"',
        )

        assert "in window: 1" in done.stdout

    def test_titles_the_window(self, tmp_path):
        text = login_window.script_text(tmp_path / "status")

        assert "\\033]0;pyhood Authorization\\007" in text

    def test_adds_no_words_of_its_own(self, tmp_path, monkeypatch):
        """What the user reads comes from the login, in one voice."""
        _, done = self.run_script(tmp_path, monkeypatch, "exit 0")

        printable = done.stdout.split("\x07")[-1].strip()
        assert printable == ""

    def test_the_login_saves_where_the_waiting_command_looks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(login_window.Path, "home", lambda: tmp_path / "their home")

        status, done = self.run_script(tmp_path, monkeypatch, 'echo "home is $HOME"')

        assert f"home is {tmp_path / 'their home'}" in done.stdout

    def test_runs_the_login_this_pyhood_is_installed_with(self, tmp_path, monkeypatch):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "pyhood").write_text("")
        monkeypatch.setattr(sys, "executable", str(bin_dir / "python"))

        assert login_window._login_command() == [str(bin_dir / "pyhood"), "authorize"]

    def test_falls_back_to_the_module(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))

        assert login_window._login_command() == [
            str(tmp_path / "python"), "-m", "pyhood", "authorize",
        ]


# ── Which program opens the window ───────────────────────────────────


class TestWindowCommands:
    def test_macos_opens_the_script_file(self, tmp_path):
        script = tmp_path / "login.command"

        assert login_window.window_commands(script, "darwin", {}) == [["open", str(script)]]

    def test_linux_tries_the_usual_terminal_programs(self, tmp_path):
        script = tmp_path / "login.command"

        commands = login_window.window_commands(script, "linux", {"DISPLAY": ":0"})

        assert [c[0] for c in commands] == [
            "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm",
        ]
        assert all(c[-2:] == ["sh", str(script)] for c in commands)

    def test_linux_on_wayland(self, tmp_path):
        assert login_window.window_commands(tmp_path / "s", "linux", {"WAYLAND_DISPLAY": "w"})

    def test_linux_with_no_screen(self, tmp_path):
        assert login_window.window_commands(tmp_path / "s", "linux", {}) == []

    @pytest.mark.parametrize("variable", ["SSH_CONNECTION", "SSH_TTY"])
    def test_not_over_ssh(self, tmp_path, variable):
        environ = {variable: "x", "DISPLAY": ":0"}

        assert login_window.window_commands(tmp_path / "s", "darwin", environ) == []
        assert login_window.window_commands(tmp_path / "s", "linux", environ) == []

    def test_windows_is_left_to_the_user(self, tmp_path):
        assert login_window.window_commands(tmp_path / "s", "win32", {}) == []


class TestOpenWindow:
    def test_macos_reports_whether_open_worked(self, tmp_path, monkeypatch):
        monkeypatch.setattr(login_window.shutil, "which", lambda name: f"/usr/bin/{name}")
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(login_window.subprocess, "run", fake_run)

        assert login_window.open_window(tmp_path / "s", "darwin", {}) is True
        assert calls == [["open", str(tmp_path / "s")]]

    def test_macos_open_failing_means_no_window(self, tmp_path, monkeypatch):
        monkeypatch.setattr(login_window.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(
            login_window.subprocess, "run",
            lambda command, **kwargs: subprocess.CompletedProcess(command, 1),
        )

        assert login_window.open_window(tmp_path / "s", "darwin", {}) is False

    def test_linux_uses_the_first_terminal_program_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            login_window.shutil, "which",
            lambda name: "/usr/bin/konsole" if name == "konsole" else None,
        )
        started = []
        monkeypatch.setattr(
            login_window.subprocess, "Popen",
            lambda command, **kwargs: started.append(command),
        )

        assert login_window.open_window(tmp_path / "s", "linux", {"DISPLAY": ":0"}) is True
        assert [c[0] for c in started] == ["konsole"]

    def test_linux_with_no_terminal_program(self, tmp_path, monkeypatch):
        monkeypatch.setattr(login_window.shutil, "which", lambda name: None)

        assert login_window.open_window(tmp_path / "s", "linux", {"DISPLAY": ":0"}) is False

    def test_a_program_that_will_not_start_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(login_window.shutil, "which", lambda name: f"/usr/bin/{name}")
        started = []

        def fake_popen(command, **kwargs):
            if command[0] == "x-terminal-emulator":
                raise OSError("broken link")
            started.append(command[0])

        monkeypatch.setattr(login_window.subprocess, "Popen", fake_popen)

        assert login_window.open_window(tmp_path / "s", "linux", {"DISPLAY": ":0"}) is True
        assert started == ["gnome-terminal"]


# ── The command line ─────────────────────────────────────────────────


class TestCommandLine:
    @pytest.mark.parametrize("command", [["authorize"], ["setup", "login"]])
    def test_window_routes_to_the_window(self, monkeypatch, command):
        seen = {}

        def fake(wait, program):
            seen.update(wait=wait, program=program)
            return 0

        monkeypatch.setattr(login_window, "login_in_window", fake)

        assert onboarding.main([*command, "--window"]) == 0
        assert seen["wait"] == login_window.DEFAULT_WAIT

    def test_wait_sets_how_long(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            login_window, "login_in_window",
            lambda wait, program: seen.update(wait=wait) or 3,
        )

        assert onboarding.main(["authorize", "--window", "--wait", "20"]) == 3
        assert seen["wait"] == 20

    def test_window_only_goes_with_login(self, monkeypatch):
        def never(**kwargs):
            raise AssertionError("setup crypto must not run")

        monkeypatch.setattr(onboarding, "setup_crypto", never)

        with pytest.raises(SystemExit):
            onboarding.main(["setup", "crypto", "--window"])

    @pytest.mark.parametrize("command", [["authorize"], ["setup", "login"]])
    def test_wait_needs_window(self, command):
        with pytest.raises(SystemExit):
            onboarding.main([*command, "--wait", "20"])

    def test_plain_login_is_unchanged(self, monkeypatch):
        monkeypatch.setattr(onboarding, "setup_login", lambda: 0)

        assert onboarding.main(["setup", "login"]) == 0


class TestLoginWithNoTerminal:
    def test_points_an_agent_at_the_window(self, home, monkeypatch):
        monkeypatch.setattr(onboarding, "_has_terminal", lambda: False)
        out = Recorder()

        code = onboarding.setup_login(out=out)

        assert code == 1
        assert "There is no terminal here to type a password into." in out.text
        assert "An AI agent can open an authorization window on the user's screen" in out.text
        assert "authorize --window" in out.text
        assert "Robinhood email" not in out.text

    def test_with_a_terminal_it_asks_as_before(self, home, monkeypatch):
        monkeypatch.setattr(onboarding, "_has_terminal", lambda: True)
        asked = []

        def cancel(question):
            asked.append(question)
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", cancel)
        out = Recorder()

        code = onboarding.setup_login(prompt=cancel, out=out)

        assert code == 1
        assert asked == ["Robinhood email or username: "]
