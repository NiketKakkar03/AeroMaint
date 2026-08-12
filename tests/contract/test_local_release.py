from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_all_supported_profiles_are_declared() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()
    for profile in ("core", "media", "ml", "ai", "observe", "full"):
        assert profile in compose


def test_destructive_commands_require_explicit_local_target() -> None:
    lifecycle = (ROOT / "scripts/local-release").read_text()
    assert 'require_local_target "$TARGET"' in lifecycle
    assert '[[ "$CONFIRM" == "RESET" ]]' in lifecycle


def test_generated_secrets_and_backups_are_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env.local-release" in ignored
    assert "backups/" in ignored
