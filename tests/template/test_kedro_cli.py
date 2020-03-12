# Copyright 2020 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
#     or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=unused-argument
import os
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import anyconfig
import pytest
from click.testing import CliRunner

from kedro.extras.datasets.pandas import CSVDataSet
from kedro.io.data_catalog import DataCatalog
from kedro.io.memory_data_set import MemoryDataSet
from kedro.runner import ParallelRunner, SequentialRunner


@pytest.fixture(autouse=True)
def call_mock(mocker, fake_kedro_cli):
    return mocker.patch.object(fake_kedro_cli, "call")


@pytest.fixture(autouse=True)
def python_call_mock(mocker, fake_kedro_cli):
    return mocker.patch.object(fake_kedro_cli, "python_call")


@pytest.fixture()
def fake_ipython_message(mocker, fake_kedro_cli):
    return mocker.patch.object(fake_kedro_cli, "ipython_message")


class TestActivateNbstripoutCommand:
    @staticmethod
    @pytest.fixture()
    def fake_nbstripout():
        """
        ``nbstripout`` tries to access ``sys.stdin.buffer.readable``
        on import, but it's patches by pytest.
        Let's replace it by the fake!
        """
        sys.modules["nbstripout"] = "fake"
        yield
        del sys.modules["nbstripout"]

    @staticmethod
    @pytest.fixture
    def fake_git_repo(mocker):
        return mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))

    @staticmethod
    @pytest.fixture
    def without_git_repo(mocker):
        return mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1))

    def test_install_successfully(
        self, fake_kedro_cli, call_mock, fake_nbstripout, fake_git_repo
    ):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["activate-nbstripout"])
        assert not result.exit_code

        call_mock.assert_called_once_with(["nbstripout", "--install"])

        fake_git_repo.assert_called_once_with(
            ["git", "rev-parse", "--git-dir"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_nbstripout_not_installed(self, fake_kedro_cli, fake_git_repo, mocker):
        """
        Run activate-nbstripout target without nbstripout installed
        There should be a clear message about it.
        """
        mocker.patch.dict("sys.modules", {"nbstripout": None})

        result = CliRunner().invoke(fake_kedro_cli.cli, ["activate-nbstripout"])
        assert result.exit_code
        assert "nbstripout is not installed" in result.stdout

    def test_no_git_repo(self, fake_kedro_cli, fake_nbstripout, without_git_repo):
        """
        Run activate-nbstripout target with no git repo available.
        There should be a clear message about it.
        """
        result = CliRunner().invoke(fake_kedro_cli.cli, ["activate-nbstripout"])

        assert result.exit_code
        assert "Not a git repository" in result.stdout


class TestRunCommand:
    @staticmethod
    @pytest.fixture(autouse=True)
    def fake_load_context(mocker, fake_kedro_cli):
        context = mocker.Mock()
        yield mocker.patch.object(fake_kedro_cli, "load_context", return_value=context)

    @staticmethod
    @pytest.fixture(params=["run_config.yml", "run_config.json"])
    def fake_run_config(request, fake_root_dir):
        config_path = str(fake_root_dir / request.param)
        anyconfig.dump(
            {
                "run": {
                    "pipeline": "pipeline1",
                    "tag": ["tag1", "tag2"],
                    "node_names": ["node1", "node2"],
                }
            },
            config_path,
        )
        return config_path

    @staticmethod
    @pytest.fixture()
    def fake_run_config_with_params(fake_run_config, request):
        config = anyconfig.load(fake_run_config)
        config["run"].update(request.param)
        anyconfig.dump(config, fake_run_config)
        return fake_run_config

    def test_run_successfully(self, fake_kedro_cli, fake_load_context, mocker):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["run"])
        assert not result.exit_code

        fake_load_context.return_value.run.assert_called_once_with(
            tags=(),
            runner=mocker.ANY,
            node_names=(),
            from_nodes=[],
            to_nodes=[],
            from_inputs=[],
            load_versions={},
            pipeline_name=None,
        )

        assert isinstance(
            fake_load_context.return_value.run.call_args_list[0][1]["runner"],
            SequentialRunner,
        )

    def test_with_sequential_runner_and_parallel_flag(
        self, fake_kedro_cli, fake_load_context
    ):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["run", "--parallel", "--runner=SequentialRunner"]
        )

        assert result.exit_code
        assert "Please use either --parallel or --runner" in result.stdout
        fake_load_context.return_value.run.assert_not_called()

    def test_run_successfully_parallel_via_flag(
        self, fake_kedro_cli, fake_load_context, mocker
    ):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["run", "--parallel"])

        assert not result.exit_code

        fake_load_context.return_value.run.assert_called_once_with(
            tags=(),
            runner=mocker.ANY,
            node_names=(),
            from_nodes=[],
            to_nodes=[],
            from_inputs=[],
            load_versions={},
            pipeline_name=None,
        )

        assert isinstance(
            fake_load_context.return_value.run.call_args_list[0][1]["runner"],
            ParallelRunner,
        )

    def test_run_successfully_parallel_via_name(
        self, fake_kedro_cli, fake_load_context
    ):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["run", "--runner=ParallelRunner"]
        )

        assert not result.exit_code
        assert isinstance(
            fake_load_context.return_value.run.call_args_list[0][1]["runner"],
            ParallelRunner,
        )

    @pytest.mark.parametrize("config_flag", ["--config", "-c"])
    def test_run_with_config(
        self, config_flag, fake_kedro_cli, fake_load_context, fake_run_config, mocker
    ):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["run", config_flag, fake_run_config]
        )
        assert not result.exit_code
        fake_load_context.return_value.run.assert_called_once_with(
            tags=("tag1", "tag2"),
            runner=mocker.ANY,
            node_names=("node1", "node2"),
            from_nodes=[],
            to_nodes=[],
            from_inputs=[],
            load_versions={},
            pipeline_name="pipeline1",
        )

    @pytest.mark.parametrize(
        "fake_run_config_with_params,expected",
        [
            ({}, {}),
            ({"params": {"foo": "baz"}}, {"foo": "baz"}),
            ({"params": "foo:baz"}, {"foo": "baz"}),
            (
                {"params": {"foo": "123.45", "baz": "678", "bar": 9}},
                {"foo": "123.45", "baz": "678", "bar": 9},
            ),
        ],
        indirect=["fake_run_config_with_params"],
    )
    def test_run_with_params_in_config(
        self,
        expected,
        fake_kedro_cli,
        fake_load_context,
        fake_run_config_with_params,
        mocker,
    ):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["run", "-c", fake_run_config_with_params]
        )
        assert not result.exit_code
        fake_load_context.return_value.run.assert_called_once_with(
            tags=("tag1", "tag2"),
            runner=mocker.ANY,
            node_names=("node1", "node2"),
            from_nodes=[],
            to_nodes=[],
            from_inputs=[],
            load_versions={},
            pipeline_name="pipeline1",
        )
        fake_load_context.assert_called_once_with(
            Path.cwd(), env=mocker.ANY, extra_params=expected
        )

    @pytest.mark.parametrize(
        "cli_arg,expected_extra_params",
        [
            ("foo:bar", {"foo": "bar"}),
            (
                "foo:123.45, bar:1a,baz:678. ,qux:1e-2,quux:0,quuz:",
                {
                    "foo": 123.45,
                    "bar": "1a",
                    "baz": 678,
                    "qux": 0.01,
                    "quux": 0,
                    "quuz": "",
                },
            ),
            ("foo:bar,baz:fizz:buzz", {"foo": "bar", "baz": "fizz:buzz"}),
            (
                "foo:bar, baz: https://example.com",
                {"foo": "bar", "baz": "https://example.com"},
            ),
            ("foo:bar,baz:fizz buzz", {"foo": "bar", "baz": "fizz buzz"}),
            ("foo:bar, foo : fizz buzz  ", {"foo": "fizz buzz"}),
        ],
    )
    def test_run_extra_params(
        self, mocker, fake_kedro_cli, fake_load_context, cli_arg, expected_extra_params
    ):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["run", "--params", cli_arg])

        assert not result.exit_code
        fake_load_context.assert_called_once_with(
            Path.cwd(), env=mocker.ANY, extra_params=expected_extra_params
        )

    @pytest.mark.parametrize("bad_arg", ["bad", "foo:bar,bad"])
    def test_bad_extra_params(self, fake_kedro_cli, fake_load_context, bad_arg):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["run", "--params", bad_arg])
        assert result.exit_code
        assert (
            "Item `bad` must contain a key and a value separated by `:`"
            in result.stdout
        )

    @pytest.mark.parametrize("bad_arg", [":", ":value", " :value"])
    def test_bad_params_key(self, fake_kedro_cli, fake_load_context, bad_arg):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["run", "--params", bad_arg])
        assert result.exit_code
        assert "Parameter key cannot be an empty string" in result.stdout


class TestTestCommand:
    def test_happy_path(self, fake_kedro_cli, python_call_mock):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["test", "--random-arg", "value"]
        )
        assert not result.exit_code
        python_call_mock.assert_called_once_with("pytest", ("--random-arg", "value"))

    def test_pytest_not_installed(self, fake_kedro_cli, python_call_mock, mocker):
        mocker.patch.dict("sys.modules", {"pytest": None})

        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["test", "--random-arg", "value"]
        )
        expected_message = fake_kedro_cli.NO_DEPENDENCY_MESSAGE.format("pytest")

        assert result.exit_code
        assert expected_message in result.stdout
        python_call_mock.assert_not_called()


class TestLintCommand:
    def test_bare_lint(self, fake_kedro_cli, python_call_mock, mocker):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["lint"])
        assert not result.exit_code

        files = ("src/tests", "src/fake_package")
        expected_calls = [
            mocker.call("flake8", ("--max-line-length=88",) + files),
            mocker.call(
                "isort", ("-rc", "-tc", "-up", "-fgw=0", "-m=3", "-w=88") + files
            ),
        ]
        if sys.version_info[:2] >= (3, 6):
            expected_calls.insert(0, mocker.call("black", files))  # pragma: no cover

        assert python_call_mock.call_args_list == expected_calls

    def test_file_lint(self, fake_kedro_cli, python_call_mock, mocker):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["lint", "kedro"])
        assert not result.exit_code

        files = ("kedro",)
        expected_calls = [
            mocker.call("flake8", ("--max-line-length=88",) + files),
            mocker.call(
                "isort", ("-rc", "-tc", "-up", "-fgw=0", "-m=3", "-w=88") + files
            ),
        ]
        if sys.version_info[:2] >= (3, 6):
            expected_calls.insert(0, mocker.call("black", files))  # pragma: no cover

        assert python_call_mock.call_args_list == expected_calls

    @pytest.mark.parametrize("module_name", ["flake8", "isort"])
    def test_import_not_installed(
        self, fake_kedro_cli, python_call_mock, module_name, mocker
    ):
        mocker.patch.dict("sys.modules", {module_name: None})

        result = CliRunner().invoke(fake_kedro_cli.cli, ["lint"])
        expected_message = fake_kedro_cli.NO_DEPENDENCY_MESSAGE.format(module_name)

        assert result.exit_code
        assert expected_message in result.stdout
        python_call_mock.assert_not_called()


class TestInstallCommand:
    def test_happy_path(self, python_call_mock, call_mock, fake_kedro_cli):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["install"])
        assert not result.exit_code
        python_call_mock.assert_called_once_with(
            "pip", ["install", "-U", "-r", "src/requirements.txt"]
        )
        call_mock.assert_not_called()

    def test_with_env_file(self, python_call_mock, call_mock, fake_kedro_cli, mocker):
        # Pretend env file exists:
        mocker.patch.object(Path, "is_file", return_value=True)

        result = CliRunner().invoke(fake_kedro_cli.cli, ["install"])
        assert not result.exit_code, result.stdout
        python_call_mock.assert_called_once_with(
            "pip", ["install", "-U", "-r", "src/requirements.txt"]
        )
        call_mock.assert_called_once_with(
            ["conda", "install", "--file", "src/environment.yml", "--yes"]
        )

    def test_windows(self, fake_kedro_cli, mocker):
        mock_subprocess = mocker.patch.object(fake_kedro_cli, "subprocess")
        # pretend we are on Windows
        mocker.patch.object(fake_kedro_cli, "os").name = "nt"

        result = CliRunner().invoke(fake_kedro_cli.cli, ["install"])
        assert not result.exit_code, result.stdout

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "-r",
            "src/requirements.txt",
        ]
        mock_subprocess.Popen.assert_called_once_with(
            command, creationflags=mock_subprocess.CREATE_NEW_CONSOLE
        )


class TestIpythonCommand:
    def test_happy_path(self, call_mock, fake_kedro_cli, fake_ipython_message):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["ipython", "--random-arg", "value"]
        )
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_called_once_with()
        call_mock.assert_called_once_with(["ipython", "--random-arg", "value"])

    @pytest.mark.parametrize("help_flag", ["-h", "--help"])
    def test_help(self, help_flag, call_mock, fake_kedro_cli, fake_ipython_message):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["ipython", help_flag])
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_not_called()
        call_mock.assert_called_once_with(["ipython", help_flag])


class TestPackageCommand:
    def test_happy_path(self, call_mock, fake_kedro_cli, mocker):
        result = CliRunner().invoke(fake_kedro_cli.cli, ["package"])
        assert not result.exit_code, result.stdout
        call_mock.assert_has_calls(
            [
                mocker.call(
                    [sys.executable, "setup.py", "clean", "--all", "bdist_egg"],
                    cwd="src",
                ),
                mocker.call(
                    [sys.executable, "setup.py", "clean", "--all", "bdist_wheel"],
                    cwd="src",
                ),
            ]
        )


class TestBuildDocsCommand:
    def test_happy_path(self, call_mock, python_call_mock, fake_kedro_cli, mocker):
        fake_rmtree = mocker.patch("shutil.rmtree")

        result = CliRunner().invoke(fake_kedro_cli.cli, ["build-docs"])
        assert not result.exit_code, result.stdout
        call_mock.assert_has_calls(
            [
                mocker.call(
                    [
                        "sphinx-apidoc",
                        "--module-first",
                        "-o",
                        "docs/source",
                        "src/fake_package",
                    ]
                ),
                mocker.call(
                    ["sphinx-build", "-M", "html", "docs/source", "docs/build", "-a"]
                ),
            ]
        )
        python_call_mock.assert_has_calls(
            [
                mocker.call("pip", ["install", "src/[docs]"]),
                mocker.call("pip", ["install", "-r", "src/requirements.txt"]),
                mocker.call("ipykernel", ["install", "--user", "--name=fake_package"]),
            ]
        )
        fake_rmtree.assert_called_once_with("docs/build", ignore_errors=True)

    @pytest.mark.parametrize("open_flag", ["-o", "--open"])
    def test_open_docs(self, open_flag, fake_kedro_cli, mocker):
        patched_browser = mocker.patch("webbrowser.open")
        result = CliRunner().invoke(fake_kedro_cli.cli, ["build-docs", open_flag])
        assert not result.exit_code, result.stdout
        expected_path = (Path.cwd() / "docs" / "build" / "html" / "index.html").as_uri()
        patched_browser.assert_called_once_with(expected_path)


class TestBuildReqsCommand:
    def test_requirements_file_exists(self, python_call_mock, fake_kedro_cli, mocker):
        # File exists:
        mocker.patch.object(Path, "is_file", return_value=True)

        result = CliRunner().invoke(fake_kedro_cli.cli, ["build-reqs"])
        assert not result.exit_code, result.stdout
        assert "Requirements built!" in result.stdout

        python_call_mock.assert_called_once_with(
            "piptools", ["compile", str(Path.cwd() / "src" / "requirements.in")]
        )

    def test_requirements_file_doesnt_exist(
        self, python_call_mock, fake_kedro_cli, mocker
    ):
        # File does not exist:
        mocker.patch.object(Path, "is_file", return_value=False)
        mocker.patch.object(Path, "read_text", return_value="fake requirements")
        fake_writer = mocker.patch.object(Path, "write_text")

        result = CliRunner().invoke(fake_kedro_cli.cli, ["build-reqs"])
        assert not result.exit_code, result.stdout
        assert "Requirements built!" in result.stdout
        python_call_mock.assert_called_once_with(
            "piptools", ["compile", str(Path.cwd() / "src" / "requirements.in")]
        )
        fake_writer.assert_called_once_with("fake requirements")


class TestJupyterNotebookCommand:
    @pytest.fixture
    def default_jupyter_options(self):
        return (
            "jupyter",
            [
                "notebook",
                "--ip",
                "127.0.0.1",
                "--MappingKernelManager.cull_idle_timeout=30",
                "--MappingKernelManager.cull_interval=30",
                "--NotebookApp.kernel_spec_manager_class="
                "kedro.cli.jupyter.SingleKernelSpecManager",
                "--KernelSpecManager.default_kernel_name='TestProject'",
            ],
        )

    def test_default_kernel(
        self, python_call_mock, fake_kedro_cli, fake_ipython_message
    ):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "notebook", "--ip", "0.0.0.0"]
        )
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_called_once_with(False)
        python_call_mock.assert_called_once_with(
            "jupyter",
            [
                "notebook",
                "--ip",
                "0.0.0.0",
                "--MappingKernelManager.cull_idle_timeout=30",
                "--MappingKernelManager.cull_interval=30",
                "--NotebookApp.kernel_spec_manager_class="
                "kedro.cli.jupyter.SingleKernelSpecManager",
                "--KernelSpecManager.default_kernel_name='TestProject'",
            ],
        )

    def test_all_kernels(self, python_call_mock, fake_kedro_cli, fake_ipython_message):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "notebook", "--all-kernels"]
        )
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_called_once_with(True)
        python_call_mock.assert_called_once_with(
            "jupyter",
            [
                "notebook",
                "--ip",
                "127.0.0.1",
                "--MappingKernelManager.cull_idle_timeout=30",
                "--MappingKernelManager.cull_interval=30",
            ],
        )

    @pytest.mark.parametrize("help_flag", ["-h", "--help"])
    def test_help(self, help_flag, fake_kedro_cli, fake_ipython_message):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "notebook", help_flag]
        )
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_not_called()

    @pytest.mark.parametrize("env_flag", ["--env", "-e"])
    def test_env(
        self, env_flag, fake_kedro_cli, python_call_mock, default_jupyter_options
    ):
        """This tests passing an environment variable to the jupyter subprocess."""
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "notebook", env_flag, "my_special_env"]
        )
        assert not result.exit_code

        args, kwargs = python_call_mock.call_args
        assert args == default_jupyter_options
        assert "env" in kwargs
        assert kwargs["env"]["KEDRO_ENV"] == "my_special_env"


class TestJupyterLabCommand:
    @pytest.fixture
    def default_jupyter_options(self):
        return (
            "jupyter",
            [
                "lab",
                "--ip",
                "127.0.0.1",
                "--MappingKernelManager.cull_idle_timeout=30",
                "--MappingKernelManager.cull_interval=30",
                "--NotebookApp.kernel_spec_manager_class="
                "kedro.cli.jupyter.SingleKernelSpecManager",
                "--KernelSpecManager.default_kernel_name='TestProject'",
            ],
        )

    def test_default_kernel(
        self, python_call_mock, fake_kedro_cli, fake_ipython_message
    ):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "lab", "--ip", "0.0.0.0"]
        )
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_called_once_with(False)
        python_call_mock.assert_called_once_with(
            "jupyter",
            [
                "lab",
                "--ip",
                "0.0.0.0",
                "--MappingKernelManager.cull_idle_timeout=30",
                "--MappingKernelManager.cull_interval=30",
                "--NotebookApp.kernel_spec_manager_class="
                "kedro.cli.jupyter.SingleKernelSpecManager",
                "--KernelSpecManager.default_kernel_name='TestProject'",
            ],
        )

    def test_all_kernels(self, python_call_mock, fake_kedro_cli, fake_ipython_message):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "lab", "--all-kernels"]
        )
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_called_once_with(True)
        python_call_mock.assert_called_once_with(
            "jupyter",
            [
                "lab",
                "--ip",
                "127.0.0.1",
                "--MappingKernelManager.cull_idle_timeout=30",
                "--MappingKernelManager.cull_interval=30",
            ],
        )

    @pytest.mark.parametrize("help_flag", ["-h", "--help"])
    def test_help(self, help_flag, fake_kedro_cli, fake_ipython_message):
        result = CliRunner().invoke(
            fake_kedro_cli.cli, [sys.executable, "-m", "jupyter", "lab", help_flag]
        )
        assert not result.exit_code, result.stdout
        fake_ipython_message.assert_not_called()

    @pytest.mark.parametrize("env_flag", ["--env", "-e"])
    def test_env(
        self, env_flag, fake_kedro_cli, python_call_mock, default_jupyter_options
    ):
        """This tests passing an environment variable to the jupyter subprocess."""
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "lab", env_flag, "my_special_env"]
        )
        assert not result.exit_code

        args, kwargs = python_call_mock.call_args
        assert args == default_jupyter_options
        assert "env" in kwargs
        assert kwargs["env"]["KEDRO_ENV"] == "my_special_env"


class TestConvertNotebookCommand:
    @staticmethod
    @pytest.fixture
    def fake_export_nodes(mocker, fake_kedro_cli):
        return mocker.patch.object(fake_kedro_cli, "export_nodes")

    @staticmethod
    @pytest.fixture
    def tmp_file_path():
        with NamedTemporaryFile() as f:
            yield Path(f.name)

    @staticmethod
    @pytest.fixture(autouse=True)
    def chdir_to_repo_root(fake_repo_path):
        os.chdir(str(fake_repo_path))

    # pylint: disable=too-many-arguments
    def test_convert_one_file_overwrite(
        self, mocker, fake_kedro_cli, fake_export_nodes, tmp_file_path, fake_repo_path
    ):
        """
        Trying to convert one file, the output file already exists,
        overwriting it.
        """
        mocker.patch.object(Path, "is_file", return_value=True)
        mocker.patch("click.confirm", return_value=True)

        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "convert", str(tmp_file_path)]
        )
        assert not result.exit_code, result.stdout

        output_prefix = fake_repo_path.resolve() / "src" / "fake_package" / "nodes"
        fake_export_nodes.assert_called_once_with(
            tmp_file_path.resolve(), output_prefix / "{}.py".format(tmp_file_path.stem)
        )

    def test_convert_one_file_do_not_overwrite(
        self, mocker, fake_kedro_cli, fake_export_nodes, tmp_file_path
    ):
        """
        Trying to convert one file, the output file already exists,
        user refuses to overwrite it.
        """
        mocker.patch.object(Path, "is_file", return_value=True)
        mocker.patch("click.confirm", return_value=False)

        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["jupyter", "convert", str(tmp_file_path)]
        )
        assert not result.exit_code, result.stdout

        fake_export_nodes.assert_not_called()

    def test_convert_all_files(
        self, mocker, fake_kedro_cli, fake_export_nodes, fake_repo_path
    ):
        """
        Trying to convert all files, the output files already exist.
        """
        mocker.patch.object(Path, "is_file", return_value=True)
        mocker.patch("click.confirm", return_value=True)
        mocker.patch.object(
            fake_kedro_cli, "iglob", return_value=["/path/1", "/path/2"]
        )

        result = CliRunner().invoke(fake_kedro_cli.cli, ["jupyter", "convert", "--all"])
        assert not result.exit_code, result.stdout

        output_prefix = (fake_repo_path / "src" / "fake_package" / "nodes").resolve()
        fake_export_nodes.assert_has_calls(
            [
                mocker.call(Path("/path/1"), output_prefix / "1.py"),
                mocker.call(Path("/path/2"), output_prefix / "2.py"),
            ]
        )


class TestCatalogListCommand:
    PIPELINE_NAME = "pipeline"

    @staticmethod
    @pytest.fixture
    def fake_load_context(mocker, fake_kedro_cli):
        context = mocker.MagicMock()
        return mocker.patch.object(fake_kedro_cli, "load_context", return_value=context)

    def test_list_all_pipelines(self, fake_kedro_cli, fake_load_context, mocker):
        yaml_dump_mock = mocker.patch("yaml.dump", return_value="Result YAML")
        mocked_context = fake_load_context.return_value
        mocked_context.pipelines.keys.return_value = (self.PIPELINE_NAME,)
        mocked_context.catalog.list.return_value = []
        mocked_pl_obj = mocked_context.pipelines.get.return_value
        mocked_pl_obj.data_sets.return_value = set()

        result = CliRunner().invoke(fake_kedro_cli.cli, ["catalog", "list"])

        assert not result.exit_code
        assert mocked_context.pipelines.keys.call_count == 1
        mocked_context.pipelines.get.assert_called_once_with(self.PIPELINE_NAME)

        expected_dict = {"DataSets in 'pipeline' pipeline": {}}
        yaml_dump_mock.assert_called_once_with(expected_dict)

    def test_list_specific_pipelines(self, fake_kedro_cli, fake_load_context):
        mocked_context = fake_load_context.return_value

        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["catalog", "list", "--pipeline", self.PIPELINE_NAME]
        )

        assert not result.exit_code
        assert not mocked_context.pipelines.keys.called
        mocked_context.pipelines.get.assert_called_once_with(self.PIPELINE_NAME)

    def test_not_found_pipeline(self, fake_kedro_cli, fake_load_context):
        mocked_context = fake_load_context.return_value
        mocked_context.pipelines.get.return_value = None
        mocked_context.pipelines.keys.return_value = (self.PIPELINE_NAME,)
        result = CliRunner().invoke(
            fake_kedro_cli.cli, ["catalog", "list", "--pipeline", "fake"]
        )
        assert result.exit_code
        expected_output = "Error: fake pipeline not found! Existing pipelines: {}\n".format(
            self.PIPELINE_NAME
        )
        assert result.output == expected_output

    def test_no_param_datasets_in_respose(
        self, fake_kedro_cli, fake_load_context, mocker
    ):
        yaml_dump_mock = mocker.patch("yaml.dump", return_value="Result YAML")
        mocked_context = fake_load_context.return_value
        catalog_data_sets = {
            "iris_data": CSVDataSet("test.csv"),
            "parameters": MemoryDataSet(),
            "params:data_ratio": MemoryDataSet(),
            "intermediate": MemoryDataSet(),
            "not_used": CSVDataSet("test2.csv"),
        }

        pl_obj_data_sets = set(catalog_data_sets.keys()).difference(["not_used"])
        mocked_context.catalog = DataCatalog(data_sets=catalog_data_sets)
        mocked_context.pipelines.keys.return_value = (self.PIPELINE_NAME,)
        mocked_pl_obj = mocked_context.pipelines.get.return_value
        mocked_pl_obj.data_sets.return_value = pl_obj_data_sets

        result = CliRunner().invoke(fake_kedro_cli.cli, ["catalog", "list"])

        assert not result.exit_code
        # 'parameters' and 'params:data_ratio' should not appear in the response
        expected_dict = {
            "DataSets in 'pipeline' pipeline": {
                "Datasets mentioned in pipeline": {
                    "CSVDataSet": ["iris_data"],
                    "MemoryDataSet": ["intermediate"],
                },
                "Datasets not mentioned in pipeline": {"CSVDataSet": ["not_used"]},
            }
        }
        yaml_dump_mock.assert_called_once_with(expected_dict)
