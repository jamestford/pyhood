"""install.sh, run for real against a stand-in uv and a stand-in pyhood.

Nothing here touches the network or the real home folder. Each test gets an
empty HOME and a PATH holding a fake `uv` that builds a fake install, so what
is tested is the script's own decisions: what it runs, in what order, and
what it tells the user.

The script is fed to `sh` on standard input, as `curl ... | sh` does. That
matters: the script cannot read answers from standard input, and has to find
the terminal another way.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="install.sh is for macOS and Linux")

SCRIPT = Path(__file__).resolve().parent.parent / "install.sh"

FAKE_UV = """#!/bin/sh
echo "uv $*" >> "$HOME/calls.log"
case "$1" in
    venv)
        for folder; do :; done
        mkdir -p "$folder/bin"
        : > "$folder/pyvenv.cfg"
        printf '#!/bin/sh\\n' > "$folder/bin/python"
        chmod +x "$folder/bin/python"
        ;;
    pip)
        while [ $# -gt 0 ]; do
            if [ "$1" = --python ]; then python=$2; fi
            shift
        done
        bin=$(dirname "$python")
        cp "$FAKES/pyhood" "$bin/pyhood"
        chmod +x "$bin/pyhood"
        : > "$(dirname "$bin")/AGENTS.md"
        ;;
esac
"""

FAKE_PYHOOD = """#!/bin/sh
echo "pyhood $*" >> "$HOME/calls.log"
case "$1 ${2:-}" in
    "version ") echo "pyhood 9.9.9" ;;
    "authorize ")
        read -r who
        echo "typed $who" >> "$HOME/calls.log"
        [ "$who" != refuse ] && : > "$HOME/logged-in"
        ;;
    "verify ")
        if [ -f "$HOME/logged-in" ] && [ ! -f "$HOME/verify-fails" ]; then
            echo "Session works."
        else
            echo "Not authenticated"
            exit 1
        fi
        ;;
esac
"""

# Stands in for uv's own installer, fetched with curl.
FAKE_CURL = """#!/bin/sh
echo "curl $*" >> "$HOME/calls.log"
echo 'mkdir -p "$HOME/.local/bin" && cp "$FAKES/uv" "$HOME/.local/bin/uv"'
"""


# Runs `sh` with the script on standard input and a new terminal as its
# controlling terminal, types into that terminal, and prints the exit code.
AT_TERMINAL = """
import os, pty, select, signal, sys, time

script, out_path, err_path, typed = sys.argv[1:5]
pid, terminal = pty.fork()
if pid == 0:
    # Hold the terminal open: on macOS it goes away with its last user.
    os.set_inheritable(os.dup(0), True)
    os.dup2(os.open(script, os.O_RDONLY), 0)
    os.dup2(os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC), 1)
    os.dup2(os.open(err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC), 2)
    os.execve("/bin/sh", ["sh"], dict(os.environ))

os.write(terminal, typed.encode())
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    # Read what the terminal echoes. Unread, it stops the script from
    # exiting on macOS.
    if select.select([terminal], [], [], 0.02)[0]:
        try:
            os.read(terminal, 4096)
        except OSError:
            pass
    done, status = os.waitpid(pid, os.WNOHANG)
    if done:
        print(os.waitstatus_to_exitcode(status))
        break
else:
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    sys.exit("install.sh did not finish at the terminal")
"""


class Machine:
    """An empty home folder and a PATH with only what a test puts on it."""

    def __init__(self, root: Path, uv: bool = True):
        self.home = root / "home"
        self.home.mkdir()
        self.fakes = root / "fakes"
        self.fakes.mkdir()
        self.path_dir = root / "path"
        self.path_dir.mkdir()
        for name, text in (("uv", FAKE_UV), ("pyhood", FAKE_PYHOOD), ("curl", FAKE_CURL)):
            self._write(self.fakes / name, text)
        if uv:
            self._write(self.path_dir / "uv", FAKE_UV)
        self.local_bin_on_path = True
        self.extra_env: dict[str, str] = {}

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.write_text(text)
        path.chmod(0o755)

    def add_curl(self) -> None:
        self._write(self.path_dir / "curl", FAKE_CURL)

    @property
    def env(self) -> dict[str, str]:
        path = [str(self.path_dir), "/usr/bin", "/bin"]
        if self.local_bin_on_path:
            path.insert(0, str(self.home / ".local" / "bin"))
        return {
            "HOME": str(self.home),
            "PATH": ":".join(path),
            "FAKES": str(self.fakes),
            **self.extra_env,
        }

    @property
    def calls(self) -> list[str]:
        log = self.home / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    @property
    def install(self) -> Path:
        return self.home / "pyhood"

    def run(self, script: str | None = None) -> subprocess.CompletedProcess:
        """Run the script with no terminal, as an agent or CI would."""
        return subprocess.run(
            ["sh"],
            input=script if script is not None else SCRIPT.read_text(),
            capture_output=True,
            text=True,
            env=self.env,
            start_new_session=True,
            timeout=30,
        )

    def run_at_terminal(self, typed: str) -> subprocess.CompletedProcess:
        """Run the script with a terminal attached, and `typed` typed into it.

        The script arrives on standard input, as under `curl ... | sh`, and
        the terminal is reachable only as /dev/tty.
        """
        out_path, err_path = self.home.parent / "out", self.home.parent / "err"
        # In a Python of its own: forking a terminal from inside pytest, which
        # has threads, is not safe.
        driver = subprocess.run(
            [sys.executable, "-c", AT_TERMINAL, str(SCRIPT), str(out_path), str(err_path), typed],
            env=self.env, capture_output=True, text=True, timeout=60,
        )
        assert driver.stdout.strip().lstrip("-").isdigit(), driver.stdout + driver.stderr
        return subprocess.CompletedProcess(
            ["sh"], int(driver.stdout), out_path.read_text(), err_path.read_text(),
        )


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


@pytest.fixture
def no_uv(tmp_path):
    return Machine(tmp_path, uv=False)


# ── A first install ──────────────────────────────────────────────────


class TestFirstInstall:
    def test_installs_into_the_pyhood_folder(self, machine):
        result = machine.run()

        assert result.returncode == 0, result.stderr
        assert f"uv venv --managed-python --python 3.14 {machine.install}" in machine.calls
        assert f"uv pip install --python {machine.install}/bin/python pyhood" in machine.calls
        assert (machine.install / "bin" / "pyhood").exists()

    def test_creates_the_folder_before_installing_into_it(self, machine):
        machine.run()

        uv_calls = [c for c in machine.calls if c.startswith("uv ")]
        assert [c.split()[1] for c in uv_calls] == ["venv", "pip"]

    def test_says_what_it_installed_and_where(self, machine):
        result = machine.run()

        assert "Installing pyhood into ~/pyhood." in result.stdout
        assert "pyhood 9.9.9 is installed in ~/pyhood." in result.stdout

    def test_ends_by_pointing_at_the_agent(self, machine):
        result = machine.run()

        assert "open your AI agent in the pyhood folder" in result.stdout
        assert "    cd ~/pyhood" in result.stdout

    def test_installs_what_it_is_told_to(self, machine):
        machine.extra_env["PYHOOD_INSTALL_SPEC"] = "/tmp/pyhood-1.0-py3-none-any.whl"

        machine.run()

        assert any(c.endswith("/tmp/pyhood-1.0-py3-none-any.whl") for c in machine.calls)

    def test_works_run_from_a_file_too(self, machine):
        result = subprocess.run(
            ["sh", str(SCRIPT)], capture_output=True, text=True, env=machine.env,
            start_new_session=True, timeout=30,
        )

        assert result.returncode == 0, result.stderr
        assert (machine.install / "bin" / "pyhood").exists()


# ── Without a terminal the login is left to the user ─────────────────


class TestWithoutATerminal:
    def test_does_not_try_to_log_in(self, machine):
        machine.run()

        assert "pyhood authorize" not in machine.calls

    def test_tells_the_user_to_log_in_themselves(self, machine):
        result = machine.run()

        assert "It is not authorized yet." in result.stdout
        assert "If you are a person, authorize it yourself, in your own terminal." in result.stdout
        assert "    pyhood authorize\n" in result.stdout
        assert "    pyhood verify" in result.stdout

    def test_tells_an_agent_to_open_the_login_window(self, machine):
        result = machine.run()

        assert (
            "If you are an AI agent, open the authorization window on the user's screen:"
            in result.stdout
        )
        assert "    pyhood authorize --window" in result.stdout

    def test_does_not_claim_the_login_works(self, machine):
        result = machine.run()

        assert "and it is authorized" not in result.stdout

    def test_a_login_saved_earlier_is_checked_and_reported(self, machine):
        (machine.home / "logged-in").touch()

        result = machine.run()

        assert "pyhood authorize" not in machine.calls
        assert "pyhood 9.9.9 is installed in ~/pyhood, and it is authorized." in result.stdout
        assert "not authorized yet" not in result.stdout

    def test_the_check_prints_nothing_of_its_own(self, machine):
        (machine.home / "logged-in").touch()

        result = machine.run()

        assert "Session works." not in result.stdout


# ── With a terminal it logs in and checks the login ──────────────────


class TestAtATerminal:
    def test_login_reads_from_the_terminal_not_the_script(self, machine):
        result = machine.run_at_terminal("someone\n")

        assert result.returncode == 0, result.stderr
        assert "typed someone" in machine.calls

    def test_checks_the_login_after_making_it(self, machine):
        machine.run_at_terminal("someone\n")

        calls = machine.calls
        assert calls.index("pyhood authorize") < calls.index("pyhood verify")

    def test_says_the_login_works(self, machine):
        result = machine.run_at_terminal("someone\n")

        assert "pyhood 9.9.9 is installed in ~/pyhood, and it is authorized." in result.stdout
        assert "not authorized yet" not in result.stdout

    def test_a_login_that_fails_stops_the_script(self, machine):
        result = machine.run_at_terminal("refuse\n")

        assert result.returncode == 1
        assert "pyhood is installed, but it is not authorized yet." in result.stdout
        assert "    pyhood authorize" in result.stdout
        assert "pyhood verify" not in machine.calls
        assert "and it is authorized" not in result.stdout

    def test_a_check_that_fails_stops_the_script(self, machine):
        (machine.home / "verify-fails").touch()

        result = machine.run_at_terminal("someone\n")

        assert result.returncode == 1
        assert "the check did not pass" in result.stdout
        assert "and it is authorized" not in result.stdout


# ── Running it again upgrades ────────────────────────────────────────


class TestAlreadyInstalled:
    def test_upgrades_and_does_not_rebuild_the_folder(self, machine):
        machine.run()
        (machine.home / "calls.log").unlink()

        result = machine.run()

        assert result.returncode == 0, result.stderr
        assert "pyhood 9.9.9 is already installed in ~/pyhood. Upgrading it." in result.stdout
        uv_calls = [c for c in machine.calls if c.startswith("uv ")]
        python = machine.install / "bin" / "python"
        assert uv_calls == [f"uv pip install --python {python} --upgrade pyhood"]

    def test_finishes_a_folder_made_but_never_installed_into(self, machine):
        (machine.install / "bin").mkdir(parents=True)
        (machine.install / "pyvenv.cfg").touch()

        result = machine.run()

        assert result.returncode == 0, result.stderr
        uv_calls = [c for c in machine.calls if c.startswith("uv ")]
        assert [c.split()[1] for c in uv_calls] == ["pip"]

    def test_refuses_a_folder_that_is_something_else(self, machine):
        machine.install.mkdir()
        (machine.install / "notes.txt").write_text("mine")

        result = machine.run()

        assert result.returncode == 1
        assert "~/pyhood already exists and is not a pyhood install." in result.stderr
        assert machine.calls == []
        assert (machine.install / "notes.txt").read_text() == "mine"

    def test_refuses_a_file_of_that_name(self, machine):
        machine.install.write_text("mine")

        result = machine.run()

        assert result.returncode == 1
        assert machine.calls == []

    def test_uses_an_empty_folder(self, machine):
        machine.install.mkdir()

        result = machine.run()

        assert result.returncode == 0, result.stderr


# ── The link that makes `pyhood` work anywhere ───────────────────────


class TestTheLink:
    def test_links_the_command_into_local_bin(self, machine):
        machine.run()

        link = machine.home / ".local" / "bin" / "pyhood"
        assert link.is_symlink()
        assert os.readlink(link) == str(machine.install / "bin" / "pyhood")

    def test_names_the_command_by_its_short_name_when_it_resolves(self, machine):
        result = machine.run()

        assert "    pyhood authorize" in result.stdout
        assert "add ~/.local/bin to your PATH" not in result.stdout

    def test_says_so_when_local_bin_is_not_on_the_path(self, machine):
        machine.local_bin_on_path = False

        result = machine.run()

        assert "add ~/.local/bin to your PATH" in result.stdout
        assert "    ~/pyhood/bin/pyhood authorize" in result.stdout

    def test_leaves_a_real_file_alone(self, machine):
        local_bin = machine.home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        (local_bin / "pyhood").write_text("something else")

        result = machine.run()

        assert result.returncode == 0, result.stderr
        assert (local_bin / "pyhood").read_text() == "something else"
        assert "Left ~/.local/bin/pyhood alone" in result.stdout
        assert "    ~/pyhood/bin/pyhood authorize" in result.stdout

    def test_leaves_a_link_to_another_pyhood_alone(self, machine):
        local_bin = machine.home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        (local_bin / "pyhood").symlink_to("/somewhere/else/pyhood")

        result = machine.run()

        assert os.readlink(local_bin / "pyhood") == "/somewhere/else/pyhood"
        assert "it links to another pyhood" in result.stdout

    def test_running_again_keeps_its_own_link(self, machine):
        machine.run()

        result = machine.run()

        assert result.returncode == 0, result.stderr
        assert "Left" not in result.stdout

    def test_full_name_when_another_pyhood_comes_first(self, machine):
        machine._write(machine.path_dir / "pyhood", "#!/bin/sh\n")
        machine.local_bin_on_path = False
        env_path = f"{machine.path_dir}:{machine.home}/.local/bin:/usr/bin:/bin"
        machine.extra_env["PATH"] = env_path

        result = machine.run()

        assert "Another pyhood comes first on your PATH" in result.stdout
        assert "    ~/pyhood/bin/pyhood authorize" in result.stdout


# ── uv is missing ────────────────────────────────────────────────────


class TestWithoutUv:
    def test_without_a_terminal_it_stops_and_installs_nothing(self, no_uv):
        result = no_uv.run()

        assert result.returncode == 1
        assert "uv is not on this computer." in result.stdout
        assert "Install uv first" in result.stderr
        assert "Nothing was installed." in result.stderr
        assert not no_uv.install.exists()
        assert no_uv.calls == []

    def test_asks_before_installing_uv(self, no_uv):
        no_uv.add_curl()

        result = no_uv.run_at_terminal("n\n")

        assert result.returncode == 1
        assert "Install uv now? [y/N]" in result.stdout
        assert "Nothing was installed." in result.stderr
        assert no_uv.calls == []
        assert not no_uv.install.exists()

    def test_an_empty_answer_means_no(self, no_uv):
        no_uv.add_curl()

        result = no_uv.run_at_terminal("\n")

        assert result.returncode == 1
        assert no_uv.calls == []

    def test_yes_installs_uv_then_pyhood(self, no_uv):
        no_uv.add_curl()

        result = no_uv.run_at_terminal("y\nsomeone\n")

        assert result.returncode == 0, result.stderr
        calls = no_uv.calls
        assert calls[0] == "curl -LsSf https://astral.sh/uv/install.sh"
        assert f"uv venv --managed-python --python 3.14 {no_uv.install}" in calls
        assert "typed someone" in calls

    def test_finds_a_uv_that_is_installed_but_not_on_the_path(self, no_uv):
        local_bin = no_uv.home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        no_uv._write(local_bin / "uv", FAKE_UV)
        no_uv.local_bin_on_path = False

        result = no_uv.run()

        assert result.returncode == 0, result.stderr
        assert "uv is not on this computer." not in result.stdout


# ── A download that is cut off ───────────────────────────────────────


class TestCutOffDownload:
    @pytest.mark.parametrize("fraction", [0.25, 0.5, 0.75, 0.97])
    def test_a_partial_script_runs_nothing(self, machine, fraction):
        text = SCRIPT.read_text()
        partial = text[: int(len(text) * fraction)]

        machine.run(partial)

        assert machine.calls == []
        assert not machine.install.exists()

    def test_the_last_line_is_the_only_call(self):
        lines = [line for line in SCRIPT.read_text().splitlines() if line.strip()]

        assert lines[-1] == 'main "$@"'
        top_level = [
            line for line in lines
            if not line.startswith((" ", "#", "}")) and not line.endswith("() {")
        ]
        assert [line for line in top_level if "=" not in line and line != 'main "$@"'] == [
            "set -eu",
        ]


def test_script_never_uses_sudo():
    code = [
        line for line in SCRIPT.read_text().splitlines()
        if not line.lstrip().startswith("#")
    ]

    assert not any("sudo" in line for line in code)


@pytest.mark.skipif(sys.platform == "win32", reason="needs sh")
def test_script_is_valid_posix_shell():
    result = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
