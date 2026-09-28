| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 25/25 | 17/36 | 0 | 20 | 27/157 | 0.6 | 2/3 | 0.62 | 0.62 | 5.38 | 24.75 | 8.66 | 28.55 | 1.4 | 0.003 | 0.183 | 2.1 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.56 | 166.96 | 166.96 | 172.67 | 5.0 |
| prod | games_search | 2 | 0.56 | 6.12 | 6.12 | 9.58 | 2.0 |
| prod | general | 3 | 0.88 | 3.07 | 5.27 | 9.65 | 0.7 |
| prod | import | 1 | 0.64 | 6.14 | 6.14 | 8.6 | 5.0 |
| prod | legality_check | 3 | 0.65 | 4.42 | 9.72 | 6.15 | 1.7 |
| prod | move_recommendation | 11 | 0.65 | 6.47 | 24.75 | 8.57 | 0.3 |
| prod | opening | 3 | 0.68 | 5.38 | 14.76 | 8.66 | 3.0 |
| prod | position_assessment | 8 | 0.59 | 7.15 | 26.47 | 9.98 | 0.6 |
| prod | puzzle | 3 | 0.64 | 3.97 | 7.37 | 5.52 | 2.0 |
