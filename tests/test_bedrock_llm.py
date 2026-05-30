"""Amazon Bedrock Converse backend (mocked boto3)."""

from unittest.mock import MagicMock, patch

from newton3.services.llm_explain import (
    bedrock_configured,
    enrich_with_llm,
    llm_feature_flags,
)


def test_bedrock_configured_requires_model(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_BACKEND", "bedrock")
    monkeypatch.delenv("NEWTON3_BEDROCK_MODEL_ID", raising=False)
    assert bedrock_configured() is False
    monkeypatch.setenv("NEWTON3_BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")
    assert bedrock_configured() is True


def test_llm_feature_flags_bedrock(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_BACKEND", "bedrock")
    monkeypatch.setenv("NEWTON3_BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")
    monkeypatch.setenv("NEWTON3_LLM_AUTO", "0")
    monkeypatch.setenv("NEWTON3_BEDROCK_REGION", "eu-west-1")
    f = llm_feature_flags()
    assert f["llm_explain_env"] is True
    assert f["llm_backend"] == "bedrock"
    assert "haiku" in f["llm_bedrock_model"]
    assert f["llm_bedrock_region"] == "eu-west-1"


def test_enrich_bedrock_converse(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_BACKEND", "bedrock")
    monkeypatch.setenv("NEWTON3_BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")
    monkeypatch.setenv("NEWTON3_LLM_AUTO", "0")
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)

    ranking = [{"rank": 1, "user_id": "alice", "explain": "rank=1: ok"}]
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Alice ranks first because of behaviour score."}]}},
    }

    with patch("boto3.client", return_value=fake_client) as mock_client:
        out = enrich_with_llm(ranking, context="Summarize briefly.")

    assert out["mode"] == "bedrock"
    assert "Alice" in out["text"]
    assert out["llm_source"] == "bedrock"
    mock_client.assert_called_once()
    call_kw = fake_client.converse.call_args[1]
    assert call_kw["modelId"] == "anthropic.claude-3-5-haiku-20241022-v1:0"
    assert call_kw["messages"][-1]["role"] == "user"


def test_local_still_template_without_bedrock(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_AUTO", "0")
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)
    monkeypatch.delenv("NEWTON3_LLM_BACKEND", raising=False)
    monkeypatch.delenv("NEWTON3_BEDROCK_MODEL_ID", raising=False)
    out = enrich_with_llm([{"rank": 1, "user_id": "a", "explain": "x"}], context="")
    assert out["mode"] == "template"
