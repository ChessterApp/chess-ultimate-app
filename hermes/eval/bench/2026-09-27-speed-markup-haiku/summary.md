| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | 0/36 | 36/36 | 4/4 | 25/25 | 12/36 | 0 | 7 | 27/162 | 0.72 | 2/3 | 1.41 | 1.41 | 3.8 | 4.29 | 9.41 | 17.3 | 0.9 | 0.0067 | 0.314 | 1.7 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | game_review | 2 | 1.4 | 2.19 | 2.19 | 36.01 | 3.5 |
| anthropic/claude-haiku-4.5 | games_search | 2 | 1.89 | 3.74 | 3.74 | 17.3 | 3.0 |
| anthropic/claude-haiku-4.5 | general | 3 | 1.41 | 1.6 | 1.86 | 16.42 | 2.7 |
| anthropic/claude-haiku-4.5 | import | 1 | 1.4 | 1.69 | 1.69 | 6.13 | 1.0 |
| anthropic/claude-haiku-4.5 | legality_check | 3 | 1.47 | 4.03 | 4.45 | 7.8 | 0.0 |
| anthropic/claude-haiku-4.5 | move_recommendation | 11 | 1.37 | 4.05 | 7.28 | 9.35 | 0.0 |
| anthropic/claude-haiku-4.5 | opening | 3 | 1.26 | 2.19 | 4.12 | 9.67 | 1.0 |
| anthropic/claude-haiku-4.5 | position_assessment | 8 | 1.47 | 3.85 | 4.15 | 9.41 | 0.0 |
| anthropic/claude-haiku-4.5 | puzzle | 3 | 1.31 | 1.64 | 2.03 | 7.88 | 2.0 |
