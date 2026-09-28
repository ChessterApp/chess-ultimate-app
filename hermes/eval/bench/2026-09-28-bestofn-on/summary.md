| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 2/25 | 10/36 | 23 | 5 | 7/58 | 0.68 | 2/3 | 3.98 | 0.62 | 4.86 | 22.37 | 5.25 | 22.37 | 0.8 | 0.0043 | 0.069 | 0.8 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.76 | 7.6 | 7.6 | 9.18 | 3.0 |
| prod | games_search | 2 | None | 22.37 | 22.37 | 22.37 | 0.0 |
| prod | general | 3 | 0.49 | 2.2 | 3.82 | 4.6 | 2.0 |
| prod | import | 1 | 0.62 | 7.94 | 7.94 | 9.29 | 4.0 |
| prod | legality_check | 3 | None | 2.31 | 2.44 | 2.31 | 0.0 |
| prod | move_recommendation | 11 | None | 5.25 | 97.23 | 5.25 | 0.0 |
| prod | opening | 3 | None | 3.9 | 5.17 | 5.17 | 1.7 |
| prod | position_assessment | 8 | None | 6.02 | 104.63 | 6.02 | 0.0 |
| prod | puzzle | 3 | 0.87 | 4.0 | 94.61 | 7.12 | 2.0 |
