
    monkeypatch.setattr(
        "app.repositories.lottery_draw_repository.LotteryDrawRepository.delete",
        raise_integrity,
    )
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.log_mutation",
        lambda **kwargs: audit_events.append(kwargs),
    )

    response = client.delete(
        f"/api/v1/draws/{draw.id}",
        headers=auth_header(user),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Lottery draw cannot be deleted"
    assert audit_events == []