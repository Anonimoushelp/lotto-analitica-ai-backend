def test_unused_runtime_dependency_groups_are_not_declared():
    with open("requirements.txt", encoding="utf-8") as requirements_file:
        requirements = requirements_file.read()

    for package in ("celery", "amqp", "billiard", "kombu", "vine", "PyYAML"):
        assert f"{package}==" not in requirements
