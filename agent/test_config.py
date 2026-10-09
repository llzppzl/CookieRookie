"""agent/test_config.py - reading the API settings from .env and the environment"""
import pytest

import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty CookieRookie folder and an environment without any of the settings"""
    monkeypatch.setattr(main, "PROJECT_DIR", str(tmp_path))
    for name in main.ENV_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def write_env(project, text):
    (project / ".env").write_text(text, encoding="utf-8")


def test_settings_from_env_file(project):
    write_env(project, "ANTHROPIC_API_KEY=sk-file\nMODEL_ID=glm-5\nANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic\n")
    config = main.load_config()
    assert config["api_key"] == "sk-file"
    assert config["model"] == "glm-5"
    assert config["base_url"] == "https://api.z.ai/api/anthropic"


def test_quotes_around_values_are_removed(project):
    write_env(project, "ANTHROPIC_API_KEY=\"sk-quoted\"\nMODEL_ID='deepseek-chat'\n")
    config = main.load_config()
    assert config["api_key"] == "sk-quoted"
    assert config["model"] == "deepseek-chat"


def test_environment_without_env_file(project, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.setenv("MODEL_ID", "claude-sonnet-4-6")
    config = main.load_config()
    assert config["api_key"] == "sk-env"
    assert config["model"] == "claude-sonnet-4-6"
    assert config["base_url"] == "https://api.minimax.io/anthropic"  # default kept


def test_environment_wins_over_env_file(project, monkeypatch):
    write_env(project, "ANTHROPIC_API_KEY=sk-file\nMODEL_ID=glm-5\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.setenv("MODEL_ID", "")  # empty means not set
    config = main.load_config()
    assert config["api_key"] == "sk-env"
    assert config["model"] == "glm-5"


@pytest.mark.parametrize("line", ["ANTHROPIC_API_KEY=your-api-key-here", "ANTHROPIC_API_KEY=", 'ANTHROPIC_API_KEY=""'])
def test_placeholder_or_empty_key_counts_as_missing(project, line):
    write_env(project, line + "\n")
    assert main.load_config()["api_key"] is None


def test_missing_key_message_mentions_both_places(project, monkeypatch, capsys):
    monkeypatch.setattr(main.sys, "argv", ["main.py", "some bug"])
    main.main()
    out = capsys.readouterr().out
    assert ".env" in out
    assert "export ANTHROPIC_API_KEY" in out
