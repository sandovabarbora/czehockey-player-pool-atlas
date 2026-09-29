"""Analysis for spec §3 (questions 1-7) and §4 (nationality and linking).

One module per question, each writing one JSON file to outputs/:

    linking      the unified player-season table and the linking/nationality report
    q1_per_million, q2_break_model, q3_cohort_gaps, q4_youth_ice_time,
    q5_abroad, q6_national_team, q7_goalkeepers, pool

    python -m src.analysis            # every module, in order
    python -m src.analysis.q1_per_million
"""
