| model | errors | lang_ok | kk_ok | engine_when_needed | expected_tool_hit | ungrounded | tool_failures | illegal/claims | correctness | traps | ttft_p50 | total_p50 | total_p90 | cost_p50 | cost_sum | iters_avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| google/gemini-3.8-flash | 0/6 | 6/6 | 1/1 | 4/4 | 6/6 | 0 | 1 | 4/18 | 0.62 | 1/1 | 24.81 | 28.6 | 38.28 | 0.0167 | 0.101 | 3.7 |
| deepseek/deepseek-v4.1-flash | 0/6 | 6/6 | 1/1 | 4/4 | 6/6 | 0 | 2 | 10/32 | 0.22 | 1/1 | 13.44 | 27.69 | 117.02 | 0.0031 | 0.035 | 3.7 |
| deepseek/deepseek-v4-pro-0813 | 0/6 | 6/6 | 1/1 | 3/4 | 5/6 | 1 | 1 | 9/21 | 0.4 | 1/1 | 14.55 | 22.29 | 41.33 | 0.0143 | 0.102 | 3.0 |
| anthropic/claude-sonnet-5 | 0/6 | 6/6 | 1/1 | 4/4 | 6/6 | 0 | 0 | 4/15 | 0.32 | 1/1 | 18.39 | 30.3 | 77.91 | 0.0426 | 0.26 | 3.5 |
| moonshotai/kimi-k3 | 0/6 | 6/6 | 1/1 | 4/4 | 6/6 | 0 | 2 | 5/18 | 0.41 | 1/1 | 58.29 | 80.12 | 196.53 | 0.0609 | 0.4 | 3.3 |
