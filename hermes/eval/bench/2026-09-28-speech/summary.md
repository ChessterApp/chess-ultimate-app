| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 35/36 | 4/4 | 25/25 | 13/36 | 0 | 10 | 12/64 | 0.54 | 2/3 | 0.65 | 0.65 | 1.04 | 5.17 | 3.13 | 6.72 | 0.8 | 0.001 | 0.067 | 1.6 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 2.06 | 7.93 | 7.93 | 9.18 | 2.5 |
| prod | games_search | 2 | 0.62 | 2.72 | 2.72 | 3.98 | 3.0 |
| prod | general | 3 | 0.58 | 0.82 | 1.54 | 3.33 | 1.7 |
| prod | import | 1 | 1.15 | 1.36 | 1.36 | 3.58 | 1.0 |
| prod | legality_check | 3 | 0.65 | 1.0 | 1.61 | 1.75 | 0.0 |
| prod | move_recommendation | 11 | 0.65 | 0.93 | 7.42 | 2.32 | 0.0 |
| prod | opening | 3 | 0.68 | 0.93 | 3.07 | 3.8 | 1.7 |
| prod | position_assessment | 8 | 0.67 | 1.17 | 1.63 | 2.07 | 0.0 |
| prod | puzzle | 3 | 0.64 | 2.68 | 2.87 | 3.53 | 2.0 |
