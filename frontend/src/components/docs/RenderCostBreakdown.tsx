"use client";
import React from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import {
  Info as InfoIcon,
  Calculate as CalculateIcon,
  SportsEsports as GameIcon,
  Quiz as PuzzleIcon,
  Analytics as AnalysisIcon,
} from "@mui/icons-material";
import { ChessScenario, MODEL_PRICING, ModelPricing } from "@/libs/docs/helper";

const getTierColor = (tier: string) => {
  switch (tier) {
    case "Free":
      return "success";
    case "Budget":
      return "success";
    case "Balanced":
      return "warning";
    case "Premium":
      return "error";
    default:
      return "default";
  }
};

const calculateScenarioCost = (
  pricing: ModelPricing,
  scenario: ChessScenario
) => {
  const inputCost =
    (scenario.tokensPerRequest.input *
      scenario.requestsPerSession *
      pricing.inputPrice) /
    1000000;
  const outputCost =
    (scenario.tokensPerRequest.output *
      scenario.requestsPerSession *
      pricing.outputPrice) /
    1000000;
  return inputCost + outputCost;
};

const CHESS_SCENARIOS: ChessScenario[] = [
  {
    name: "Quick Move Analysis",
    description: "Get hints or analyze a single position during live play",
    icon: <GameIcon />,
    tokensPerRequest: { input: 3000, output: 3000 },
    requestsPerSession: 15,
  },
  {
    name: "Full Game Review (40 moves)",
    description: "Analyze every move of a typical game (~80 half-moves)",
    icon: <AnalysisIcon />,
    tokensPerRequest: { input: 3200, output: 3000 },
    requestsPerSession: 80,
  },
  {
    name: "Puzzle Training (20 puzzles)",
    description: "Solve multiple tactical puzzles with detailed explanations",
    icon: <PuzzleIcon />,
    tokensPerRequest: { input: 3000, output: 1200 },
    requestsPerSession: 20,
  },
  {
    name: "Opening Study",
    description: "Learn opening theory and key variations",
    icon: <InfoIcon />,
    tokensPerRequest: { input: 3000, output: 3000 },
    requestsPerSession: 12,
  },
];

export const renderCostsAnalysis = () => (
  <Box>
    {/* Cost Overview */}
    <Card sx={{ mb: 4 }}>
      <CardContent>
        <Typography
          variant="h5"
          gutterBottom
          color="primary.text"
          sx={{ display: "flex", alignItems: "center", gap: 1 }}
        >
          <CalculateIcon />
          Cost Analysis Overview
        </Typography>
        <Typography variant="body1" color="text.secondary" paragraph>
          All costs are calculated based on 200 API requests with approximately
          3,000 input tokens and 3,000 output tokens per request. Chess
          scenarios below show approximately usage patterns, actual costs may
          very. Pricing updated August 2025 from official provider APIs.
        </Typography>
      </CardContent>
    </Card>

    {/* Pricing Table */}
    <Card sx={{ mb: 4 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom color="primary.text">
          Model Pricing Comparison
        </Typography>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Provider</TableCell>
                <TableCell>Model</TableCell>
                <TableCell align="right">
                  Input Price
                  <br />
                  (/1M tokens)
                </TableCell>
                <TableCell align="right">
                  Output Price
                  <br />
                  (/1M tokens)
                </TableCell>
                <TableCell align="right">
                  200 Requests
                  <br />
                  Cost
                </TableCell>
                <TableCell align="center">Tier</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {MODEL_PRICING.sort(
                (a, b) => a.costPer200Requests - b.costPer200Requests
              ).map((model, index) => (
                <TableRow key={index}>
                  <TableCell>{model.provider}</TableCell>
                  <TableCell
                    sx={{ fontFamily: "monospace", fontSize: "0.875rem" }}
                  >
                    {model.model}
                  </TableCell>
                  <TableCell align="right">
                    ${model.inputPrice.toFixed(2)}
                  </TableCell>
                  <TableCell align="right">
                    ${model.outputPrice.toFixed(2)}
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    ${model.costPer200Requests.toFixed(2)}
                  </TableCell>
                  <TableCell align="center">
                    <Chip
                      label={model.tier}
                      size="small"
                      color={getTierColor(model.tier)}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>

    {/* Chess Scenarios */}
    <Typography variant="h5" gutterBottom color="primary.text" sx={{ mb: 3 }}>
      Chess Session Cost Examples
    </Typography>

    {CHESS_SCENARIOS.map((scenario, scenarioIndex) => (
      <Card key={scenarioIndex} sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
            {scenario.icon}
            <Box>
              <Typography variant="h6" color="primary.text">
                {scenario.name}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {scenario.description}
              </Typography>
            </Box>
          </Box>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Session: {scenario.requestsPerSession} requests ×{" "}
            {scenario.tokensPerRequest.input} input +{" "}
            {scenario.tokensPerRequest.output} output tokens each
          </Typography>

          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Model</TableCell>
                  <TableCell align="right">Cost per Session</TableCell>
                  <TableCell align="right">
                    Monthly Cost
                    <br />
                    (20 sessions)
                  </TableCell>
                  <TableCell align="center">Value Rating</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {MODEL_PRICING.map((model) => ({
                  ...model,
                  sessionCost: calculateScenarioCost(model, scenario),
                }))
                  .sort((a, b) => a.sessionCost - b.sessionCost)
                  .map((model, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 500 }}>
                            {model.provider}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ fontFamily: "monospace" }}
                          >
                            {model.model}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        ${model.sessionCost.toFixed(3)}
                      </TableCell>
                      <TableCell align="right">
                        ${(model.sessionCost * 20).toFixed(2)}
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={model.tier}
                          size="small"
                          color={getTierColor(model.tier)}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    ))}
  </Box>
);
