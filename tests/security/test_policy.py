import json
from pathlib import Path


def test_release_scan_policy_blocks_high_and_critical_findings() -> None:
    policy = json.loads(Path("tests/security/policy.json").read_text())
    assert policy["dependency_scan"]["fail_on"] == ["high", "critical"]
    assert policy["image_scan"]["fail_on"] == ["high", "critical"]
    assert policy["image_scan"]["ignore_unfixed"] is True
