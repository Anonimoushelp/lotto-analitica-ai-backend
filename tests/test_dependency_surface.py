REQUIREMENTS = open("requirements.txt", encoding="utf-8").read()


def test_unused_runtime_dependency_groups_are_not_declared():
    for package in ("celery", "amqp", "billiard", "kombu", "vine", "PyYAML"):
        assert f"{package}==" not in REQUIREMENTS
