import pytest

from novel_forge_kdp.quality import QualityGate, QualityGateError


def test_quality_gate_allows_ready_review_without_blocking_issues():
    QualityGate().ensure_export_allowed({"ready_for_publication": True, "issues": [{"severity": "minor"}]})


def test_quality_gate_blocks_not_ready_review_unless_forced():
    gate = QualityGate()
    review = {"ready_for_publication": False, "issues": [{"severity": "major"}]}
    with pytest.raises(QualityGateError, match="not ready for publication"):
        gate.ensure_export_allowed(review)
    gate.ensure_export_allowed(review, force=True)


def test_quality_gate_blocks_major_ready_review_unless_forced():
    gate = QualityGate()
    review = {"ready_for_publication": True, "issues": [{"severity": "major"}]}
    with pytest.raises(QualityGateError, match="major final review issues"):
        gate.ensure_export_allowed(review)
    gate.ensure_export_allowed(review, force=True)


def test_quality_gate_validates_revised_chapter_count():
    gate = QualityGate()
    with pytest.raises(QualityGateError, match="no chapter headings"):
        gate.ensure_revised_volume_structure("本文だけ", expected_chapter_count=1)
    with pytest.raises(QualityGateError, match="chapter count mismatch"):
        gate.ensure_revised_volume_structure("## A\n\n本文\n\n## B\n", expected_chapter_count=1)
    gate.ensure_revised_volume_structure("## A\n\n本文", expected_chapter_count=1)
