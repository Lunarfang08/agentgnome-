import os
import stat

from scripts.bootstrap import initialize_env


def test_bootstrap_creates_private_unique_tokens(tmp_path):
    (tmp_path / ".env.example").write_text("AG_PROFILE=dev\nAG_DEV_TOKEN=\n")
    assert initialize_env(tmp_path)
    content = (tmp_path / ".env").read_text()
    token = content.split("AG_DEV_TOKEN=")[1].strip()
    assert len(token) >= 40
    assert not initialize_env(tmp_path)
    assert (tmp_path / ".env").read_text() == content
    if os.name != "nt":
        assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600


def test_bootstrap_preserves_custom_secrets_and_rotates_legacy_token(tmp_path):
    target = tmp_path / ".env"
    target.write_text(
        "AG_PROVIDER_API_KEY=private-fixture\nAG_DEV_TOKEN=local-development-token-change-me\n"
    )
    assert initialize_env(tmp_path)
    content = target.read_text()
    assert "local-development-token-change-me" not in content
    assert "AG_PROVIDER_API_KEY=private-fixture" in content
    assert not initialize_env(tmp_path)
