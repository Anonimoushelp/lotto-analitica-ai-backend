from pathlib import Path


REQUIREMENTS = Path("requirements.txt").read_text(encoding="utf-8")


def test_unused_runtime_dependency_groups_are_not_declared():
    for package in ("celery", "amqp", "billiard", "kombu", "vine", "PyYAML"):
        assert f"{package}==" not in REQUIREMENTS
