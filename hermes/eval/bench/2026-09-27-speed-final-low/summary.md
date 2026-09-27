| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 25/25 | 18/36 | 0 | 23 | 24/133 | 0.58 | 2/3 | 0.98 | 0.97 | 12.51 | 26.04 | 16.38 | 34.94 | 3.2 | 0.0033 | 0.211 | 2.8 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 1.42 | 73.14 | 73.14 | 73.18 | 7.0 |
| prod | games_search | 2 | 2.6 | 13.04 | 13.04 | 19.43 | 6.5 |
| prod | general | 3 | 0.7 | 3.81 | 12.51 | 12.89 | 1.7 |
| prod | import | 1 | 0.67 | 5.38 | 5.38 | 9.33 | 3.0 |
| prod | legality_check | 3 | 0.92 | 11.76 | 26.04 | 18.58 | 3.7 |
| prod | move_recommendation | 11 | 0.97 | 11.99 | 57.25 | 15.65 | 2.3 |
| prod | opening | 3 | 0.85 | 15.63 | 19.01 | 15.64 | 6.3 |
| prod | position_assessment | 8 | 0.98 | 12.68 | 20.06 | 18.69 | 2.4 |
| prod | puzzle | 3 | 0.75 | 14.16 | 22.83 | 18.9 | 2.0 |
