from pathlib import Path

from sneaker_market_maker.research.acceptance import verify_acceptance


def test_acceptance_checklist_manifest() -> None:
    verify_acceptance(Path("docs/research/acceptance-checklist.md"))
