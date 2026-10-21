# PROCESS 1 – IMPORTS

import streamlit as st

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
    explain_where_money,
    md,
    money,
    money_warning,
    outcome_frame,
    range_text,
    team_cost_persistence,
    team_excess_cost,
)
from src.tools.priorities import (
    PRIORITY_MEANING,
    explain_priorities,
    factor_value,
    priority_chart,
    priority_matrix,
)
from src.tools.recommendations import (
    PERFORMANCE,
    TIER_ORDER,
    productivity_levers,
    team_plans,
)
from src.ui import (
    OUTCOME_LEVEL,
    analysis_runner,
    how_to_read,
    page_header,
    require_data,
    story_box,
    trap_checks,
)


# PROCESS 2 – HEADER

page_header(
    "Financial impact",
    ":material/payments:",
    "What turnover and absence cost today, and what engagement improvements backed by "
    "your data could be worth.",
)

df, validation = require_data()

if validation["capabilities"]["level"] != OUTCOME_LEVEL:
    st.info(
        "Financial impact needs business outcomes (turnover, absence or performance) "
        "in the uploaded data.",
        icon=":material/info:",
    )
    st.stop()

sample = len(outcome_frame(df))           # every employee in the outcome file, not only respondents
assumptions = st.session_state.get("assumptions") or default_assumptions(df)
c = assumptions.currency


# PROCESS 3 – ASSUMPTIONS: ONE LINE + EDIT POPOVER

line_col, edit_col = st.columns([4, 1], vertical_alignment="center")

line_col.caption(
    f":material/tune: **Using:** {assumptions_line(assumptions, sample)}. "
    "Defaults are placeholders; replace them with your organization's numbers."
)

with edit_col.popover("Edit assumptions", icon=":material/edit:", width="stretch"):

    with st.form("assumptions_form", border=False):

        avg_salary = st.number_input(
            "Average salary per year", min_value=0.0,
            value=float(assumptions.avg_salary), step=1000.0, format="%.0f")
        replacement_pct = st.slider(
            "Cost to replace one leaver (% of salary)", min_value=10, max_value=200,
            value=int(round(assumptions.replacement_cost_pct * 100)), step=5,
            help="Recruiting, onboarding and lost output. Studies often put it at 50–200%.")
        day_cost = st.number_input(
            "Cost of one unplanned absence day (0 = salary ÷ 260)", min_value=0.0,
            value=float(assumptions.absence_day_cost or 0.0), step=10.0, format="%.0f")
        point_value = st.number_input(
            "Value of +1 performance point, per person per year (0 = leave out)",
            min_value=0.0, value=float(assumptions.value_per_rating_point),
            step=500.0, format="%.0f")
        headcount = st.number_input(
            "Company headcount", min_value=1,
            value=int(assumptions.headcount or sample), step=100,
            help=f"The data has {sample:,} people; results scale to this number.")
        currency = st.selectbox(
            "Currency symbol", options=["$", "€", "£", "Rp", "¥"],
            index=["$", "€", "£", "Rp", "¥"].index(assumptions.currency))

        if st.form_submit_button("Apply", type="primary", icon=":material/check:",
                                 width="stretch"):
            st.session_state["assumptions"] = Assumptions(
                avg_salary=avg_salary,
                replacement_cost_pct=replacement_pct / 100,
                absence_day_cost=day_cost or None,
                value_per_rating_point=point_value,
                headcount=int(headcount),
                currency=currency,
            )
            st.rerun()


# PROCESS 3B – SURVEY-RESPONSE NOTE (leavers answer less often, so savings are understated)

response_note = money_warning(df, st.session_state.get("health_report"))
if response_note:
    st.warning(response_note, icon=":material/info:")


# PROCESS 4 – WHAT IT COSTS TODAY

costs = current_costs(df, assumptions)

st.subheader("What it costs today", anchor=False)

today = [("People cost at stake", money(costs["total_cost"], c),
          "Voluntary turnover + unplanned absence, per year.")]
if "turnover_cost" in costs:
    today.append(("Voluntary turnover", money(costs["turnover_cost"], c),
                  md(f"About {costs['leavers']:,.0f} leavers a year (all employees) × "
                     f"{money(assumptions.cost_per_leaver, c)} each.")))
if "absence_cost" in costs:
    today.append(("Unplanned absence", money(costs["absence_cost"], c),
                  md(f"About {costs['absence_days']:,.0f} days a year × "
                     f"{money(assumptions.day_cost, c)} a day.")))

for (label, value, help_text), column in zip(today, st.columns(len(today))):
    column.metric(label, value, help=help_text, border=True)


# PROCESS 5 – WHAT ENGAGEMENT COULD BE WORTH

analysis = analysis_runner(df, key="run_analysis_financials")

# One engine (the Scenarios simulation) prices every factor and the headline program.
factors = factor_value(df, analysis, assumptions, trap_checks(df)) if analysis is not None else None

if analysis is not None:

    plans = None
    if PERFORMANCE in df.columns:
        levers = productivity_levers(df, analysis, st.session_state.get("change_analysis"))
        if not levers.empty:
            plans = team_plans(df, levers)

    with st.container(border=True):

        title_col, tier_col = st.columns([2, 2], vertical_alignment="bottom")

        title_col.subheader("What engagement could be worth", anchor=False)

        tiers = TIER_ORDER[:1]
        if plans is not None and assumptions.value_per_rating_point > 0:
            tiers = tier_col.pills(
                "Productivity: teams that follow their plan",
                options=TIER_ORDER[:2],
                selection_mode="multi",
                default=TIER_ORDER[:1],
                key="fin_tiers",
            ) or TIER_ORDER[:1]

        value = engagement_value(df, analysis, assumptions, plans, tiers, factors=factors)
        scenarios = value["scenarios"]
        program = value["program"]

        if scenarios.empty:
            st.caption("No verified driver is available to value yet.")
        else:
            share = value["total"] / costs["total_cost"] if costs["total_cost"] else 0
            low, high = value["range"]
            tiles = [("Total, per year", money(value["total"], c),
                      f"{share:.0%} of today's people cost · {range_text(low, high, c)}")]
            tiles += [(row["source"], money(row["value"], c),
                       f"{row['units']:,.0f} {row['unit_label']}")
                      for _, row in scenarios.iterrows()]

            for (label, val, detail), column in zip(tiles, st.columns(len(tiles))):
                column.metric(label, val, delta=detail, delta_color="off",
                              delta_arrow="off", border=True)

            if program:
                st.markdown(md(
                    f"**The program:** everyone who answers 1–3 on **{program['names']}** moves "
                    f"up one point ({program['people']:,.0f} people), counted once even when a "
                    "person is helped by more than one question. The turnover and absence "
                    "figures above are this one program, not a sum of separate programs."))
                per_person = break_even_per_person(program["value"], program["people"])
                st.caption(md(
                    f":material/balance: Break-even: the program pays for itself if it costs "
                    f"less than about {money(per_person, c)} per person per year "
                    f"(low end of the range: "
                    f"{money(break_even_per_person(program['low'], program['people']), c)})."))
            st.markdown("\n".join(
                f"- **{row['source']}:** {md(row['what'])}."
                for _, row in scenarios.iterrows()))

        if plans is not None and assumptions.value_per_rating_point <= 0:
            st.caption(":material/info: Add a value for +1 performance point under **Edit "
                       "assumptions** to include the productivity plans from Recommendations.")

        how_to_read(
            "The headline is one named program, simulated with each person's own risk from "
            "the verified models (the same engine as the Scenarios page), so the two pages "
            "agree. The range is the 95% margin of error of those models. It covers sampling "
            "error only, and the survey-response note above says which way the real value is "
            "likely to differ. Productivity assumes the chosen teams close the gap on their "
            "first recommended question. Values are yearly once the change is complete. They "
            "describe associations in your data, not guaranteed returns.",
            "How these figures work",
        )


# PROCESS 6 – WHERE TO INVEST: FACTORS RANKED BY DOLLARS

if analysis is not None:

    if not factors.empty:

        with st.container(border=True):

            st.subheader("Where to invest: factors ranked by value", anchor=False)
            st.caption(
                "Every question that passed all checks, priced with your assumptions and "
                "ranked by yearly value: each person's own risk change from the verified "
                "models, for the people who score 1–3 today, with a 95% range in the table."
            )

            chart_col, story_col = st.columns([3, 2], gap="large")

            with chart_col:
                st.altair_chart(
                    priority_chart(factors, c),
                    width="stretch",
                    alt="Engagement questions ranked by estimated yearly value",
                )

            with story_col:
                story_box(explain_priorities(factors, assumptions))

            st.markdown("  ".join(
                f"**{name}:** {meaning}." for name, meaning in PRIORITY_MEANING.items()))

            with st.expander("Impact vs current score", icon=":material/scatter_plot:"):
                st.altair_chart(
                    priority_matrix(factors, c),
                    width="stretch",
                    alt="Each question's value per person against the share who agree today",
                )
                st.caption(
                    "Dashed lines: the median share agreeing across all 12 questions, and half "
                    "the strongest factor's value per person. Top-left = Fix first."
                )

            with st.expander("All factors as a table", icon=":material/table_chart:"):
                st.dataframe(
                    factors.drop(columns=["mean_score"]),
                    hide_index=True,
                    width="stretch",
                    height="content",
                    column_config={
                        "rank": st.column_config.NumberColumn("Rank", format="%d"),
                        "item": "Question",
                        "label": "Topic",
                        "priority": "Priority",
                        "yearly_value": st.column_config.NumberColumn(
                            "Yearly value", format="compact"),
                        "value_low": st.column_config.NumberColumn(
                            "Low end (95%)", format="compact"),
                        "value_high": st.column_config.NumberColumn(
                            "High end (95%)", format="compact"),
                        "value_per_person": st.column_config.NumberColumn(
                            "Per person moved", format="compact"),
                        "agree_pct": st.column_config.NumberColumn(
                            "Agree today", format="percent"),
                        "people_below": st.column_config.NumberColumn(
                            "People answering 1–3", format="%,.0f"),
                        "avoided_leavers": st.column_config.NumberColumn(
                            "Leavers avoided", format="%.1f"),
                        "turnover_value": st.column_config.NumberColumn(
                            "Turnover value", format="compact"),
                        "avoided_absence_days": st.column_config.NumberColumn(
                            "Absence days avoided", format="%,.0f"),
                        "absence_value": st.column_config.NumberColumn(
                            "Absence value", format="compact"),
                        "rating_points": st.column_config.NumberColumn(
                            "Performance points", format="%,.0f"),
                        "performance_value": st.column_config.NumberColumn(
                            "Performance value", format="compact"),
                        "outcomes": "Linked to",
                        "caution": "Note",
                    },
                    alt="Every valued engagement factor with avoided turnover, absence and value",
                )

            how_to_read(
                "Scenario: everyone who answers 1–3 on the question moves up one point, with "
                "everything else unchanged. Each person's chance of leaving and expected absence "
                "days are predicted twice by the verified models, today and after the lift, and "
                "the difference is added up. Each factor is valued on its own: the same people "
                "answer every question, so don't add the values together (the program above "
                "counts them jointly).",
                "How these values work",
            )


# PROCESS 7 – WHERE THE MONEY IS

departments = department_excess_cost(df, assumptions)
teams = team_excess_cost(df, assumptions)

if not departments.empty and (departments["excess_cost"] > 0).any():

    with st.container(border=True):

        st.subheader("Where the money is: departments", anchor=False)

        dept_col, dept_story_col = st.columns([3, 2], gap="large")

        with dept_col:
            st.dataframe(
                departments,
                hide_index=True,
                width="stretch",
                height="content",
                column_config={
                    "department": "Department",
                    "people": st.column_config.NumberColumn("People", format="%,.0f"),
                    "turnover_rate": st.column_config.NumberColumn("Turnover", format="percent"),
                    "absence_days": st.column_config.NumberColumn(
                        "Absence days (6 mo.)", format="%.1f"),
                    "excess_turnover_cost": st.column_config.NumberColumn(
                        "Extra turnover cost", format="compact"),
                    "excess_absence_cost": st.column_config.NumberColumn(
                        "Extra absence cost", format="compact"),
                    "excess_cost": st.column_config.NumberColumn(
                        "Extra cost, total", format="compact"),
                },
                alt="Extra yearly turnover and absence cost for every department",
            )

        with dept_story_col:
            story_box(explain_departments(departments, assumptions))
            st.caption("Counted on all employees. Descriptive only: it shows where extra "
                       "costs are, not why.")

if not teams.empty and (teams["excess_cost"] > 0).any():

    persistence = team_cost_persistence(df, assumptions)

    with st.container(border=True):

        st.subheader("Where the money is: teams", anchor=False)

        if persistence["status"] == "failed":
            st.warning(
                persistence["text"] + " Team rankings are hidden because the costliest teams "
                "do not stay costly: most of a team's extra cost one year is chance. Use the "
                "department view above.", icon=":material/visibility_off:")
        else:
            if persistence["status"] == "passed":
                st.caption(":material/fact_check: " + persistence["text"])
            else:
                st.caption(":material/hourglass_empty: " + persistence["text"])

            basis_label = st.segmented_control(
                "Compare each team with",
                options=["The company rate", "Its own department"],
                default="The company rate",
                key="fin_team_basis",
            ) or "The company rate"
            basis = "department" if basis_label == "Its own department" else "company"
            ranked = teams.sort_values("excess_cost_dept" if basis == "department"
                                       else "excess_cost", ascending=False)

            chart_col, story_col = st.columns([3, 2], gap="large")

            with chart_col:
                st.altair_chart(
                    excess_cost_chart(ranked, c, basis=basis),
                    width="stretch",
                    alt="Teams with the highest extra yearly cost from turnover and absence",
                )

            with story_col:
                story_box(explain_where_money(teams, assumptions))
                st.caption("Descriptive only. Small teams are pulled toward the company rate "
                           "so one leaver does not decide the ranking.")

            with st.expander("All teams", icon=":material/table_chart:"):
                st.dataframe(
                    ranked.drop(columns=["excess_turnover_cost_dept", "excess_absence_cost_dept"]),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "team_id": "Team",
                        "department": "Department",
                        "people": st.column_config.NumberColumn("People", format="%d"),
                        "turnover_rate": st.column_config.NumberColumn("Turnover", format="percent"),
                        "absence_days": st.column_config.NumberColumn(
                            "Absence days (6 mo.)", format="%.1f"),
                        "excess_turnover_cost": st.column_config.NumberColumn(
                            "Extra turnover cost", format="compact"),
                        "excess_absence_cost": st.column_config.NumberColumn(
                            "Extra absence cost", format="compact"),
                        "excess_cost": st.column_config.NumberColumn(
                            "Extra cost vs company", format="compact"),
                        "excess_cost_dept": st.column_config.NumberColumn(
                            "Extra cost vs own department", format="compact"),
                    },
                    alt="Extra yearly turnover and absence cost for every team",
                )


# PROCESS 8 – ASSUMPTIONS AND LIMITS

with st.expander("Assumptions and limits", icon=":material/rule:"):

    st.markdown("\n".join(f"- {line}" for line in assumptions.describe(sample)))
    st.caption(
        "Costs today count every employee in the outcome file. Savings come from models fitted "
        "on survey respondents and scaled to the headcount above. "
        "Your data has no revenue or profit, so these are cost-based estimates, not a "
        "measured link to profit. To measure that link, add team-level financial results "
        "(for example profit or revenue per team per period) to the data."
    )
