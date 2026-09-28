| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 3/36 | 33/33 | 4/4 | 23/23 | 11/33 | 0 | 4 | 9/74 | 0.73 | 2/3 | 0.54 | 0.54 | 1.1 | 3.83 | 3.08 | 8.58 | 0.6 | 0.0009 | 0.058 | 1.5 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.54 | 6.97 | 6.97 | 8.58 | 2.5 |
| prod | games_search | 2 | 1.4 | 2.93 | 2.93 | 4.62 | 1.0 |
| prod | general | 3 | 0.46 | 0.76 | 1.29 | 3.08 | 1.0 |
| prod | legality_check | 3 | 0.55 | 0.67 | 1.4 | 1.55 | 0.0 |
| prod | move_recommendation | 10 | 0.57 | 0.99 | 2.88 | 3.39 | 0.0 |
| prod | opening | 3 | 0.5 | 2.14 | 3.83 | 2.58 | 1.3 |
| prod | position_assessment | 7 | 0.51 | 0.88 | 1.36 | 3.21 | 0.0 |
| prod | puzzle | 3 | 0.57 | 2.49 | 4.15 | 3.02 | 2.0 |
