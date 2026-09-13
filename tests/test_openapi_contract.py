from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


EXPECTED_PATHS = {
    "/",
    "/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/me",
    "/api/v1/auth/admin/users/{user_id}",
    "/api/v1/lotteries",
    "/api/v1/lotteries/{lottery_id}",
    "/api/v1/draws",
    "/api/v1/draws/{draw_id}",
    "/api/v1/statistics/overview",
}


def test_openapi_exposes_expected_api_surface():
    schema = app.openapi()
    assert schema["info"]["title"] == "Lotto Analítica AI"
    assert schema["info"]["version"] == "0.1.0"
    assert EXPECTED_PATHS <= set(schema["paths"])


def test_openapi_documents_parameter_constraints():
    schema = app.openapi()
    lottery_detail = schema["paths"]["/api/v1/lotteries/{lottery_id}"]["get"]
    lottery_id = next(
        parameter
        for parameter in lottery_detail["parameters"]
        if parameter["name"] == "lottery_id"
    )
    assert lottery_id["in"] == "path"
    assert lottery_id["required"] is True
    assert lottery_id["schema"]["exclusiveMinimum"] == 0

    draw_list = schema["paths"]["/api/v1/draws"]["get"]
    limit = next(
        parameter
        for parameter in draw_list["parameters"]
        if parameter["name"] == "limit"
    )
    assert limit["schema"]["minimum"] == 1
    assert limit["schema"]["maximum"] == 500

    statistics = schema["paths"]["/api/v1/statistics/overview"]["get"]
    statistics_lottery_id = next(
        parameter
        for parameter in statistics["parameters"]
        if parameter["name"] == "lottery_id"
    )
    assert statistics_lottery_id["schema"]["exclusiveMinimum"] == 0
    assert statistics_lottery_id["schema"]["maximum"] == 2_147_483_647


def test_openapi_documents_success_response_models_and_status_codes():
    schema = app.openapi()
    paths = schema["paths"]

    assert paths["/api/v1/auth/login"]["post"]["responses"]["200"]["content"]
    assert paths["/api/v1/auth/register"]["post"]["responses"]["201"]["content"]
    assert paths["/api/v1/lotteries"]["post"]["responses"]["201"]["content"]
    assert paths["/api/v1/draws"]["post"]["responses"]["201"]["content"]
    assert paths["/api/v1/lotteries/{lottery_id}"]["delete"]["responses"]["204"]
    assert paths["/api/v1/draws/{draw_id}"]["delete"]["responses"]["204"]


def test_openapi_endpoint_is_available_only_when_development_docs_are_enabled():
    response = client.get("/openapi.json")
    if app.openapi_url is None:
        assert response.status_code == 404
    else:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")


def test_docs_urls_follow_openapi_configuration():
    docs_response = client.get("/docs")
    redoc_response = client.get("/redoc")
    if app.docs_url is None:
        assert docs_response.status_code == 404
    else:
        assert docs_response.status_code == 200
    if app.redoc_url is None:
        assert redoc_response.status_code == 404
    else:
        assert redoc_response.status_code == 200
