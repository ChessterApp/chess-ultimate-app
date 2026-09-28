| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | 0/36 | 36/36 | 4/4 | 24/25 | 13/36 | 0 | 10 | 12/127 | 0.78 | 2/3 | 1.35 | 1.3 | 3.59 | 4.16 | 10.75 | 19.29 | 1.3 | 0.007 | 0.34 | 2.1 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | game_review | 2 | 1.29 | 1.92 | 1.92 | 32.53 | 4.0 |
| anthropic/claude-haiku-4.5 | games_search | 2 | 1.26 | 3.68 | 3.68 | 19.29 | 3.5 |
| anthropic/claude-haiku-4.5 | general | 3 | 1.5 | 1.61 | 1.63 | 12.47 | 1.3 |
| anthropic/claude-haiku-4.5 | import | 1 | 1.26 | 1.6 | 1.6 | 5.72 | 1.0 |
| anthropic/claude-haiku-4.5 | legality_check | 3 | 1.26 | 3.82 | 4.02 | 9.42 | 0.7 |
| anthropic/claude-haiku-4.5 | move_recommendation | 11 | 1.3 | 3.59 | 6.89 | 10.63 | 0.8 |
| anthropic/claude-haiku-4.5 | opening | 3 | 1.52 | 2.0 | 3.99 | 11.74 | 1.7 |
| anthropic/claude-haiku-4.5 | position_assessment | 8 | 1.42 | 3.87 | 4.99 | 11.39 | 0.5 |
| anthropic/claude-haiku-4.5 | puzzle | 3 | 1.55 | 1.74 | 1.82 | 9.41 | 2.0 |
