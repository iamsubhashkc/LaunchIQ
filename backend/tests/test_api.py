from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_query_returns_distribution_for_region_question() -> None:
    response = client.post(
        "/query",
        json={
            "query": "Which Car Families are launching in the next 24 months, and how are they distributed across regions (RoS vs IPZ)?"
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "distribution"
    assert payload["plan"]["group_by"] == ["region_logic", "region_value"]
    assert isinstance(payload["answer"], list)


def test_query_marks_unsupported_for_peak_load_with_unknown_platform_taxonomy() -> None:
    response = client.post(
        "/query",
        json={
            "query": "What is the month-wise clustering of launches, and where do we see peak load on platform (SSDP/SPACE/SCEP)?"
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "unsupported"
    assert payload["plan"]["unsupported_reasons"]


def test_query_marks_unsupported_for_ssdp_migration_question() -> None:
    response = client.post(
        "/query",
        json={
            "query": "Are there vehicles where SOPM is near but Target SDP is still not SSDP (migration risk)?"
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "unsupported"
    assert payload["plan"]["unsupported_reasons"]


def test_query_returns_active_vehicles_for_year() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are active in 2030?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "list"
    assert payload["answer"]


def test_general_launch_query_uses_business_columns_without_default_volume() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in 2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    first_row = payload["answer"][0]
    assert "car_family" in first_row
    assert "brand" in first_row
    assert "commercial_name" in first_row
    assert "tcu_details" in first_row
    assert "infotainment_details" in first_row
    assert "ota" in first_row
    assert "launch_volume" not in first_row


def test_query_returns_volume_distribution_by_region_for_year() -> None:
    response = client.post(
        "/query",
        json={"query": "What is the total volume split by region for 2030?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "distribution"
    assert payload["answer"]


def test_query_returns_mca_launches_in_next_24_months() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles have MCA SOPM in the next 24 months?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "list"
    assert payload["plan"]["data_view"] == "launch_event"
    assert payload["answer"]


def test_query_returns_overlap_months_for_launch_events() -> None:
    response = client.post(
        "/query",
        json={"query": "Are there months where SOPM + MCA + MCA2 launches overlap heavily?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer"]
    assert "event_count" in payload["answer"][0]


def test_query_marks_stage_specific_architecture_change_as_unsupported() -> None:
    response = client.post(
        "/query",
        json={"query": "How does TCU / architecture change between SOPM and MCA?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "unsupported"
    assert payload["plan"]["unsupported_reasons"]


def test_feedback_persists_learning_record() -> None:
    response = client.post(
        "/feedback",
        json={
            "query": "How many vehicles lack FOTA/FOTA IVI capability?",
            "plan": {"intent": "count", "filters": []},
            "answer": {"value": 3},
            "rating": "helpful",
            "correction": None,
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["stored"] is True
    assert payload["record_id"]
