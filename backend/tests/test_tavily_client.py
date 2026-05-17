from unittest.mock import patch, MagicMock
from app.utils.tavily_client import TavilyClient


def test_search_returns_results():
    client = TavilyClient(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"title": "Article A", "url": "https://example.com/a", "content": "Some content A"},
            {"title": "Article B", "url": "https://example.com/b", "content": "Some content B"},
        ]
    }
    with patch("app.utils.tavily_client.requests.post", return_value=mock_resp) as mock_post:
        results = client.search("test query", max_results=2)

    assert len(results) == 2
    assert results[0]["title"] == "Article A"
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["content"] == "Some content A"
    call_json = mock_post.call_args.kwargs["json"]
    assert call_json["query"] == "test query"
    assert call_json["max_results"] == 2
    assert "api_key" not in call_json
    call_headers = mock_post.call_args.kwargs["headers"]
    assert call_headers["Authorization"] == "Bearer test-key"


def test_search_returns_empty_on_api_error():
    client = TavilyClient(api_key="test-key")
    with patch("app.utils.tavily_client.requests.post", side_effect=Exception("network error")):
        results = client.search("test query")
    assert results == []


def test_search_strips_missing_fields():
    client = TavilyClient(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [{"url": "https://example.com/c"}]  # no title or content
    }
    with patch("app.utils.tavily_client.requests.post", return_value=mock_resp):
        results = client.search("q")
    assert results[0]["title"] == ""
    assert results[0]["content"] == ""
    assert results[0]["url"] == "https://example.com/c"
