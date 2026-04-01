from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
import pandas as pd

import app.main as main_module
from app.data_loader import LaunchDataLoader
from app.learning import LearningStore
from app.main import app
from app.milestone_store import MilestoneStore
from app.planner import Planner


client = TestClient(app)


def _loaded_frame():
    return LaunchDataLoader().load().frame.copy()


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


def test_query_marks_unsupported_for_low_signal_nonsense_input() -> None:
    response = client.post(
        "/query",
        json={"query": "Blah"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "unsupported"
    assert payload["plan"]["unsupported_reasons"]


def test_query_marks_unsupported_for_ungrounded_launch_word_only() -> None:
    response = client.post(
        "/query",
        json={"query": "launches"},
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
    assert payload["plan"]["data_view"] == "launch_event"
    first_row = payload["answer"][0]
    assert "car_family" in first_row
    assert "brand" in first_row
    assert "commercial_name" in first_row
    assert "tcu_details" in first_row
    assert "infotainment_details" in first_row
    assert "ota" in first_row
    assert "launch_stage" in first_row
    assert "launch_date" in first_row
    assert "milestone_im" in first_row
    assert "milestone_anchor_label" in first_row
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
    assert payload["plan"]["data_view"] == "launch_event"
    assert len(payload["answer"]) == 3
    assert {row["brand"] for row in payload["answer"]} == {"JEEP"}
    assert {row["car_family"] for row in payload["answer"]} == {"J516", "J5O", "J-WL"}


def test_query_can_match_multiple_regions_with_or_semantics() -> None:
    response = client.post(
        "/query",
        json={"query": "Which Jeep vehicles are launching in IAP and MEA regions in 2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["data_view"] == "launch_event"
    assert any(
        item["field"] == "region_of_sales" and item["operator"] == "contains_any" and item["value"] == ["IAP", "MEA"]
        for item in payload["plan"]["filters"]
    )
    assert any(item["field"] == "brand" and item["value"] == "JEEP" for item in payload["plan"]["filters"])
    assert payload["answer"]
    assert {row["region_of_sales"] for row in payload["answer"]}.issubset({"IAP", "MEA"})
    assert {row["car_family"] for row in payload["answer"]} == {"J550", "J5O", "J516", "J-WL"}


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
    assert payload["plan"]["data_view"] == "launch_event"
    assert len(payload["answer"]) == 8
    assert {row["eea"] for row in payload["answer"]} == {"Atlantis High"}
    assert {row["car_family"] for row in payload["answer"]} == {"M189", "J5O", "LD Pickup (DTe)", "M182", "J-WL"}


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
    assert payload["plan"]["data_view"] == "launch_event"
    assert len(payload["answer"]) == 3
    assert {row["car_family"] for row in payload["answer"]} == {"OV51", "OV52", "P54"}


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
    assert payload["plan"]["data_view"] == "launch_event"
    assert {row["car_family"] for row in payload["answer"]} == {"M189", "J5O", "LD Pickup (DTe)", "M182", "J-WL"}


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
    assert all(not row.get("mca_sopm") for row in payload["answer"])


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
    assert any(
        item["field"] == "tcu_details"
        and item["operator"] == "stack_contains_any"
        and set(item["value"]) == {"R2eX", "ATB4S V2"}
        for item in payload["plan"]["filters"]
    )
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


def test_query_returns_exact_tcu_volume_for_year() -> None:
    frame = _loaded_frame()
    mask = frame["tcu_details"].fillna("").str.lower().str.contains(r"(?:^|,\s*)tbm\ 2\.0(?:\s*\([^)]*\))?(?:,\s*|$)", regex=True)
    expected = int(round(frame.loc[mask & (frame["volume_2026"] > 0), "volume_2026"].sum()))

    response = client.post(
        "/query",
        json={"query": "What is the Volume of TBM 2.0 vehicles in 2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "count"
    assert payload["plan"]["metric"] == "volume_2026"
    assert any(item["field"] == "tcu_details" and item["operator"] == "stack_contains" and item["value"] == "TBM 2.0" for item in payload["plan"]["filters"])
    assert payload["answer"]["value"] == expected


def test_query_returns_multi_tcu_volume_with_or_semantics_for_year() -> None:
    frame = _loaded_frame()
    stack_text = frame["tcu_details"].fillna("").str.lower()
    mask = (
        stack_text.str.contains(r"(?:^|,\s*)tbm\ 2\.0(?:\s*\([^)]*\))?(?:,\s*|$)", regex=True)
        | stack_text.str.contains(r"(?:^|,\s*)tbm\ 2\.0h(?:\s*\([^)]*\))?(?:,\s*|$)", regex=True)
    )
    expected = int(round(frame.loc[mask & (frame["volume_2026"] > 0), "volume_2026"].sum()))

    response = client.post(
        "/query",
        json={"query": "What is the Volume of TBM 2.0 and TBM 2.0H vehicles in 2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "count"
    assert any(
        item["field"] == "tcu_details"
        and item["operator"] == "stack_contains_any"
        and set(item["value"]) == {"TBM 2.0", "TBM 2.0H"}
        for item in payload["plan"]["filters"]
    )
    assert payload["answer"]["value"] == expected


def test_query_returns_brand_launch_volume_for_quarter() -> None:
    frame = _loaded_frame()
    sopm = frame["sopm"]
    mask = (frame["brand"] == "JEEP") & (sopm >= pd.Timestamp("2026-04-01")) & (sopm < pd.Timestamp("2026-07-01"))
    expected = int(round(frame.loc[mask, "launch_volume"].sum()))

    response = client.post(
        "/query",
        json={"query": "What is the Volume of Jeep Vehicles in 26Q2?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "count"
    assert payload["plan"]["metric"] == "launch_volume"
    assert any(item["field"] == "brand" and item["value"] == "JEEP" for item in payload["plan"]["filters"])
    assert any(item["field"] == "sopm" and item["operator"] == ">=" and item["value"] == "2026-04-01" for item in payload["plan"]["filters"])
    assert any(item["field"] == "sopm" and item["operator"] == "<" and item["value"] == "2026-07-01" for item in payload["plan"]["filters"])
    assert payload["answer"]["value"] == expected


def test_query_returns_ranked_vehicle_volume_distribution_for_year() -> None:
    frame = _loaded_frame()
    expected = (
        frame.loc[frame["volume_2026"] > 0, ["car_family", "brand", "commercial_name", "volume_2026"]]
        .groupby(["car_family", "brand", "commercial_name"], as_index=False)["volume_2026"]
        .sum()
        .sort_values(["volume_2026", "car_family", "commercial_name"], ascending=[False, True, True])
        .iloc[0]
    )

    response = client.post(
        "/query",
        json={"query": "Which vehicles have the highest launch volume in 2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "distribution"
    assert payload["plan"]["data_view"] == "vehicle"
    assert payload["plan"]["group_by"] == ["car_family", "brand", "commercial_name"]
    first = payload["answer"][0]
    assert first["car_family"] == expected["car_family"]
    assert first["brand"] == expected["brand"]
    assert first["commercial_name"] == expected["commercial_name"]
    assert int(round(first["value"])) == int(round(expected["volume_2026"]))


def test_query_returns_launch_volume_distribution_by_ros_for_year() -> None:
    frame = _loaded_frame()
    expected = (
        frame.loc[frame["volume_2026"] > 0, ["region_of_sales", "volume_2026"]]
        .groupby("region_of_sales", as_index=False)["volume_2026"]
        .sum()
        .sort_values(["volume_2026", "region_of_sales"], ascending=[False, True])
        .reset_index(drop=True)
    )

    response = client.post(
        "/query",
        json={"query": "Show launch volume by RoS in 2026"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "distribution"
    assert payload["plan"]["group_by"] == ["region_of_sales"]
    assert [row["region_of_sales"] for row in payload["answer"][:5]] == expected["region_of_sales"].head(5).tolist()
    assert [int(round(row["value"])) for row in payload["answer"][:5]] == [int(round(value)) for value in expected["volume_2026"].head(5).tolist()]


def test_query_compares_tcu_launch_volumes_for_year() -> None:
    frame = _loaded_frame()
    stack_text = frame["tcu_details"].fillna("").str.lower()
    expected_tbm20 = int(
        round(
            frame.loc[
                stack_text.str.contains(r"(?:^|,\s*)tbm\ 2\.0(?:\s*\([^)]*\))?(?:,\s*|$)", regex=True) & (frame["volume_2026"] > 0),
                "volume_2026",
            ].sum()
        )
    )
    expected_tbm20h = int(
        round(
            frame.loc[
                stack_text.str.contains(r"(?:^|,\s*)tbm\ 2\.0h(?:\s*\([^)]*\))?(?:,\s*|$)", regex=True) & (frame["volume_2026"] > 0),
                "volume_2026",
            ].sum()
        )
    )

    response = client.post(
        "/query",
        json={"query": "Compare between TBM2.0 and TBM 2.0H Launch volumes in 2026"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["answer_type"] == "distribution"
    assert payload["plan"]["group_by"] == ["comparison_value"]
    assert payload["plan"]["metric"] == "volume_2026"
    pairs = {row["comparison_value"]: int(round(row["value"])) for row in payload["answer"]}
    assert pairs == {"TBM 2.0": expected_tbm20, "TBM 2.0H": expected_tbm20h}


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


def test_query_parses_quarter_launch_window_deterministically() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in 26Q4?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["data_view"] == "launch_event"
    assert any(item["field"] == "launch_date" and item["operator"] == ">=" and item["value"] == "2026-10-01" for item in payload["plan"]["filters"])
    assert any(item["field"] == "launch_date" and item["operator"] == "<" and item["value"] == "2027-01-01" for item in payload["plan"]["filters"])
    assert all(row["launch_date"].startswith(("2026-10", "2026-11", "2026-12")) for row in payload["answer"])


def test_query_with_explicit_sopm_in_quarter_uses_launch_window_view() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles have SOPM in 26Q4?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["data_view"] == "launch_event"
    assert any(item["field"] == "launch_stage" and item["value"] == "SOPM" for item in payload["plan"]["filters"])
    assert any(item["field"] == "launch_date" and item["operator"] == ">=" and item["value"] == "2026-10-01" for item in payload["plan"]["filters"])
    assert any(item["field"] == "launch_date" and item["operator"] == "<" and item["value"] == "2027-01-01" for item in payload["plan"]["filters"])
    assert all(row["launch_stage"] == "SOPM" for row in payload["answer"])


def test_query_filters_sop_6_by_requested_quarter() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles has SOP -6 in 26Q3?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["data_view"] == "vehicle"
    assert payload["plan"]["milestone_columns"] == ["milestone_sop_6"]
    assert any(item["field"] == "milestone_window" for item in payload["plan"]["filters"])
    assert payload["answer"] == []


def test_query_filters_shrm_by_requested_quarter() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles has SHRM in 26Q3?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["milestone_columns"] == ["milestone_shrm"]
    assert any(item["field"] == "milestone_window" for item in payload["plan"]["filters"])
    assert payload["answer"] == []


def test_query_filters_x0_by_requested_quarter() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles has X0 in 26Q2?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["milestone_columns"] == ["milestone_x0"]
    assert any(item["field"] == "milestone_window" for item in payload["plan"]["filters"])
    assert payload["answer"] == []


def test_query_can_return_positive_milestone_window_matches() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles has X0 in 25Q4?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["milestone_columns"] == ["milestone_x0"]
    assert any(item["field"] == "milestone_window" for item in payload["plan"]["filters"])
    assert payload["answer"]
    assert all(row["milestone_x0"].startswith(("2025-10", "2025-11", "2025-12")) for row in payload["answer"])


def test_query_parses_half_year_launch_window_deterministically() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in 27H2?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["data_view"] == "launch_event"
    assert any(item["field"] == "launch_date" and item["operator"] == ">=" and item["value"] == "2027-07-01" for item in payload["plan"]["filters"])
    assert any(item["field"] == "launch_date" and item["operator"] == "<" and item["value"] == "2028-01-01" for item in payload["plan"]["filters"])
    assert payload["answer"] == []


def test_query_parses_month_launch_window_deterministically() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in April 2028?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["data_view"] == "launch_event"
    assert any(item["field"] == "launch_date" and item["operator"] == ">=" and item["value"] == "2028-04-01" for item in payload["plan"]["filters"])
    assert any(item["field"] == "launch_date" and item["operator"] == "<" and item["value"] == "2028-05-01" for item in payload["plan"]["filters"])
    assert payload["answer"] == []


def test_query_parses_cy_launch_window_deterministically() -> None:
    response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in CY2026?"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["plan"]["data_view"] == "launch_event"
    assert any(item["field"] == "launch_date" and item["operator"] == ">=" and item["value"] == "2026-01-01" for item in payload["plan"]["filters"])
    assert any(item["field"] == "launch_date" and item["operator"] == "<" and item["value"] == "2027-01-01" for item in payload["plan"]["filters"])
    assert payload["answer"]


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


def test_feedback_report_summarizes_learning_records() -> None:
    original_store = main_module.learning_store
    original_planner = main_module.planner
    with TemporaryDirectory() as temp_dir:
        temp_store = LearningStore(
            jsonl_path=Path(temp_dir) / "learning.jsonl",
            duckdb_path=Path(temp_dir) / "learning.duckdb",
        )
        main_module.learning_store = temp_store
        main_module.planner = Planner(learning_store=temp_store)
        try:
            client.post(
                "/feedback",
                json={
                    "query": "Which vehicles are launching in 26Q4?",
                    "plan": {"intent": "list", "filters": []},
                    "answer": [{"car_family": "F2X"}],
                    "rating": "incorrect",
                    "correction": "This should have used launch_event output.",
                },
            )
            client.post(
                "/feedback",
                json={
                    "query": "Tell me about Jeep Recon",
                    "plan": {"intent": "list", "filters": []},
                    "answer": [{"car_family": "J-RC"}],
                    "rating": "helpful",
                    "correction": None,
                },
            )
            report_response = client.get("/feedback/report")
            report = report_response.json()

            assert report_response.status_code == 200
            assert report["total_feedback"] == 2
            assert report["helpful_count"] == 1
            assert report["incorrect_count"] == 1
            assert report["needs_more_detail_count"] == 0
            assert "This should have used launch_event output." in report["top_corrections"]
            assert len(report["recent_feedback"]) == 2
        finally:
            main_module.learning_store = original_store
            main_module.planner = original_planner


def test_export_endpoint_returns_excel_workbook() -> None:
    query_response = client.post(
        "/query",
        json={"query": "Which vehicles are launching in 26Q4?"},
    )
    query_payload = query_response.json()

    export_response = client.post(
        "/export",
        json={
            "query": query_payload["query"],
            "plan": query_payload["plan"],
            "answer_type": query_payload["answer_type"],
            "answer": query_payload["answer"],
        },
    )

    assert query_response.status_code == 200
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert export_response.content[:2] == b"PK"


def test_hybrid_planner_can_override_weak_intent_signal(monkeypatch) -> None:
    monkeypatch.setenv("LAUNCHIQ_PLANNER_MODE", "hybrid")
    monkeypatch.setenv("LAUNCHIQ_LLM_PROVIDER", "openai")
    planner = Planner()
    monkeypatch.setattr(
        planner,
        "_interpret_with_provider",
        lambda query, feedback_context=None: {
            "intent": "count",
            "data_view": "vehicle",
            "confidence": 0.93,
            "reasoning": "User asks for a metric-style total rather than a row list.",
        },
    )

    plan = planner.build_plan("Vehicles in 2026")

    assert plan.intent == "count"
    assert "Hybrid assist" in plan.reasoning_summary
    assert plan.planner_diagnostics is not None
    assert plan.planner_diagnostics.llm_suggestion is not None
    assert "intent" in plan.planner_diagnostics.llm_suggestion.accepted_overrides


def test_hybrid_planner_preserves_strong_heuristics_against_bad_override(monkeypatch) -> None:
    monkeypatch.setenv("LAUNCHIQ_PLANNER_MODE", "hybrid")
    monkeypatch.setenv("LAUNCHIQ_LLM_PROVIDER", "openai")
    planner = Planner()
    monkeypatch.setattr(
        planner,
        "_interpret_with_provider",
        lambda query, feedback_context=None: {
            "intent": "list",
            "data_view": "vehicle",
            "confidence": 0.99,
            "reasoning": "Incorrect override for regression protection.",
        },
    )

    plan = planner.build_plan("How many vehicles have MCA in 2026?")

    assert plan.intent == "count"
    assert plan.data_view == "launch_event"
    assert "Hybrid assist" not in plan.reasoning_summary
    assert plan.planner_diagnostics is not None
    assert plan.planner_diagnostics.llm_suggestion is not None
    assert plan.planner_diagnostics.llm_suggestion.accepted_overrides == []


def test_hybrid_planner_can_force_launch_event_window_for_weak_phrasing(monkeypatch) -> None:
    monkeypatch.setenv("LAUNCHIQ_PLANNER_MODE", "hybrid")
    monkeypatch.setenv("LAUNCHIQ_LLM_PROVIDER", "openai")
    planner = Planner()
    monkeypatch.setattr(
        planner,
        "_interpret_with_provider",
        lambda query, feedback_context=None: {
            "intent": "list",
            "data_view": "launch_event",
            "confidence": 0.91,
            "reasoning": "This is a launch-window query even though it does not say launching explicitly.",
        },
    )

    plan = planner.build_plan("Show vehicles planned in 26Q4")

    assert plan.data_view == "launch_event"
    assert any(item.field == "launch_date" and item.operator == ">=" and item.value == "2026-10-01" for item in plan.filters)
    assert any(item.field == "launch_date" and item.operator == "<" and item.value == "2027-01-01" for item in plan.filters)
    assert "Hybrid assist" in plan.reasoning_summary
    assert plan.planner_diagnostics is not None
    assert plan.planner_diagnostics.query_frame == "launch_window"


def test_planner_attaches_diagnostics_for_heuristic_path() -> None:
    plan = Planner().build_plan("Which vehicles are launching in 2026?")

    assert plan.planner_diagnostics is not None
    assert plan.planner_diagnostics.query_frame == "launch_window"
    assert plan.planner_diagnostics.grounding_status == "grounded"
    assert plan.planner_diagnostics.heuristic_baseline.data_view == "launch_event"
    assert plan.planner_diagnostics.final_resolved_plan.data_view == "launch_event"


def test_planner_mode_override_can_force_heuristic(monkeypatch) -> None:
    monkeypatch.setenv("LAUNCHIQ_PLANNER_MODE", "hybrid")
    monkeypatch.setenv("LAUNCHIQ_LLM_PROVIDER", "openai")
    planner = Planner()
    monkeypatch.setattr(
        planner,
        "_interpret_with_provider",
        lambda query, feedback_context=None: {
            "intent": "count",
            "data_view": "vehicle",
            "confidence": 0.95,
            "reasoning": "Would normally override if hybrid were active.",
        },
    )

    plan = planner.build_plan("Vehicles in 2026", mode_override="heuristic")

    assert plan.intent == "list"
    assert plan.planner_diagnostics is not None
    assert any("Planner mode requested by UI: heuristic." == note for note in plan.planner_diagnostics.decision_notes)
    assert plan.planner_diagnostics.llm_suggestion is None


def test_planner_diagnostics_include_relevant_feedback_context() -> None:
    with TemporaryDirectory() as temp_dir:
        store = LearningStore(
            jsonl_path=Path(temp_dir) / "learning.jsonl",
            duckdb_path=Path(temp_dir) / "learning.duckdb",
        )
        store.store_feedback(
            query="Which vehicles have SOPM in 26Q4?",
            plan={"intent": "list", "data_view": "launch_event"},
            answer=[{"car_family": "F2X"}],
            rating="incorrect",
            correction="Use launch-event output with SOPM stage filtering.",
        )
        planner = Planner(learning_store=store)

        plan = planner.build_plan("Which vehicles have SOPM in 26Q4?")

        assert plan.planner_diagnostics is not None
        assert plan.planner_diagnostics.feedback_context
        assert plan.planner_diagnostics.feedback_context[0].query == "Which vehicles have SOPM in 26Q4?"
        assert plan.planner_diagnostics.feedback_context[0].rating == "incorrect"
        assert "Loaded 1 relevant feedback hint(s)" in " ".join(plan.planner_diagnostics.decision_notes)


def test_hybrid_planner_passes_feedback_context_to_interpretation(monkeypatch) -> None:
    monkeypatch.setenv("LAUNCHIQ_PLANNER_MODE", "hybrid")
    monkeypatch.setenv("LAUNCHIQ_LLM_PROVIDER", "openai")
    with TemporaryDirectory() as temp_dir:
        store = LearningStore(
            jsonl_path=Path(temp_dir) / "learning.jsonl",
            duckdb_path=Path(temp_dir) / "learning.duckdb",
        )
        store.store_feedback(
            query="Show vehicles planned in 26Q4",
            plan={"intent": "list", "data_view": "launch_event"},
            answer=[{"car_family": "F2X"}],
            rating="incorrect",
            correction="Treat this as a launch-window query.",
        )
        planner = Planner(learning_store=store)
        captured: dict[str, object] = {}

        def fake_interpret(query, feedback_context=None):
            captured["query"] = query
            captured["feedback_context"] = feedback_context
            return {
                "intent": "list",
                "data_view": "launch_event",
                "confidence": 0.88,
                "reasoning": "Feedback and phrasing both indicate a launch window.",
            }

        monkeypatch.setattr(planner, "_interpret_with_provider", fake_interpret)
        plan = planner.build_plan("Show vehicles planned in 26Q4")

        assert plan.data_view == "launch_event"
        assert captured["query"] == "Show vehicles planned in 26Q4"
        assert captured["feedback_context"]
        assert captured["feedback_context"][0]["correction"] == "Treat this as a launch-window query."


def test_planner_mode_override_hybrid_without_provider_falls_back_safely(monkeypatch) -> None:
    monkeypatch.setenv("LAUNCHIQ_PLANNER_MODE", "heuristic")
    monkeypatch.setenv("LAUNCHIQ_LLM_PROVIDER", "heuristic")
    planner = Planner()

    plan = planner.build_plan("Which vehicles are launching in 2026?", mode_override="hybrid")

    assert plan.intent == "list"
    assert plan.data_view == "launch_event"
    assert plan.planner_diagnostics is not None
    assert any("Planner mode requested by UI: hybrid." == note for note in plan.planner_diagnostics.decision_notes)
    assert any("no llm provider was available" in note.lower() for note in plan.planner_diagnostics.decision_notes)


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
