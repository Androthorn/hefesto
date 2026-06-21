import pytest
from hefesto.schemas.config import HefestoConfig, ProviderConfig, ConfigError


def _cfg(providers):
    return HefestoConfig(
        providers=providers, objective="o.yaml", prompt="p.txt",
        grader="llm_judge", store_path="h.db",
    )


def test_role_resolves_from_default():
    c = _cfg({"default": ProviderConfig(provider="openai", model="gpt-x")})
    assert c.provider_for("judge").model == "gpt-x"


def test_role_specific_overrides_default():
    c = _cfg({
        "default": ProviderConfig(provider="openai", model="gpt-x"),
        "judge": ProviderConfig(provider="anthropic", model="claude-y"),
    })
    assert c.provider_for("judge").model == "claude-y"


def test_missing_role_and_default_fails_fast():
    c = _cfg({"runner": ProviderConfig(provider="openai", model="gpt-x")})
    with pytest.raises(ConfigError) as e:
        c.provider_for("judge")
    assert "judge" in str(e.value)
