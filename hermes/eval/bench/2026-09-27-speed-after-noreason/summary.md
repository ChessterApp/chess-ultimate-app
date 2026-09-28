| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 22/25 | 29/36 | 4 | 17 | 36/169 | 0.45 | 2/3 | 1.12 | 1.12 | 4.37 | 23.5 | 13.69 | 32.89 | 3.3 | 0.0079 | 0.196 | 3.3 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 1.54 | 46.14 | 46.14 | 46.16 | 6.0 |
| prod | games_search | 2 | 2.18 | 8.09 | 8.09 | 22.14 | 4.5 |
| prod | general | 3 | 0.74 | 1.46 | 5.06 | 8.83 | 1.7 |
| prod | import | 1 | 0.67 | 2.32 | 2.32 | 7.5 | 2.0 |
| prod | legality_check | 3 | 0.93 | 3.52 | 4.37 | 9.98 | 2.7 |
| prod | move_recommendation | 11 | 1.25 | 9.6 | 24.19 | 17.04 | 2.9 |
| prod | opening | 3 | 0.71 | 6.87 | 17.79 | 13.98 | 6.3 |
| prod | position_assessment | 8 | 1.27 | 3.96 | 23.5 | 19.04 | 3.0 |
| prod | puzzle | 3 | 0.95 | 1.05 | 2.76 | 7.01 | 2.7 |
