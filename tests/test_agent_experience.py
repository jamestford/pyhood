"""What an AI agent meets when it picks pyhood up cold.

These come from watching a local model try to use pyhood with no help. It
answered the question, after ten failed commands: it imported pyhood from
the source folder with the wrong Python, installed dependencies into the
system Python, and guessed a field name that does not exist. Each test
here pins one thing that would have stopped it going wrong.
"""

import builtins
import copy
import dataclasses
import importlib
import inspect
import pickle
import re
import sys
from pathlib import Path

import pytest

import pyhood
from pyhood import guide, models, onboarding, verify
from pyhood._model import Model
from pyhood.client import PyhoodClient
from pyhood.crypto import models as crypto_models
from pyhood.exceptions import AuthError
from pyhood.models import OptionContract, Order, Position

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def position():
    return Position("ANT", 95, 97.13, 80.19, 7617.57, -1609.43, -17.44)


# ── A wrong field name names the right ones ──────────────────────────


class TestWrongFieldName:
    def test_error_lists_the_real_fields(self, position):
        """The model guessed `average_buy_price`, Robinhood's own name."""
        with pytest.raises(AttributeError) as error:
            position.average_buy_price

        message = str(error.value)
        assert "Position has no field 'average_buy_price'" in message
        for field in dataclasses.fields(Position):
            assert field.name in message

    def test_error_lists_computed_properties_too(self):
        contract = OptionContract("AAPL", "call", 200, "2026-12-18", 1.0)

        with pytest.raises(AttributeError, match="Computed: vol_oi_ratio, cost_per_contract"):
            contract.implied_volatility

    def test_real_fields_and_hasattr_are_unaffected(self, position):
        assert position.average_cost == 97.13
        assert not hasattr(position, "average_buy_price")
        assert getattr(position, "average_buy_price", None) is None

    def test_copy_pickle_and_asdict_still_work(self, position):
        """They look up dunder names, which must get the ordinary error."""
        assert copy.deepcopy(position) == position
        assert pickle.loads(pickle.dumps(position)) == position
        assert dataclasses.asdict(position)["symbol"] == "ANT"
        with pytest.raises(AttributeError) as error:
            position.__no_such_dunder__
        assert "Its fields are" not in str(error.value)

    @pytest.mark.parametrize("module", [models, crypto_models])
    def test_every_model_has_it(self, module):
        """A model added later without the base would lose the message."""
        classes = [
            cls for _, cls in inspect.getmembers(module, inspect.isclass)
            if dataclasses.is_dataclass(cls) and cls.__module__ == module.__name__
        ]
        assert classes
        assert [cls.__name__ for cls in classes if not issubclass(cls, Model)] == []


# ── A misplaced install says what is wrong ───────────────────────────


class TestImportErrors:
    def test_old_python_is_named_as_the_problem(self, monkeypatch):
        """On 3.9 the import used to die inside urls.py with
        "unsupported operand type(s) for |"."""
        monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
        try:
            with pytest.raises(ImportError) as error:
                importlib.reload(pyhood)
        finally:
            monkeypatch.undo()
            importlib.reload(pyhood)

        message = str(error.value)
        assert "requires Python 3.10 or newer" in message
        assert "this is Python 3.9" in message
        assert "pyhood run script.py" in message

    def test_the_check_itself_runs_on_old_pythons(self):
        """It is no use if the file fails to parse before reaching it."""
        import ast

        source = (ROOT / "pyhood" / "__init__.py").read_text(encoding="utf-8")
        ast.parse(source, feature_version=(3, 6))

    def _reload_without(self, monkeypatch, missing):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pyhood.auth":
                raise ModuleNotFoundError(f"No module named {missing!r}", name=missing)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        try:
            importlib.reload(pyhood)
        finally:
            monkeypatch.undo()
            importlib.reload(pyhood)

    def test_missing_dependency_says_not_to_install_it_by_hand(self, monkeypatch):
        """The model answered "No module named 'requests'" by installing
        requests into the system Python with --break-system-packages."""
        with pytest.raises(ImportError) as error:
            self._reload_without(monkeypatch, "requests")

        message = str(error.value)
        assert "dependency 'requests' is not installed" in message
        assert "source folder" in message
        assert "Do not install the dependency by hand" in message
        assert not isinstance(error.value, ModuleNotFoundError)

    def test_other_missing_modules_are_not_disguised(self, monkeypatch):
        with pytest.raises(ModuleNotFoundError, match="something_else"):
            self._reload_without(monkeypatch, "something_else")


# ── The guide describes the code as it is ────────────────────────────


class TestGuide:
    """`pyhood guide` is the commands and the rules for orders. `pyhood
    guide python` is the reference for writing a script. They were one
    page, which grew to 240 lines: a model that read the first hundred
    never saw how to place a spread, and made up a Python call."""

    @pytest.mark.parametrize("name", guide.READ_METHODS + guide.WRITE_METHODS)
    def test_every_method_named_exists_and_is_not_retired(self, name):
        method = getattr(PyhoodClient, name)
        assert callable(method)
        assert not (inspect.getdoc(method) or "").startswith("Deprecated")

    @pytest.mark.parametrize("name", guide.MODELS)
    def test_every_model_named_exists_with_its_fields(self, name):
        cls = getattr(models, name)
        fields = ", ".join(f.name for f in dataclasses.fields(cls))
        assert f"  {name}: {fields}" in guide.render("python")

    def test_signatures_come_from_the_code(self):
        text = guide.render("python")
        assert (
            "client.get_quote(symbol: str, include_fundamentals: bool = False) -> Quote"
            in text
        )
        assert "'str'" not in text  # annotations unquoted

    def test_the_example_uses_real_methods_and_fields(self):
        """Hand-written code is where a guide goes stale."""
        for method in re.findall(r"client\.(\w+)\(", guide.SCRIPTS):
            assert hasattr(PyhoodClient, method), method
        position_fields = {f.name for f in dataclasses.fields(Position)}
        order_fields = {f.name for f in dataclasses.fields(Order)}
        assert set(re.findall(r"\bp\.(\w+)", guide.SCRIPTS)) <= position_fields
        assert set(re.findall(r"\bo\.(\w+)", guide.SCRIPTS)) <= order_fields

    def test_the_commands_page_carries_the_version_and_the_rules(self):
        text = guide.render()
        assert f"pyhood {pyhood.__version__}" in text
        assert "Never place an order or move money without showing the user" in text
        assert "Cancel an order only when the user asks you to." in text
        assert "Never ask for, read or type a password" in text
        assert "pyhood guide python" in text

    def test_the_commands_page_is_short_enough_to_be_read_whole(self):
        lines = guide.render().splitlines()
        assert len(lines) <= 150
        # A model that reads only the first hundred lines must still get
        # every rule for placing and cancelling an order.
        first_hundred = "\n".join(lines[:100])
        assert "PLACING ORDERS (two steps" in first_hundred
        assert "CANCELLING AN ORDER" in first_hundred
        assert first_hundred.index("PLACING ORDERS (") < first_hundred.index("LOOKING THINGS UP")

    def test_the_commands_page_has_no_python_reference(self):
        text = guide.render()
        assert "client." not in text
        assert "FIELDS" not in text

    def test_the_python_page_says_how_to_run_a_script(self):
        text = guide.render("python")
        assert "pyhood run script.py" in text
        assert "never place an order or move money" in text

    def test_orders_are_listed_apart_from_reads(self):
        text = guide.render("python")
        reading = text[text.index("READING"):text.index("FIELDS")]
        orders = text[text.index("ORDERS FROM A SCRIPT"):]
        for name in guide.WRITE_METHODS:
            assert f"client.{name}(" not in reading
            assert f"client.{name}(" in orders
        assert not set(guide.READ_METHODS) & set(guide.WRITE_METHODS)

    def test_guide_commands_print_each_page(self, capsys):
        assert onboarding.main(["guide"]) == 0
        assert capsys.readouterr().out == guide.render()

        assert onboarding.main(["guide", "python"]) == 0
        assert capsys.readouterr().out == guide.render("python")


# ── `pyhood run` finds the right Python ──────────────────────────────


class TestRun:
    def test_runs_with_the_python_pyhood_is_installed_in(self, capfd):
        code = "import sys, pyhood; print(sys.executable); print(pyhood.__version__)"

        assert onboarding.main(["run", "-c", code]) == 0

        executable, version = capfd.readouterr().out.split()
        assert executable == sys.executable
        assert version == pyhood.__version__

    def test_runs_a_script_with_its_arguments(self, tmp_path, capfd):
        script = tmp_path / "script.py"
        script.write_text("import sys; print(sys.argv[1:])")

        assert onboarding.main(["run", str(script), "--flag", "x"]) == 0
        assert capfd.readouterr().out.strip() == "['--flag', 'x']"

    def test_exit_code_is_the_scripts(self):
        assert onboarding.main(["run", "-c", "raise SystemExit(3)"]) == 3

    def test_nothing_to_run_is_a_usage_error(self, capsys):
        assert onboarding.main(["run"]) == 2
        assert "pyhood run script.py" in capsys.readouterr().out


# ── `pyhood verify` works after a plain install ──────────────────────


class TestVerify:
    def test_verify_runs_the_stock_check_by_default(self, monkeypatch):
        monkeypatch.setattr(verify, "verify_stocks", lambda: 7)
        monkeypatch.setattr(verify, "verify_crypto", lambda: 9)

        assert onboarding.main(["verify"]) == 7
        assert onboarding.main(["verify", "stocks"]) == 7
        assert onboarding.main(["verify", "crypto"]) == 9

    def test_not_logged_in_says_how_to_log_in(self, monkeypatch, capsys):
        def no_session():
            raise AuthError("no saved session")

        monkeypatch.setattr(pyhood, "login", no_session)

        assert verify.verify_stocks() == 1
        assert "pyhood setup login" in capsys.readouterr().out


# ── The docs name commands that exist ────────────────────────────────


# Words that follow "pyhood" inside a code span without being a command,
# as in the lines users paste into an agent: "pyhood is installed at ..."
# and "Install pyhood for me."
NOT_COMMANDS = {"is", "for", "cannot"}


def documented_commands():
    """Every `pyhood <word>` written in the docs an agent or user follows."""
    pattern = re.compile(r"(?<![\w/.-])pyhood ([\w-]+)")
    found = set()
    for path in (
        "README.md", "AGENTS.md", "install/AGENTS.md", "docs/getting-started.md",
        "docs/setup.md", "docs/cli.md",
    ):
        text = (ROOT / path).read_text(encoding="utf-8")
        # Commands appear in code spans and code blocks, not in prose.
        for code in re.findall(r"```.*?```|`[^`\n]+`", text, flags=re.S):
            found.update(
                (path, word) for word in pattern.findall(code) if word not in NOT_COMMANDS
            )
    return sorted(found)


@pytest.mark.parametrize(("path", "command"), documented_commands())
def test_documented_commands_exist(path, command):
    parser = onboarding.build_parser()
    subcommands = next(
        action.choices for action in parser._actions if getattr(action, "choices", None)
    )
    assert command in subcommands, f"{path} mentions `pyhood {command}`"


class TestInstallFolder:
    """An install carries its own AGENTS.md, so an agent started in the
    install folder is told what to do with nothing set up by hand."""

    def test_the_wheel_puts_agents_md_at_the_top_of_the_environment(self):
        config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "[tool.hatch.build.targets.wheel.shared-data]" in config
        assert '"install/AGENTS.md" = "AGENTS.md"' in config
        # The wheel is built from the sdist, so the sdist must carry the file.
        assert '"/install",' in config
        assert (ROOT / "install" / "AGENTS.md").is_file()

    def test_it_points_at_the_guide_by_a_path_that_works_in_that_folder(self):
        text = (ROOT / "install" / "AGENTS.md").read_text(encoding="utf-8")
        assert "bin/pyhood guide" in text
        assert "Do not install anything" in text
        assert "~/.pyhood/" in text
        assert "Place orders the way the guide says for this install" in text
        assert "never run `pyhood setup confirmation off`" in text
        assert "Cancel an order only when the user asks you to" in text

    def test_it_is_not_the_file_for_the_source_folder(self):
        """One says pyhood is installed here; the other says it is not."""
        installed = (ROOT / "install" / "AGENTS.md").read_text(encoding="utf-8")
        source = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "is installed in this folder" in installed
        assert "Do not run pyhood from a copy of this repository" in source
        assert "Do not run pyhood from a copy of this repository" not in installed


class TestInstallByAgent:
    """The README's install step is one line that sends an agent to the
    repository's AGENTS.md, so that file has to hold the steps."""

    URL = "https://raw.githubusercontent.com/jamestford/pyhood/main/AGENTS.md"

    def test_the_readme_and_getting_started_point_at_the_file(self):
        for path in ("README.md", "docs/getting-started.md"):
            text = (ROOT / path).read_text(encoding="utf-8")
            assert f"Follow the install steps in {self.URL}" in text, path

    def steps(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        return text[text.index("## If you were asked to install pyhood"):
                    text.index("## If you want to use pyhood")]

    def test_the_file_has_the_install_steps(self):
        steps = self.steps()
        assert (
            "curl -LsSf https://raw.githubusercontent.com/jamestford/pyhood/main/install.sh | sh"
            in steps
        )
        assert "uv venv --managed-python --python 3.14 ~/pyhood" in steps
        assert "uv pip install --python ~/pyhood/bin/python pyhood" in steps
        assert "~/pyhood/bin/pyhood verify" in steps
        assert "Read `~/pyhood/AGENTS.md`" in steps

    def test_the_agent_opens_the_login_window(self):
        steps = self.steps()
        assert "~/pyhood/bin/pyhood setup login --window" in steps
        assert "allow it two minutes" in steps
        assert "run it again. It does not open a second window" in steps
        assert "ask the user what happened before running it again" in steps

    def test_the_agent_has_a_way_on_when_no_window_opens(self):
        steps = self.steps()
        assert "could not open a window" in steps
        assert "run `~/pyhood/bin/pyhood setup login` themselves" in steps

    def test_the_agent_is_told_what_not_to_do(self):
        steps = self.steps()
        assert "If one fails, stop" in steps
        assert "already installed" in steps
        assert "Never ask for, read or type their password" in steps
        assert "Do not run `setup login` without `--window`" in steps
        assert "Do not install it yourself without asking" in steps
        assert "Do not use `pip`, `sudo` or `--break-system-packages`" in steps

    def test_the_readme_says_what_the_agent_is_told(self):
        """The folded-away list is a promise about what the file says."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for promise in (
            "`pyhood setup login --window`",
            "`pyhood verify`",
            "never to ask for, read or type your password",
        ):
            assert promise in readme, promise

    def test_the_agent_steps_and_the_readme_name_the_same_commands(self):
        """Both ways in build the same install."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        steps = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for command in (
            "uv venv --managed-python --python 3.14 ~/pyhood",
            "uv pip install --python ~/pyhood/bin/python pyhood",
        ):
            assert command in readme and command in steps, command


class TestInstallScript:
    """The README's first install step is one command that fetches
    install.sh, so the docs have to name it and describe it truthfully."""

    COMMAND = (
        "curl -LsSf https://raw.githubusercontent.com/jamestford/pyhood/main/install.sh | sh"
    )

    def test_the_readme_and_getting_started_give_the_command(self):
        for path in ("README.md", "docs/getting-started.md"):
            text = (ROOT / path).read_text(encoding="utf-8")
            assert self.COMMAND in text, path

    def test_the_script_names_the_same_command(self):
        assert self.COMMAND in (ROOT / "install.sh").read_text(encoding="utf-8")

    def test_the_script_runs_the_commands_the_readme_lists(self):
        """The folded-away list is a promise about what the script does."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        script = (ROOT / "install.sh").read_text(encoding="utf-8")
        assert "uv venv --managed-python --python 3.14 ~/pyhood" in readme
        assert "PYTHON_VERSION=3.14" in script
        assert '"$UV" venv --managed-python --python "$PYTHON_VERSION" "$DIR"' in script
        assert 'DIR="$HOME/pyhood"' in script
        assert "uv pip install --python ~/pyhood/bin/python pyhood" in readme
        assert '"$UV" pip install --python "$BIN/python" "$SPEC"' in script
        assert 'SPEC="${PYHOOD_INSTALL_SPEC:-pyhood}"' in script
        for command in ("setup login", "verify"):
            assert f"`pyhood {command}`" in readme
            assert f'"$BIN/pyhood" {command}' in script


def test_agents_file_sends_agents_to_the_guide():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "pyhood guide" in text
    assert "Do not run pyhood from a copy of this repository" in text
