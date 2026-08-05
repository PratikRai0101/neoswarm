from cli import _auth_provider_rows


def test_auth_provider_rows_include_subscription_and_custom_providers():
    rows = _auth_provider_rows(
        {
            "anthropic_api_key": None,
            "claude_subscription_token": "__neoswarm_secret_unchanged__",
            "openai_api_key": "__neoswarm_secret_unchanged__",
            "openai_subscription_token": None,
            "google_api_key": None,
            "gemini_subscription_token": "__neoswarm_secret_unchanged__",
            "openrouter_api_key": None,
            "copilot_github_token": None,
            "copilot_token": "__neoswarm_secret_unchanged__",
            "custom_providers": [
                {
                    "name": "Local Gateway",
                    "base_url": "http://127.0.0.1:9000/v1",
                    "api_key": "",
                    "models": [{"id": "local-model"}],
                }
            ],
        }
    )

    assert rows == [
        ("Anthropic", True),
        ("OpenAI", True),
        ("Google", True),
        ("OpenRouter", False),
        ("Ollama", True),
        ("Copilot", True),
        ("Custom: Local Gateway", True),
    ]
