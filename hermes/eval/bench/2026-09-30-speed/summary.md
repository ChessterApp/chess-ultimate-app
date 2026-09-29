| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 24/25 | 10/36 | 0 | 13 | 18/71 | 0.53 | 2/3 | 0.4 | 0.4 | 0.93 | 2.34 | 1.59 | 3.51 | 0.7 | 0.001 | 0.057 | 1.5 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.41 | 3.66 | 3.66 | 4.87 | 0.5 |
| prod | games_search | 2 | 0.45 | 2.01 | 2.01 | 2.76 | 3.5 |
| prod | general | 3 | 0.45 | 1.11 | 1.51 | 1.55 | 2.0 |
| prod | import | 1 | 0.48 | 3.51 | 3.51 | 3.51 | 3.0 |
| prod | legality_check | 3 | 0.36 | 0.57 | 0.93 | 1.3 | 0.0 |
| prod | move_recommendation | 11 | 0.61 | 0.59 | 1.9 | 1.48 | 0.0 |
| prod | opening | 3 | 0.4 | 0.45 | 2.34 | 1.53 | 1.3 |
| prod | position_assessment | 8 | 0.4 | 1.05 | 2.1 | 1.83 | 0.0 |
| prod | puzzle | 3 | 0.39 | 0.93 | 1.02 | 1.37 | 1.0 |
