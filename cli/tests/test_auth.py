from cli import _auth_provider_rows, _oauth_state_label, _oauth_state_map


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


def test_oauth_state_map_reads_provider_states():
    states = _oauth_state_map(
        {
            "providers": [
                {"provider": "anthropic", "state": "connected"},
                {"provider": "openai", "state": "pending"},
                "not-a-dict",
            ]
        }
    )

    assert states == {"anthropic": "connected", "openai": "pending"}
    assert _oauth_state_map(None) == {}


def test_oauth_state_labels_never_include_secrets():
    assert _oauth_state_label("connected") == "✓ Connected"
    assert _oauth_state_label("pending") == "Pending"
    assert _oauth_state_label("expired") == "Expired"
    assert _oauth_state_label("failed") == "Failed"
    assert _oauth_state_label("") == "Not linked"
    # Unknown states fall back to a neutral label rather than echoing input.
    assert _oauth_state_label("sk-ant-secret") == "Not linked"
