| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-luna | 0/36 | 36/36 | 4/4 | 25/25 | 14/36 | 0 | 17 | 21/109 | 0.58 | 2/3 | 1.05 | 1.05 | 8.21 | 22.83 | 11.99 | 33.41 | 2.0 | 0.0034 | 0.135 | 2.6 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-luna | game_review | 2 | 1.1 | 95.34 | 95.34 | 117.45 | 8.5 |
| openai/gpt-5.6-luna | games_search | 2 | 1.25 | 30.67 | 30.67 | 33.41 | 4.0 |
| openai/gpt-5.6-luna | general | 3 | 0.94 | 6.62 | 7.04 | 19.17 | 1.0 |
| openai/gpt-5.6-luna | import | 1 | 1.05 | 12.17 | 12.17 | 13.24 | 4.0 |
| openai/gpt-5.6-luna | legality_check | 3 | 1.02 | 9.57 | 13.72 | 10.85 | 1.0 |
| openai/gpt-5.6-luna | move_recommendation | 11 | 1.07 | 6.77 | 11.85 | 9.38 | 1.0 |
| openai/gpt-5.6-luna | opening | 3 | 0.96 | 21.9 | 22.83 | 29.75 | 4.0 |
| openai/gpt-5.6-luna | position_assessment | 8 | 1.13 | 8.21 | 11.57 | 11.99 | 1.0 |
| openai/gpt-5.6-luna | puzzle | 3 | 0.96 | 5.79 | 5.8 | 7.58 | 2.0 |
