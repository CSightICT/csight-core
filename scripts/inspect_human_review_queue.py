"""Print non-sensitive aggregate counts for the local human-review queue."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import func, select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import HumanReviewTaskModel
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        rows = session.execute(
            select(
                HumanReviewTaskModel.task_type,
                HumanReviewTaskModel.priority,
                HumanReviewTaskModel.status,
                func.count(HumanReviewTaskModel.id),
            )
            .group_by(
                HumanReviewTaskModel.task_type,
                HumanReviewTaskModel.priority,
                HumanReviewTaskModel.status,
            )
            .order_by(
                HumanReviewTaskModel.priority.desc(),
                HumanReviewTaskModel.task_type,
                HumanReviewTaskModel.status,
            )
        ).all()
    print(
        json.dumps(
            [
                {"task_type": task_type, "priority": priority, "status": status, "count": count}
                for task_type, priority, status, count in rows
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
