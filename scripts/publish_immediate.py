"""One-off: publish a stored article to test + production (used from deploy host)."""

from __future__ import annotations

import sys

from app.db.enums import ArticleStatus
from app.db.models import Article
from app.db.base import session_scope
from app.services.workflow import ArticleWorkflow


def main() -> None:
    article_id = int(sys.argv[1]) if len(sys.argv) > 1 else 462
    with session_scope() as session:
        article = session.get(Article, article_id)
        if article is None:
            raise SystemExit(f"article {article_id} missing")
        title = (article.title or "")[:60]
        print(f"before id={article.id} status={article.status} title={title!r}")
        article.status = ArticleStatus.NEEDS_REVIEW
        article.status_reason = "manual publish: owner requested immediate post"
        session.flush()
        wf = ArticleWorkflow(session)
        test = wf.publish_test(article)
        print(f"test ok={test.ok} msg={test.message}")
        if not test.ok:
            raise SystemExit(1)
        session.refresh(article)
        prod = wf.publish_now(article, require_test=True)
        print(f"prod ok={prod.ok} msg={prod.message}")
        if not prod.ok:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
