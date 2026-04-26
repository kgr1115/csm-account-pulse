"""Model invariants — the Pydantic guards that protect the LLM-output contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import BriefingBullet, NpsResponse


def test_briefing_bullet_requires_at_least_one_citation() -> None:
    with pytest.raises(ValidationError):
        BriefingBullet(text="A bullet with no citation", citations=[])


def test_nps_bucket_classification() -> None:
    from datetime import datetime
    base = datetime(2026, 1, 1, 12)
    assert NpsResponse(account_id="ACC-X", submitted_at=base, score=10).bucket == "promoter"
    assert NpsResponse(account_id="ACC-X", submitted_at=base, score=9).bucket == "promoter"
    assert NpsResponse(account_id="ACC-X", submitted_at=base, score=8).bucket == "passive"
    assert NpsResponse(account_id="ACC-X", submitted_at=base, score=7).bucket == "passive"
    assert NpsResponse(account_id="ACC-X", submitted_at=base, score=6).bucket == "detractor"
    assert NpsResponse(account_id="ACC-X", submitted_at=base, score=0).bucket == "detractor"


def test_nps_score_bounds_enforced() -> None:
    from datetime import datetime
    base = datetime(2026, 1, 1, 12)
    with pytest.raises(ValidationError):
        NpsResponse(account_id="ACC-X", submitted_at=base, score=11)
    with pytest.raises(ValidationError):
        NpsResponse(account_id="ACC-X", submitted_at=base, score=-1)
