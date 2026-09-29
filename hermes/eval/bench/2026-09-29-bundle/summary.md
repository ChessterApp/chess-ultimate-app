| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 23/25 | 11/36 | 0 | 9 | 19/75 | 0.48 | 2/3 | 0.52 | 0.52 | 1.79 | 4.08 | 3.05 | 5.67 | 0.6 | 0.001 | 0.051 | 1.5 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.51 | 3.04 | 3.04 | 4.6 | 0.0 |
| prod | games_search | 2 | 0.51 | 4.08 | 4.08 | 4.09 | 2.5 |
| prod | general | 3 | 0.47 | 1.45 | 2.22 | 3.3 | 2.0 |
| prod | import | 1 | 1.0 | 2.43 | 2.43 | 2.43 | 1.0 |
| prod | legality_check | 3 | 0.51 | 0.64 | 7.58 | 1.25 | 0.0 |
| prod | move_recommendation | 11 | 0.54 | 0.7 | 6.92 | 2.25 | 0.0 |
| prod | opening | 3 | 0.48 | 1.68 | 2.06 | 2.59 | 1.3 |
| prod | position_assessment | 8 | 0.53 | 0.86 | 2.2 | 1.96 | 0.0 |
| prod | puzzle | 3 | 0.55 | 3.17 | 3.32 | 3.66 | 2.0 |
