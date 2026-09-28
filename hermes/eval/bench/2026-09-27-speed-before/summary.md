| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 23/25 | 34/36 | 2 | 33 | 26/141 | 0.55 | 2/3 | 1.3 | 1.28 | 16.16 | 74.65 | 19.66 | 89.02 | 4.2 | 0.0047 | 0.259 | 3.5 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 1.63 | 63.47 | 63.47 | 63.53 | 6.5 |
| prod | games_search | 2 | 1.5 | 33.24 | 33.24 | 36.44 | 8.0 |
| prod | general | 3 | 1.23 | 7.75 | 13.46 | 13.26 | 1.7 |
| prod | import | 1 | 1.06 | 10.53 | 10.53 | 12.55 | 4.0 |
| prod | legality_check | 3 | 0.73 | 5.65 | 14.03 | 11.52 | 3.0 |
| prod | move_recommendation | 11 | 1.42 | 17.23 | 132.08 | 24.26 | 4.4 |
| prod | opening | 3 | 1.52 | 21.66 | 26.48 | 29.25 | 5.3 |
| prod | position_assessment | 8 | 1.3 | 16.16 | 124.34 | 18.6 | 4.1 |
| prod | puzzle | 3 | 1.28 | 5.41 | 77.23 | 7.81 | 2.0 |
