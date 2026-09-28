| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | 0/36 | 36/36 | 4/4 | 25/25 | 12/36 | 0 | 9 | 13/139 | 0.76 | 2/3 | 1.34 | 1.33 | 1.88 | 2.28 | 7.3 | 14.41 | 1.0 | 0.007 | 0.313 | 1.8 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | game_review | 2 | 1.66 | 1.88 | 1.88 | 38.9 | 5.0 |
| anthropic/claude-haiku-4.5 | games_search | 2 | 1.6 | 2.77 | 2.77 | 12.41 | 3.0 |
| anthropic/claude-haiku-4.5 | general | 3 | 1.32 | 1.58 | 1.64 | 13.36 | 2.3 |
| anthropic/claude-haiku-4.5 | import | 1 | 1.26 | 1.54 | 1.54 | 5.57 | 1.0 |
| anthropic/claude-haiku-4.5 | legality_check | 3 | 1.3 | 1.93 | 1.93 | 4.38 | 0.0 |
| anthropic/claude-haiku-4.5 | move_recommendation | 11 | 1.38 | 1.99 | 8.05 | 7.0 | 0.1 |
| anthropic/claude-haiku-4.5 | opening | 3 | 1.22 | 1.65 | 1.9 | 9.92 | 1.3 |
| anthropic/claude-haiku-4.5 | position_assessment | 8 | 1.27 | 1.89 | 2.27 | 7.3 | 0.0 |
| anthropic/claude-haiku-4.5 | puzzle | 3 | 1.32 | 1.59 | 1.63 | 7.31 | 2.0 |
