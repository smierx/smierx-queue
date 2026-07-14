"""Bidirektionaler Sync Task ↔ GitLab-Issue.

Regeln:
- Offene Issues der gewählten Projekte werden Tasks (Dedup über Issue-Id).
- Geschlossene Issues räumen ihren Task ab, die Queue ist eine Ausführungsliste.
- Titel: last-write-wins über die Zeitstempel, bei beidseitiger Änderung gewinnt
  GitLab und der Fall landet als Hinweis im Ergebnis.
- Tags spiegeln sich als GitLab-Labels `queue::<tag>`, fremde Labels bleiben unangetastet.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.gitlab_client import GitLabClient
from app.models import VALID_TAGS, GitlabConnection, GitlabLink, TagEvent, Task, TaskTag

LABEL_PREFIX = "queue::"


def _utc_naiv(wert: datetime) -> datetime:
    """Alle Zeitstempel als UTC ohne tzinfo vergleichen.

    GitLab liefert UTC mit Offset, die DB-Defaults (CURRENT_TIMESTAMP) sind UTC-naiv.
    """
    if wert.tzinfo is not None:
        return wert.astimezone(timezone.utc).replace(tzinfo=None)
    return wert


def _jetzt_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tags_aus_labels(labels: list[str]) -> list[str]:
    tags = [label.removeprefix(LABEL_PREFIX) for label in labels if label.startswith(LABEL_PREFIX)]
    return [t for t in tags if t in VALID_TAGS]


def _labels_setzen(client: GitLabClient, link: GitlabLink, task: Task) -> None:
    """Nur queue::-Labels anfassen, alles andere gehört dem Issue."""
    soll = {f"{LABEL_PREFIX}{tag}" for tag in task.tags}
    alle_moeglichen = {f"{LABEL_PREFIX}{tag}" for tag in VALID_TAGS}
    client.issue_aktualisieren(
        link.projekt_id,
        link.issue_iid,
        add_labels=",".join(sorted(soll)),
        remove_labels=",".join(sorted(alle_moeglichen - soll)),
    )


def _tags_ersetzen(task: Task, tags: list[str]) -> None:
    alt = set(task.tags)
    neu = set(tags)
    for zeile in [z for z in task.tag_zeilen if z.tag not in neu]:
        task.tag_zeilen.remove(zeile)
        task.historie.append(TagEvent(tag=zeile.tag, aktion="entfernt"))
    for tag in sorted(neu - alt):
        task.tag_zeilen.append(TaskTag(tag=tag))
        task.historie.append(TagEvent(tag=tag, aktion="gesetzt"))


def sync_ausfuehren(db: Session, user: str, client: GitLabClient) -> dict:
    verbindung = db.scalar(
        select(GitlabConnection).where(GitlabConnection.user_id == user)
    )
    assert verbindung is not None  # Router prüft das vorher.

    links = {
        (link.projekt_id, link.issue_iid): link
        for link in db.scalars(select(GitlabLink).where(GitlabLink.user_id == user))
    }
    ergebnis = {
        "importiert": 0,
        "aktualisiert_lokal": 0,
        "gepusht": 0,
        "geschlossen": 0,
        "konflikte": [],
    }

    for projekt_id in verbindung.projekt_ids:
        for issue in client.issues(projekt_id):
            iid = issue["iid"]
            link = links.get((projekt_id, iid))

            if link is None:
                if issue["state"] != "opened":
                    continue
                max_position = db.scalar(
                    select(func.max(Task.position)).where(Task.user_id == user)
                )
                task = Task(
                    user_id=user,
                    titel=issue["title"],
                    beschreibung=issue.get("description") or "",
                    position=(max_position or 0) + 1,
                )
                tags = _tags_aus_labels(issue.get("labels", []))
                task.tag_zeilen = [TaskTag(tag=t) for t in tags]
                task.historie = [TagEvent(tag=t, aktion="gesetzt") for t in tags]
                db.add(task)
                db.flush()
                db.add(
                    GitlabLink(
                        user_id=user, task_id=task.id, projekt_id=projekt_id, issue_iid=iid
                    )
                )
                ergebnis["importiert"] += 1
                continue

            task = db.get(Task, link.task_id)

            if issue["state"] == "closed":
                db.delete(task)  # Link hängt per Cascade dran.
                ergebnis["geschlossen"] += 1
                continue

            issue_geaendert = _utc_naiv(datetime.fromisoformat(issue["updated_at"]))
            task_geaendert = _utc_naiv(task.geaendert_am)
            basis = _utc_naiv(link.zuletzt_gesynct)

            if issue_geaendert > basis and task_geaendert > basis:
                ergebnis["konflikte"].append(
                    f"Task {task.id} / Issue {projekt_id}#{iid}: beide geändert, GitLab gewinnt"
                )

            if issue_geaendert >= task_geaendert:
                if task.titel != issue["title"]:
                    task.titel = issue["title"]
                    ergebnis["aktualisiert_lokal"] += 1
                _tags_ersetzen(task, _tags_aus_labels(issue.get("labels", [])))
            else:
                client.issue_aktualisieren(link.projekt_id, link.issue_iid, title=task.titel)
                _labels_setzen(client, link, task)
                ergebnis["gepusht"] += 1

            link.zuletzt_gesynct = _jetzt_utc()

    db.commit()
    return ergebnis
