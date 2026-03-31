from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.milestone_store import MilestoneStore


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


def test_query_applies_brand_region_and_year_filters_together() -> None:
    response = client.post(
        "/query",
        json={"query": "Which of Jeep brand's Vehicle is Launching in EEU region in 2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "list"
    assert len(payload["answer"]) == 2
    assert {row["brand"] for row in payload["answer"]} == {"JEEP"}
    assert {row["car_family"] for row in payload["answer"]} == {"J5O", "J-WL"}


def test_query_with_unavailable_brand_returns_no_rows_instead_of_broad_match() -> None:
    response = client.post(
        "/query",
        json={"query": "Which of Citroen brand's Vehicle is Launching in EEU region in 2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "list"
    assert payload["plan"]["filters"][-1]["field"] == "brand"
    assert payload["plan"]["filters"][-1]["value"] == "CITROEN"
    assert payload["answer"] == []


def test_query_applies_platform_filter_from_uploaded_lrp_values() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in EEU region in 2026 on STLA-L platform?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert len(payload["answer"]) == 1
    assert payload["answer"][0]["platform"] == "STLA-L"
    assert payload["answer"][0]["car_family"] == "J5O"


def test_query_applies_eea_filter_without_accidental_extra_region_filter() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in EEU region in 2026 with Atlantis High EEA?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert len(payload["answer"]) == 5
    assert {row["eea"] for row in payload["answer"]} == {"Atlantis High"}


def test_query_with_tbd_ota_does_not_accidentally_add_tbd_region_filter() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in EEU in 2026 on EMP2 platform with TBD OTA?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert all(
        not (item["field"] == "region_of_sales" and item["value"] == "TBD")
        for item in payload["plan"]["filters"]
    )
    assert len(payload["answer"]) == 2
    assert {row["car_family"] for row in payload["answer"]} == {"OV52", "P54"}


def test_active_year_filter_is_preserved_when_query_also_mentions_volume_trends() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are active in 2030 with declining volume trends?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "active_year" and item["value"] == 2030 for item in payload["plan"]["filters"])


def test_overlap_query_can_scope_to_specific_year() -> None:
    response = client.post(
        "/query",
        json={"query": "Are there months in 2026 where SOPM + MCA + MCA2 launches overlap heavily?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "launch_year" and item["value"] == 2026 for item in payload["plan"]["filters"])
    assert all(row["launch_month"].startswith("2026-") for row in payload["answer"])


def test_query_can_match_tcu_generation_from_uploaded_lrp_values() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in EEU in 2026 with TBM 2.0H TCU?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "tcu_details" and item["value"] == "TBM 2.0H" for item in payload["plan"]["filters"])
    assert {row["car_family"] for row in payload["answer"]} == {"M189", "J5O", "LD Pickup (DTe)", "J-WL"}


def test_natural_query_matches_car_family_entity() -> None:
    response = client.post(
        "/query",
        json={"query": "When is F2X launching?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "car_family" and item["value"] == "F2X" for item in payload["plan"]["filters"])
    assert payload["answer"]
    assert {row["car_family"] for row in payload["answer"]} == {"F2X"}


def test_natural_query_matches_commercial_name_entity() -> None:
    response = client.post(
        "/query",
        json={"query": "Tell me about Recon"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "commercial_name" and item["value"] == "Recon" for item in payload["plan"]["filters"])
    assert payload["answer"]
    assert {row["commercial_name"] for row in payload["answer"]} == {"Recon"}
    assert "milestone_im" in payload["answer"][0]
    assert "milestone_anchor_date" in payload["answer"][0]


def test_natural_query_can_combine_brand_and_commercial_name() -> None:
    response = client.post(
        "/query",
        json={"query": "Tell me about Jeep Recon"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "brand" and item["value"] == "JEEP" for item in payload["plan"]["filters"])
    assert any(item["field"] == "commercial_name" and item["value"] == "Recon" for item in payload["plan"]["filters"])
    assert payload["answer"]
    assert {row["brand"] for row in payload["answer"]} == {"JEEP"}
    assert {row["commercial_name"] for row in payload["answer"]} == {"Recon"}


def test_natural_query_prefers_car_family_over_program_collision() -> None:
    response = client.post(
        "/query",
        json={"query": "What launches are planned for J-WL?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "car_family" and item["value"] == "J-WL" for item in payload["plan"]["filters"])
    assert all(item["field"] != "program" for item in payload["plan"]["filters"])
    assert payload["answer"]
    assert {row["car_family"] for row in payload["answer"]} == {"J-WL"}


def test_natural_query_with_punctuated_commercial_name_avoids_region_collision() -> None:
    response = client.post(
        "/query",
        json={"query": "Give me details for Tipo, SAM: F2X"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "commercial_name" and item["value"] == "Tipo, SAM: F2X" for item in payload["plan"]["filters"])
    assert all(not (item["field"] == "region_of_sales" and item["value"] == "SAM") for item in payload["plan"]["filters"])
    assert payload["answer"]
    assert {row["commercial_name"] for row in payload["answer"]} == {"Tipo, SAM: F2X"}


def test_unknown_car_family_like_code_returns_zero_rows_instead_of_full_dataset() -> None:
    response = client.post(
        "/query",
        json={"query": "Tell me about B618"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "car_family" and item["value"] == "B618" for item in payload["plan"]["filters"])
    assert payload["answer"] == []


def test_query_matches_multiple_tcu_components_for_vehicle() -> None:
    response = client.post(
        "/query",
        json={"query": "Does F1H comes with R2eX and ATB4Sv2 TCUs?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "car_family" and item["value"] == "F1H" for item in payload["plan"]["filters"])
    assert any(item["field"] == "tcu_details" and item["value"] == "R2eX" for item in payload["plan"]["filters"])
    assert any(item["field"] == "tcu_details" and item["value"] == "ATB4S V2" for item in payload["plan"]["filters"])
    assert {row["region_of_sales"] for row in payload["answer"]} == {"SAM"}


def test_query_can_rule_out_region_for_tcu_component_combo() -> None:
    response = client.post(
        "/query",
        json={"query": "Is F1H being sold in MEA region with R2eX TCU?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "region_of_sales" and item["value"] == "MEA" for item in payload["plan"]["filters"])
    assert any(item["field"] == "tcu_details" and item["value"] == "R2eX" for item in payload["plan"]["filters"])
    assert payload["answer"] == []


def test_query_matches_infotainment_component_without_fota_false_positive() -> None:
    response = client.post(
        "/query",
        json={"query": "Which Vehicles are Launched with PCSA Infotainments?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert any(item["field"] == "infotainment_details" and item["value"] == "PCSA (SPS)" for item in payload["plan"]["filters"])
    assert all(not (item["field"] == "ota" and item["value"] == "FOTA") for item in payload["plan"]["filters"])
    assert {row["car_family"] for row in payload["answer"]} == {"K0 Combi", "F1H"}


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


def test_query_derives_milestones_from_sopm_with_nearest_monday_rounding() -> None:
    response = client.post(
        "/query",
        json={"query": "When is IM for F2X?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["milestone_anchor"] == "sopm"
    assert payload["plan"]["milestone_columns"] == ["milestone_im"]
    assert payload["answer"]
    first_row = payload["answer"][0]
    assert first_row["car_family"] == "F2X"
    assert first_row["milestone_im"] == "2021-06-28T00:00:00"
    assert first_row["milestone_anchor_label"] == "SOPM"


def test_query_can_derive_selected_milestones_from_mca_anchor() -> None:
    response = client.post(
        "/query",
        json={"query": "What are the PM and CM milestones for F2X at MCA?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["milestone_anchor"] == "mca_sopm"
    assert payload["plan"]["milestone_columns"] == ["milestone_pm", "milestone_cm"]
    assert any(item["field"] == "has_mca" and item["value"] is True for item in payload["plan"]["filters"])
    assert payload["answer"]
    first_row = payload["answer"][0]
    assert first_row["car_family"] == "F2X"
    assert first_row["milestone_anchor_label"] == "MCA"
    assert first_row["milestone_pm"] == "2022-11-28T00:00:00"
    assert first_row["milestone_cm"] == "2023-06-19T00:00:00"


def test_query_can_return_milestone_deliverables_alongside_milestone_date() -> None:
    response = client.post(
        "/query",
        json={"query": "What are the X0 deliverables for F2X, and When is the X0 for F2X?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["milestone_columns"] == ["milestone_x0"]
    assert payload["plan"]["milestone_deliverable_codes"] == ["X0"]
    assert len([item for item in payload["plan"]["filters"] if item["field"] == "car_family" and item["value"] == "F2X"]) == 1
    first_row = payload["answer"][0]
    assert first_row["milestone_x0"] == "2025-02-10T00:00:00"
    assert first_row["deliverable_milestone_code"] == "X0"
    assert "Functional integration readiness monitored." in first_row["deliverable_governance_communication"]
    assert "Engineering / TPM." == first_row["deliverable_ownership"]


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


def test_milestone_deliverables_seed_from_database() -> None:
    response = client.get("/milestones/deliverables")
    payload = response.json()

    assert response.status_code == 200
    assert payload["items"]
    assert payload["items"][0]["milestone_code"] == "POST_IM"
    assert any(item["milestone_code"] == "SOPM" for item in payload["items"])


def test_milestone_deliverables_are_updateable_without_code_changes() -> None:
    original_store = main_module.milestone_store
    with TemporaryDirectory() as temp_dir:
        temp_db = Path(temp_dir) / "milestones.duckdb"
        main_module.milestone_store = MilestoneStore(duckdb_path=temp_db)
        try:
            update_response = client.put(
                "/milestones/deliverables/PM",
                json={
                    "risks": "Updated risk text for test coverage.",
                    "ownership": "Updated Owner",
                },
            )
            updated = update_response.json()

            fetch_response = client.get("/milestones/deliverables/PM")
            fetched = fetch_response.json()

            assert update_response.status_code == 200
            assert updated["milestone_code"] == "PM"
            assert updated["risks"] == "Updated risk text for test coverage."
            assert updated["ownership"] == "Updated Owner"
            assert fetch_response.status_code == 200
            assert fetched["risks"] == "Updated risk text for test coverage."
            assert fetched["ownership"] == "Updated Owner"
        finally:
            main_module.milestone_store = original_store
