| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/36 | 36/36 | 4/4 | 25/25 | 13/36 | 0 | 12 | 24/87 | 0.4 | 2/3 | 0.5 | 0.5 | 1.03 | 3.3 | 2.52 | 4.59 | 0.9 | 0.0013 | 0.065 | 1.6 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | game_review | 2 | 0.65 | 5.38 | 5.38 | 6.97 | 2.0 |
| prod | games_search | 2 | 0.53 | 2.81 | 2.81 | 4.25 | 3.5 |
| prod | general | 3 | 0.45 | 1.57 | 3.3 | 2.87 | 2.7 |
| prod | import | 1 | 0.49 | 3.39 | 3.39 | 3.43 | 2.0 |
| prod | legality_check | 3 | 0.48 | 0.68 | 1.03 | 1.78 | 0.0 |
| prod | move_recommendation | 11 | 0.62 | 0.77 | 2.52 | 1.83 | 0.0 |
| prod | opening | 3 | 0.5 | 2.59 | 2.77 | 3.59 | 1.7 |
| prod | position_assessment | 8 | 0.49 | 0.74 | 2.15 | 2.51 | 0.0 |
| prod | puzzle | 3 | 0.76 | 2.27 | 2.98 | 2.75 | 2.0 |
