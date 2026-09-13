    actor = seed_user("audit-unsupported@example.com", "admin")
    with pytest.raises(ValueError, match="Unsupported audit mutation"):
        log_mutation(
            action="export",
            resource="user",
            resource_id=7,
            actor=actor,
        )
    clear_users()


def test_log_mutation_does_not_emit_unsupported_event(caplog):
    actor = seed_user("audit-noemit@example.com", "admin")
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"), pytest.raises(
        ValueError
    ):
        log_mutation(
            action="delete\nforged=true",
            resource="unknown",
            resource_id=7,
            actor=actor,
        )
    assert not any(record.name == "lotto_analitica.audit" for record in caplog.records)
    clear_users()