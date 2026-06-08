from app.core.config import Settings


def test_settings_accepts_legacy_deepseek_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_KEY", "legacy-key")

    settings = Settings(_env_file=None)

    assert settings.deepseek_api_key == "legacy-key"
