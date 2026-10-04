"""cookierookie/test_cli_config.py - 配置加载顺序"""
import pytest

from cookierookie import cli


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """把当前目录、用户配置、仓库目录都指向临时目录，并清掉相关环境变量"""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(cli, "USER_CONFIG", tmp_path / "user" / ".env")
    monkeypatch.setattr(cli, "REPO_DIR", tmp_path / "repo")
    write_env(tmp_path / "repo" / "pyproject.toml", "")
    for key in cli.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def write_env(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_defaults_without_any_config(isolated):
    config = cli.load_config()
    assert config["api_key"] is None
    assert config["model"] == "MiniMax-M2.5"


def test_environment_variable_is_enough(isolated, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert cli.load_config()["api_key"] == "from-env"


def test_user_config_is_used_from_any_directory(isolated):
    write_env(isolated / "user" / ".env", "ANTHROPIC_API_KEY=from-user\nMODEL_ID=deepseek-chat\n")
    config = cli.load_config()
    assert config["api_key"] == "from-user"
    assert config["model"] == "deepseek-chat"


def test_priority_env_over_project_over_user_over_repo(isolated, monkeypatch):
    write_env(isolated / "repo" / ".env", "ANTHROPIC_API_KEY=repo\nMODEL_ID=repo-model\nANTHROPIC_BASE_URL=repo-url\n")
    write_env(isolated / "user" / ".env", "ANTHROPIC_API_KEY=user\nMODEL_ID=user-model\n")
    write_env(isolated / "project" / ".env", "ANTHROPIC_API_KEY=project\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env")

    config = cli.load_config()

    assert config["api_key"] == "env"
    assert config["model"] == "user-model"
    assert config["base_url"] == "repo-url"


def test_comments_and_quotes_are_ignored(isolated):
    write_env(isolated / "project" / ".env", '# comment\nANTHROPIC_API_KEY="quoted"\n')
    assert cli.load_config()["api_key"] == "quoted"


def test_installed_package_does_not_look_for_env_in_site_packages(isolated, monkeypatch):
    site_packages = isolated / "site-packages"
    write_env(site_packages / ".env", "ANTHROPIC_API_KEY=should-not-be-read\n")
    monkeypatch.setattr(cli, "REPO_DIR", site_packages)

    assert site_packages / ".env" not in cli.config_paths()
    assert cli.load_config()["api_key"] is None
