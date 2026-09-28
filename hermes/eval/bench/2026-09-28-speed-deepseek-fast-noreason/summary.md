| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 25/25 | 14/36 | 0 | 11 | 27/140 | 0.61 | 2/3 | 0.63 | 0.61 | 0.92 | 4.7 | 4.47 | 11.06 | 1.0 | 0.0012 | 0.111 | 1.8 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.61 | 38.8 | 38.8 | 44.64 | 5.0 |
| prod | games_search | 2 | 0.72 | 0.82 | 0.82 | 7.41 | 2.0 |
| prod | general | 3 | 1.02 | 1.96 | 4.95 | 8.06 | 1.7 |
| prod | import | 1 | 0.61 | 2.32 | 2.32 | 125.03 | 3.0 |
| prod | legality_check | 3 | 0.69 | 0.78 | 1.09 | 2.76 | 0.0 |
| prod | move_recommendation | 11 | 0.63 | 0.83 | 3.07 | 3.27 | 0.0 |
| prod | opening | 3 | 0.66 | 0.93 | 4.7 | 3.93 | 1.7 |
| prod | position_assessment | 8 | 0.58 | 0.85 | 0.98 | 4.42 | 0.5 |
| prod | puzzle | 3 | 0.68 | 2.45 | 2.86 | 3.76 | 2.0 |
