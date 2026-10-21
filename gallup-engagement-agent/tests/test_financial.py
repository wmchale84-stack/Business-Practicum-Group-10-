# PROCESS 1 – IMPORTS

import numpy as np
import pandas as pd
import pytest

from src.agent import DEFAULT_DATASET
from src.tools.analytics import analyze_dataframe
from src.tools.waves import model_sample, model_wave
from src.tools.financial_updated import (
    Assumptions,
    assumptions_line,
    break_even_per_person,
    current_costs,
    default_assumptions,
    department_excess_cost,
    engagement_value,
    excess_cost_chart,
    explain_departments,
    explain_value,
    explain_where_money,
    money,
    money_warning,
    outcome_frame,
    share_text,
    team_cost_persistence,
    team_excess_cost,
    value_chart,
)
from src.tools.insights import analysis_frame
from src.tools.priorities import factor_value
from src.tools.recommendations import productivity_levers, team_plans
from src.tools.scenario import simulate


# PROCESS 2 – FIXTURES

@pytest.fixture(scope="module")
def data():

    path = DEFAULT_DATASET / "agent_data"

    survey = pd.read_csv(path / "survey_responses.csv")
    individual = pd.read_csv(path / "individual_outcomes.csv")

    return survey.merge(
        individual,
        on=[c for c in survey.columns if c in individual.columns],
    )


@pytest.fixture(scope="module")
def analysis(data):

    return analyze_dataframe(model_sample(data), dataset_name="dev")


@pytest.fixture(scope="module")
def plans(data, analysis):

    return team_plans(data, productivity_levers(data, analysis))


# PROCESS 3 – HELPERS

@pytest.mark.parametrize("value, text", [
    (1_234_567, "$1.2M"), (45_300, "$45K"), (900, "$900"), (-2_500_000, "-$2.5M"),
])
def test_money_formatting(value, text):

    assert money(value) == text


def test_default_day_cost_is_salary_over_workdays():

    assert Assumptions(avg_salary=52_000).day_cost == pytest.approx(200)


@pytest.mark.parametrize("part, whole, text", [
    (0.2, 100, "<1%"), (0, 100, "0%"), (43, 100, "43%"), (5, 0, "0%"),
])
def test_share_text_never_reads_as_nothing(part, whole, text):

    assert share_text(part, whole) == text


def test_break_even_is_value_per_person():

    assert break_even_per_person(1_000_000, 500) == pytest.approx(2_000)
    assert break_even_per_person(1_000_000, 0) == 0


# PROCESS 4 – COSTS TODAY (fix 1: everyone is counted, not only respondents)

def test_current_costs_count_every_employee(data):

    a = Assumptions(avg_salary=50_000, replacement_cost_pct=1.0)
    costs = current_costs(data, a)

    everyone = data[data["wave"] == model_wave(data)]
    real_leavers = everyone["left_voluntarily_12m"].sum()
    assert costs["leavers"] == pytest.approx(real_leavers)
    assert costs["turnover_cost"] == pytest.approx(real_leavers * 50_000)
    assert costs["sample"] == len(everyone)


def test_respondent_only_count_would_understate(data):

    respondents = analysis_frame(data)
    assert len(outcome_frame(data)) > len(respondents)
    # Leavers answer less often, so respondents have the lower turnover rate.
    assert (outcome_frame(data)["left_voluntarily_12m"].mean()
            > respondents["left_voluntarily_12m"].mean())


def test_default_headcount_is_all_employees(data):

    assert default_assumptions(data).headcount == len(outcome_frame(data))
    assert current_costs(data, default_assumptions(data))["headcount"] == len(outcome_frame(data))


def test_headcount_scales_costs_linearly(data):

    sample = len(outcome_frame(data))
    small = current_costs(data, Assumptions(headcount=sample))
    double = current_costs(data, Assumptions(headcount=2 * sample))

    assert double["total_cost"] == pytest.approx(2 * small["total_cost"])


# PROCESS 5 – SCENARIOS (fixes 2, 3, 4: one engine, one program, a range)

def test_program_is_the_scenarios_simulation(data, analysis):

    a = default_assumptions(data)
    value = engagement_value(data, analysis, a)
    program = value["program"]
    assert program and program["items"]

    sim = simulate(data, analysis, {i: 1.0 for i in program["items"]}, a,
                   who="low", ramp_months=0)["totals"]["estimate"]
    rows = value["scenarios"].set_index("source")
    assert rows.loc["Turnover", "units"] == pytest.approx(sim["leavers"])
    assert rows.loc["Turnover", "value"] == pytest.approx(sim["leavers"] * a.cost_per_leaver)
    if "Absence" in rows.index:
        assert rows.loc["Absence", "units"] == pytest.approx(sim["absence_days"])


def test_factor_value_matches_scenarios_page(data, analysis):

    a = default_assumptions(data)
    factors = factor_value(data, analysis, a)
    top = factors[factors["yearly_value"] > 0].iloc[0]

    sim = simulate(data, analysis, {top["item"]: 1.0}, a, who="low", ramp_months=0)
    assert top["yearly_value"] == pytest.approx(sim["totals"]["estimate"]["value"])
    assert top["value_low"] == pytest.approx(sim["value_range"][0])
    assert top["value_high"] == pytest.approx(sim["value_range"][1])


def test_headline_is_one_named_program(data, analysis):

    a = default_assumptions(data)
    value = engagement_value(data, analysis, a)
    story = explain_value(current_costs(data, a), value, team_excess_cost(data, a), a)

    assert value["total"] == pytest.approx(value["scenarios"]["value"].sum())
    assert value["program"]["names"] in story["headline"]
    assert "a year" in story["headline"] and "likely" in story["headline"]


def test_program_counts_people_once_across_questions(data, analysis):

    a = default_assumptions(data)
    items = list(factor_value(data, analysis, a).query("yearly_value > 0")["item"][:2])
    if len(items) < 2:
        pytest.skip("needs two valued factors")
    joint = engagement_value(data, analysis, a, items=items)["total"]
    alone = sum(engagement_value(data, analysis, a, items=[i])["total"] for i in items)
    assert joint <= alone + 1e-6


def test_every_figure_has_a_range(data, analysis):

    a = default_assumptions(data)
    scenarios = engagement_value(data, analysis, a)["scenarios"]
    for _, row in scenarios.iterrows():
        assert row["low"] <= row["value"] <= row["high"]

    factors = factor_value(data, analysis, a)
    assert (factors["value_low"] <= factors["yearly_value"] + 1e-6).all()
    assert (factors["yearly_value"] <= factors["value_high"] + 1e-6).all()


def test_productivity_only_counted_with_a_point_value(data, analysis, plans):

    without = engagement_value(data, analysis, Assumptions(), plans)
    with_value = engagement_value(
        data, analysis, Assumptions(value_per_rating_point=1_000), plans
    )

    assert "Productivity" not in set(without["scenarios"]["source"])
    assert "Productivity" in set(with_value["scenarios"]["source"])
    assert with_value["total"] > without["total"]


def test_no_analysis_means_no_scenarios(data):

    value = engagement_value(data, None, Assumptions())

    assert value["scenarios"].empty and value["total"] == 0 and value["program"] is None


# PROCESS 6 – WHERE THE MONEY IS (fix 6: smoothing, departments, year-over-year check)

def test_excess_cost_sums_to_about_zero_at_company_rate(data):

    teams = team_excess_cost(data, Assumptions())

    # Extra costs are relative to the company rate, so they roughly cancel out.
    assert abs(teams["excess_cost"].sum()) < 0.05 * current_costs(
        data, Assumptions(headcount=len(outcome_frame(data))))["total_cost"]
    assert teams["excess_cost"].is_monotonic_decreasing


def test_small_teams_are_pulled_toward_the_company_rate(data):

    raw = team_excess_cost(data, Assumptions(), k=0).set_index("team_id")
    smooth = team_excess_cost(data, Assumptions(), k=20).set_index("team_id")
    both = raw.join(smooth, lsuffix="_raw", rsuffix="_smooth")

    assert (both["excess_cost_smooth"].abs() <= both["excess_cost_raw"].abs() + 1e-6).all()
    assert both["excess_cost_smooth"].std() < both["excess_cost_raw"].std()


def test_department_view_is_present_and_sums_to_zero(data):

    teams = team_excess_cost(data, Assumptions())
    assert {"excess_cost_dept", "excess_turnover_cost_dept"} <= set(teams.columns)

    departments = department_excess_cost(data, Assumptions())
    assert departments["excess_cost"].is_monotonic_decreasing
    assert abs(departments["excess_cost"].sum()) < 1e-6 * max(1, departments["excess_cost"].abs().sum()) + 1
    assert "costs" in explain_departments(departments, Assumptions())["headline"]


def test_teams_under_five_are_never_shown(data):

    teams = team_excess_cost(data, Assumptions())
    assert (teams["people"] >= 5).all()


def test_persistence_check_uses_two_outcome_years(data):

    result = team_cost_persistence(data, Assumptions())

    assert result["status"] in {"passed", "failed"}
    assert result["flagged"] >= 10 and result["ratio"] is not None
    assert "wave" in result["text"]


def test_persistence_is_pending_with_one_year(data):

    one_year = data[data["wave"] == model_wave(data)]
    result = team_cost_persistence(one_year, Assumptions())

    assert result["status"] == "pending" and result["ratio"] is None


def test_persistence_fails_when_costs_are_pure_chance():

    rng = np.random.default_rng(1)
    teams = [f"T{i}" for i in range(400)]
    rows = []
    for wave in (1, 2):
        for team in teams:
            for person in range(10):
                rows.append({"wave": wave, "team_id": team, "department": "A",
                             "left_voluntarily_12m": int(rng.random() < 0.15),
                             "unplanned_absence_days_6m": 0})
    noise = pd.DataFrame(rows)

    result = team_cost_persistence(noise, Assumptions())
    assert result["status"] == "failed"


def test_story_and_charts(data, analysis):

    a = Assumptions()
    costs = current_costs(data, a)
    value = engagement_value(data, analysis, a)
    teams = team_excess_cost(data, a)

    story = explain_value(costs, value, teams, a)

    assert "a year" in story["headline"]
    assert value_chart(value).to_dict()
    assert excess_cost_chart(teams).to_dict()
    assert excess_cost_chart(teams, basis="department").to_dict()


# PROCESS 7 – SURVEY-RESPONSE NOTE (fix 5)

def test_money_note_appears_when_leavers_answer_less(data):

    note = money_warning(data)

    assert note and "understated" in note and "%" in note


def test_money_note_absent_when_everyone_answers(data):

    even = data.copy()
    even["responded"] = 1

    assert money_warning(even) is None


def test_money_note_uses_health_report_when_columns_missing(data):

    stripped = data.drop(columns=["responded"])
    report = {"checks": [{"code": "NR_LEAVERS", "status": "WARN",
                          "metrics": {"leaver_rate": 0.6, "stayer_rate": 0.86}}]}

    assert "60%" in money_warning(stripped, report)
    assert money_warning(stripped, None) is None


# PROCESS 8 – PAGE HELPERS

def test_assumptions_line_shows_every_input(data):

    line = assumptions_line(Assumptions(value_per_rating_point=2_000, headcount=5_000), 4_000)

    for part in ["$60,000 salary", "50% of salary", "per absence day", "5,000 people",
                 "per performance point"]:
        assert part in line


def test_where_money_story_names_departments(data):

    story = explain_where_money(team_excess_cost(data, Assumptions()), Assumptions())

    assert "teams cost" in story["headline"]
    assert any("Most of it sits in" in p for p in story["points"])


def test_where_money_story_uses_commas_and_small_shares():

    n = 12_000
    teams = pd.DataFrame({
        "team_id": [f"T{i}" for i in range(n)], "department": "Sales",
        "excess_cost": 1_000.0, "excess_turnover_cost": 700.0, "excess_absence_cost": 300.0})

    story = explain_where_money(teams, Assumptions())

    assert "12,000 teams" in story["headline"]
    top10 = next(p for p in story["points"] if "costliest" in p)
    assert "<1% of that extra cost" in top10 and " 0% " not in top10
