| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | quick_p50 | answer_p50 | answer_p90 | total_p50 | total_p90 | tools_avg | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prod | 0/3 | 3/3 | 0/0 | 2/2 | 1/3 | 0 | 2 | 0/2 | 0.0 | 0/0 | 0.59 | 0.59 | 0.85 | 3.47 | 2.42 | 7.45 | 1.0 | 0.0008 | 0.004 | 1.7 |

| model | kind | n | quick_p50 | answer_p50 | answer_max | total_p50 | tools_avg |
|---|---|---|---|---|---|---|---|
| prod | import | 1 | 2.83 | 3.47 | 3.47 | 7.45 | 3.0 |
| prod | move_recommendation | 1 | 0.52 | 0.85 | 0.85 | 2.42 | 0.0 |
| prod | position_assessment | 1 | 0.59 | 0.79 | 0.79 | 2.01 | 0.0 |
