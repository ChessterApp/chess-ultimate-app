| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 25/25 | 16/36 | 0 | 13 | 41/184 | 0.55 | 2/3 | 1.02 | 1.02 | 3.69 | 17.7 | 8.84 | 26.55 | 2.7 | 0.0022 | 0.172 | 2.7 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 1.61 | 93.22 | 93.22 | 93.23 | 6.5 |
| prod | games_search | 2 | 1.81 | 6.12 | 6.12 | 11.09 | 5.0 |
| prod | general | 3 | 0.99 | 1.95 | 4.37 | 7.71 | 2.0 |
| prod | import | 1 | 0.82 | 0.93 | 0.93 | 6.27 | 3.0 |
| prod | legality_check | 3 | 0.94 | 3.53 | 3.69 | 8.84 | 2.3 |
| prod | move_recommendation | 11 | 1.02 | 3.44 | 18.06 | 8.77 | 1.6 |
| prod | opening | 3 | 0.97 | 5.37 | 16.77 | 14.03 | 5.3 |
| prod | position_assessment | 8 | 1.07 | 3.11 | 17.7 | 8.47 | 2.1 |
| prod | puzzle | 3 | 1.57 | 4.57 | 4.63 | 7.95 | 2.0 |
