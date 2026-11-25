from app.lead_service import (
    classify_score,
    extract_lead_hints,
    score_lead,
)


def test_example_lead_scores_100_and_recommends_a_demo():
    result = score_lead(
        35,
        "struggles with manual route planning",
        True,
        "ops@northline.example",
    )
    assert result["lead_score"] == 100
    assert result["qualification_status"] == "Qualified"
    assert result["recommended_next_action"] == "Schedule a product demonstration with the sales team."
    assert sum(result["score_breakdown"].values()) == 100


def test_vehicle_threshold_is_ten():
    assert score_lead(10, "", False, None)["score_breakdown"]["vehicle_count"] == 30
    assert score_lead(9, "", False, None)["score_breakdown"]["vehicle_count"] == 0


def test_empty_problem_and_negative_phrases_score_zero_problem_points():
    assert score_lead(0, "", False, None)["score_breakdown"]["business_problem"] == 0
    assert score_lead(0, "no problem", False, None)["score_breakdown"]["business_problem"] == 0
    assert score_lead(0, "Manual dispatch is slow", False, None)["lead_score"] == 30


def test_contact_points_require_an_email():
    without_email = score_lead(12, "late deliveries", False, None)
    with_email = score_lead(12, "late deliveries", False, "a@fleet.example")
    assert without_email["score_breakdown"]["contact_information"] == 0
    assert with_email["score_breakdown"]["contact_information"] == 15
    assert with_email["lead_score"] == 75


def test_classification_boundaries():
    assert classify_score(100) == "Qualified"
    assert classify_score(70) == "Qualified"
    assert classify_score(69) == "Potential"
    assert classify_score(40) == "Potential"
    assert classify_score(39) == "Not Qualified"
    assert classify_score(0) == "Not Qualified"


def test_reachable_status_bands():
    # 9 vehicles gives no vehicle points: 30 + 25 + 15 = 70.
    qualified = score_lead(9, "manual planning", True, "a@b.co")
    # Email plus demo interest is the lowest Potential score the rules can produce.
    potential = score_lead(0, "", True, "a@b.co")
    unqualified = score_lead(0, "late deliveries", False, None)
    assert qualified["qualification_status"] == "Qualified"
    assert qualified["lead_score"] == 70
    assert potential["qualification_status"] == "Potential"
    assert potential["lead_score"] == 40
    assert unqualified["qualification_status"] == "Not Qualified"
    assert unqualified["lead_score"] == 30


def test_extracts_the_demo_script():
    transcript = "\n".join([
        "Hi, I am Priya Shah from Northline Logistics.",
        "We have 35 vehicles.",
        "We struggle with manual route planning and late deliveries.",
        "My email is priya@northline.example and yes, I would like a product demo.",
    ])
    hints = extract_lead_hints(transcript)
    assert hints["customer_name"] == "Priya Shah"
    assert hints["company_name"] == "Northline Logistics"
    assert hints["vehicle_count"] == 35
    assert "manual route planning" in hints["business_problem"]
    assert hints["email"] == "priya@northline.example"
    assert hints["interested_in_demo"] is True


def test_later_demo_refusal_overrides_an_earlier_yes():
    hints = extract_lead_hints("I would like a product demo. Actually I am not interested.")
    assert hints["interested_in_demo"] is False
