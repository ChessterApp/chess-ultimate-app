| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 25/25 | 30/36 | 0 | 27 | 23/144 | 0.64 | 2/3 | 1.53 | 1.53 | 12.88 | 45.72 | 19.28 | 46.88 | 3.8 | 0.0112 | 0.247 | 3.3 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 1.5 | 116.72 | 116.72 | 116.74 | 6.5 |
| prod | games_search | 2 | 1.45 | 66.42 | 66.42 | 66.44 | 7.0 |
| prod | general | 3 | 1.68 | 8.73 | 9.81 | 12.33 | 1.0 |
| prod | import | 1 | 1.39 | 11.23 | 11.23 | 13.69 | 5.0 |
| prod | legality_check | 3 | 1.84 | 8.91 | 43.66 | 10.66 | 3.0 |
| prod | move_recommendation | 11 | 1.63 | 12.88 | 39.19 | 16.97 | 3.4 |
| prod | opening | 3 | 1.01 | 18.52 | 26.68 | 38.4 | 5.7 |
| prod | position_assessment | 8 | 1.44 | 14.03 | 45.72 | 28.21 | 3.9 |
| prod | puzzle | 3 | 1.5 | 6.18 | 7.95 | 13.3 | 3.0 |
