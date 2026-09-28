| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 24/25 | 16/36 | 1 | 23 | 19/150 | 0.67 | 2/3 | 1.1 | 1.03 | 11.12 | 41.24 | 17.15 | 49.21 | 1.4 | 0.003 | 0.2 | 2.1 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.79 | 48.1 | 48.1 | 48.11 | 5.5 |
| prod | games_search | 2 | 1.17 | 11.12 | 11.12 | 21.68 | 3.0 |
| prod | general | 3 | 0.92 | 6.43 | 41.24 | 12.52 | 1.3 |
| prod | import | 1 | 1.41 | 2.46 | 2.46 | 22.01 | 5.0 |
| prod | legality_check | 3 | 1.39 | 9.46 | 13.81 | 11.93 | 0.7 |
| prod | move_recommendation | 11 | 0.86 | 14.33 | 49.07 | 20.16 | 0.3 |
| prod | opening | 3 | 0.86 | 15.12 | 15.61 | 21.13 | 2.7 |
| prod | position_assessment | 8 | 1.14 | 12.3 | 46.76 | 17.37 | 0.5 |
| prod | puzzle | 3 | 1.17 | 6.03 | 12.93 | 7.43 | 2.3 |
