| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 25/25 | 14/36 | 0 | 10 | 26/153 | 0.65 | 2/3 | 0.51 | 0.5 | 0.87 | 6.69 | 5.19 | 13.23 | 1.0 | 0.0015 | 0.091 | 1.8 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 1.23 | 12.14 | 12.14 | 17.62 | 4.0 |
| prod | games_search | 2 | 0.55 | 2.27 | 2.27 | 7.1 | 2.0 |
| prod | general | 3 | 0.53 | 1.36 | 1.42 | 5.19 | 1.0 |
| prod | import | 1 | 0.48 | 2.55 | 2.55 | 4.29 | 2.0 |
| prod | legality_check | 3 | 0.5 | 0.63 | 1.41 | 3.77 | 0.0 |
| prod | move_recommendation | 11 | 0.5 | 0.82 | 7.39 | 4.86 | 0.2 |
| prod | opening | 3 | 0.51 | 1.63 | 7.22 | 14.5 | 3.7 |
| prod | position_assessment | 8 | 0.49 | 0.75 | 1.04 | 3.96 | 0.0 |
| prod | puzzle | 3 | 0.46 | 2.27 | 2.37 | 3.74 | 2.3 |
