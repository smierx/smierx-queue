import httpx

from app.gitlab_client import GitLabClient


def test_issues_paginiert(monkeypatch):
    """Mehr als 100 Issues: der Client holt alle Seiten."""
    seiten = {
        1: [{"iid": i} for i in range(1, 101)],
        2: [{"iid": i} for i in range(101, 131)],
    }
    aufrufe = []

    def fake_get(url, headers=None, params=None, timeout=None):
        aufrufe.append(params["page"])
        return httpx.Response(200, json=seiten[params["page"]],
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    client = GitLabClient("https://gitlab.example.com", "token")
    issues = client.issues(42)

    assert len(issues) == 130
    assert aufrufe == [1, 2]
