import React, { useState } from "react";
import {
    Stack,
    Paper,
    Typography,
    Box,
    CircularProgress,
    Switch,
    IconButton,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Button,
    Chip,
    FormControl,
    Select,
    MenuItem,
} from "@mui/material";
import { Settings as SettingsIcon } from "@mui/icons-material";
import { LineEval, PositionEval } from "@/stockfish/engine/engine";
import { UciEngine } from "@/stockfish/engine/UciEngine";
import Slider from "../stockfish/Slider";
import { EngineName } from "@/stockfish/engine/engine";
import { useLocalStorage } from "usehooks-ts";
import { useTranslations } from "next-intl";

export interface StockfishAnalysisProps {
    stockfishAnalysisResult: PositionEval | null;
    stockfishLoading: boolean;
    engineDepth: number;
    setEngineDepth: (depth: number) => void;
    engineLines: number;
    setEngineLines: (lines: number) => void;
    engine: UciEngine | undefined;
    analyzeWithStockfish: () => void;
    handleEngineLineClick: (line: LineEval, index: number) => void;
    llmLoading: boolean;
    formatEvaluation: (line: LineEval) => string;
    formatPrincipalVariation: (pv: string[], fen: string) => string;
}

export const StockfishAnalysisTab: React.FC<StockfishAnalysisProps> = ({
    stockfishAnalysisResult,
    stockfishLoading,
    engineDepth,
    setEngineDepth,
    engineLines,
    setEngineLines,
    handleEngineLineClick,
    analyzeWithStockfish,
    llmLoading,
    formatEvaluation,
    formatPrincipalVariation,
}) => {
    const t = useTranslations("analysis.stockfish");
    const [engineEnabled, setEngineEnabled] = useState(true);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [isTransitioning, setIsTransitioning] = useState(false);
    const [enginePicked, setEnginePicked] = useLocalStorage<EngineName>(
        "stockfish-engine-picked",
        EngineName.Stockfish17
    );

    // Engine display names mapping (using translations)
    const getEngineDisplayName = (engine: EngineName) => {
        const key = engine.replace(/-/g, '').replace(/\./g, 'Point') as 'stockfish17' | 'stockfish17Point' | 'stockfish16' | 'stockfish11';
        return t(`engines.${key}`);
    };

    // Engine descriptions (using translations)
    const getEngineDescription = (engine: EngineName) => {
        const key = engine.replace(/-/g, '').replace(/\./g, 'Point') as 'stockfish17' | 'stockfish17Point' | 'stockfish16' | 'stockfish11';
        return t(`engineDescriptions.${key}`);
    };

    // Handle settings changes with smooth transitions
    const handleDepthChange = (newDepth: number) => {
        setIsTransitioning(true);
        setEngineDepth(newDepth);
        setSettingsOpen(false);
        
        // Restart analysis with new settings
        setTimeout(() => {
            if (engineEnabled) {
                analyzeWithStockfish();
            }
            setIsTransitioning(false);
        }, 300);
    };

    const handleLinesChange = (newLines: number) => {
        setIsTransitioning(true);
        setEngineLines(newLines);
        setSettingsOpen(false);
        
        // Restart analysis with new settings
        setTimeout(() => {
            if (engineEnabled) {
                analyzeWithStockfish();
            }
            setIsTransitioning(false);
        }, 300);
    };

    const handleEngineChange = (newEngine: EngineName) => {
        setIsTransitioning(true);
        setEnginePicked(newEngine);
        setSettingsOpen(false);
        
        // Restart analysis with new engine
        setTimeout(() => {
            if (engineEnabled) {
                analyzeWithStockfish();
            }
            setIsTransitioning(false);
        }, 300);

    };

    const handleEngineToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
        setIsTransitioning(true);
        setEngineEnabled(event.target.checked);

        
        if (event.target.checked) {
            setTimeout(() => {
                analyzeWithStockfish();
                setIsTransitioning(false);
            }, 300);
        } else {
            setTimeout(() => {
                setIsTransitioning(false);
            }, 300);
        }
    };

    const handleSettingsClose = () => {
        setSettingsOpen(false);
    };

    // Get current engine display name
    const getCurrentEngineDisplayName = () => {
        return getEngineDisplayName(enginePicked);
    };

    // Show loading state when enabled but no results yet or transitioning
    if (engineEnabled && (isTransitioning || !stockfishAnalysisResult || stockfishLoading && (!stockfishAnalysisResult.lines || stockfishAnalysisResult.lines.length === 0))) {
        return (
            <Box>
                {/* Header */}
                <Paper
                    sx={{
                        p: 2,
                        backgroundColor: "#1a1a1a",
                        borderRadius: 2,
                        mb: 2,
                        transition: "all 0.3s ease",
                    }}
                >
                    <Stack direction="row" alignItems="center" spacing={2}>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                            <Box
                                sx={{
                                    width: 8,
                                    height: 8,
                                    borderRadius: "50%",
                                    backgroundColor: "#9c27b0",
                                    transition: "background-color 0.3s ease",
                                }}
                            />
                            <Typography variant="subtitle2" sx={{ color: "white", fontWeight: 600 }}>
                                {t("stockfishOn")}
                            </Typography>
                        </Box>
                        <Switch
                            checked={engineEnabled}
                            onChange={handleEngineToggle}
                            disabled={isTransitioning}
                            sx={{
                                '& .MuiSwitch-switchBase.Mui-checked': {
                                    color: '#9c27b0',
                                },
                                '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                                    backgroundColor: '#9c27b0',
                                },
                                transition: "all 0.3s ease",
                            }}
                        />
                        <Box sx={{ flexGrow: 1 }} />
                        <IconButton
                            onClick={() => setSettingsOpen(true)}
                            sx={{ color: "white", p: 0.5 }}
                            size="small"
                        >
                            <SettingsIcon fontSize="small" />
                        </IconButton>
                    </Stack>
                </Paper>

                {/* Loading State */}
                <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
                    <Stack alignItems="center" spacing={2}>
                        <CircularProgress 
                            size={40} 
                            sx={{ color: "#9c27b0" }} 
                        />
                        <Typography variant="body2" sx={{ color: "grey.400" }}>
                            {isTransitioning ? t("applyingSettings") : t("startingAnalysis")}
                        </Typography>
                    </Stack>
                </Box>

                {/* Settings Dialog */}
                <Dialog
                    open={settingsOpen}
                    onClose={handleSettingsClose}
                    PaperProps={{
                        sx: {
                            backgroundColor: "#1a1a1a",
                            color: "white",
                            minWidth: 450
                        }
                    }}
                >
                    <DialogTitle>{t("settings")}</DialogTitle>
                    <DialogContent>
                        <Stack spacing={3} sx={{ pt: 1 }}>
                            <Box>
                                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                    {t("engineVersion")}
                                </Typography>
                                <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                    {t("engineVersionDesc")}
                                </Typography>
                                <FormControl fullWidth>
                                    <Select
                                        value={enginePicked}
                                        onChange={(e) => handleEngineChange(e.target.value as EngineName)}
                                        disabled={stockfishLoading || isTransitioning}
                                        sx={{
                                            color: 'white',
                                            '& .MuiOutlinedInput-notchedOutline': {
                                                borderColor: 'rgba(255, 255, 255, 0.23)',
                                            },
                                            '&:hover .MuiOutlinedInput-notchedOutline': {
                                                borderColor: '#9c27b0',
                                            },
                                            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                                                borderColor: '#9c27b0',
                                            },
                                            '& .MuiSvgIcon-root': {
                                                color: 'white',
                                            },
                                        }}
                                        MenuProps={{
                                            PaperProps: {
                                                sx: {
                                                    backgroundColor: '#2a2a2a',
                                                    '& .MuiMenuItem-root': {
                                                        color: 'white',
                                                        '&:hover': {
                                                            backgroundColor: 'rgba(156, 39, 176, 0.1)',
                                                        },
                                                        '&.Mui-selected': {
                                                            backgroundColor: 'rgba(156, 39, 176, 0.2)',
                                                            '&:hover': {
                                                                backgroundColor: 'rgba(156, 39, 176, 0.3)',
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        }}
                                    >
                                        {Object.values(EngineName).map((engine) => (
                                            <MenuItem key={engine} value={engine}>
                                                <Box>
                                                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                                        {getEngineDisplayName(engine)}
                                                    </Typography>
                                                    <Typography variant="caption" sx={{ color: 'grey.400', display: 'block' }}>
                                                        {getEngineDescription(engine)}
                                                    </Typography>
                                                </Box>
                                            </MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                            </Box>
                            <Box>
                                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                    {t("analysisDepth")}: {engineDepth}
                                </Typography>
                                <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                    {t("analysisDepthDesc")}
                                </Typography>
                                <Slider
                                    value={engineDepth}
                                    setValue={handleDepthChange}
                                    min={10}
                                    max={25}
                                    disable={stockfishLoading || isTransitioning}
                                />
                            </Box>
                            <Box>
                                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                    {t("numberOfLines")}: {engineLines}
                                </Typography>
                                <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                    {t("numberOfLinesDesc")}
                                </Typography>
                                <Slider
                                    value={engineLines}
                                    setValue={handleLinesChange}
                                    min={1}
                                    max={4}
                                    disable={stockfishLoading || isTransitioning}
                                />
                            </Box>
                        </Stack>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={handleSettingsClose} sx={{ color: "#9c27b0" }}>
                            {t("done")}
                        </Button>
                    </DialogActions>
                </Dialog>
            </Box>
        );
    }

    // Show disabled state
    if (!engineEnabled) {
        return (
            <Paper
                sx={{
                    p: 2,
                    backgroundColor: "#1a1a1a",
                    borderRadius: 2,
                    transition: "all 0.3s ease",
                }}
            >
                <Stack direction="row" alignItems="center" spacing={2}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Box
                            sx={{
                                width: 8,
                                height: 8,
                                borderRadius: "50%",
                                backgroundColor: "grey.600",
                                transition: "background-color 0.3s ease",
                            }}
                        />
                        <Typography variant="subtitle2" sx={{ color: "grey.400", fontWeight: 600 }}>
                            {t("stockfishOff")}
                        </Typography>
                    </Box>
                    <Switch
                        checked={engineEnabled}
                        onChange={handleEngineToggle}
                        disabled={isTransitioning}
                        sx={{
                            '& .MuiSwitch-switchBase.Mui-checked': {
                                color: '#9c27b0',
                            },
                            '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                                backgroundColor: '#9c27b0',
                            },
                            transition: "all 0.3s ease",
                        }}
                    />
                    <Box sx={{ flexGrow: 1 }} />
                    <IconButton
                        onClick={() => setSettingsOpen(true)}
                        sx={{ color: "grey.400", p: 0.5 }}
                        size="small"
                    >
                        <SettingsIcon fontSize="small" />
                    </IconButton>
                </Stack>

                {/* Settings Dialog */}
                <Dialog
                    open={settingsOpen}
                    onClose={handleSettingsClose}
                    PaperProps={{
                        sx: {
                            backgroundColor: "#1a1a1a",
                            color: "white",
                            minWidth: 450
                        }
                    }}
                >
                    <DialogTitle>{t("settings")}</DialogTitle>
                    <DialogContent>
                        <Stack spacing={3} sx={{ pt: 1 }}>
                            <Box>
                                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                    {t("engineVersion")}
                                </Typography>
                                <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                    {t("engineVersionDesc")}
                                </Typography>
                                <FormControl fullWidth>
                                    <Select
                                        value={enginePicked}
                                        onChange={(e) => handleEngineChange(e.target.value as EngineName)}
                                        disabled={stockfishLoading || isTransitioning}
                                        sx={{
                                            color: 'white',
                                            '& .MuiOutlinedInput-notchedOutline': {
                                                borderColor: 'rgba(255, 255, 255, 0.23)',
                                            },
                                            '&:hover .MuiOutlinedInput-notchedOutline': {
                                                borderColor: '#9c27b0',
                                            },
                                            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                                                borderColor: '#9c27b0',
                                            },
                                            '& .MuiSvgIcon-root': {
                                                color: 'white',
                                            },
                                        }}
                                        MenuProps={{
                                            PaperProps: {
                                                sx: {
                                                    backgroundColor: '#2a2a2a',
                                                    '& .MuiMenuItem-root': {
                                                        color: 'white',
                                                        '&:hover': {
                                                            backgroundColor: 'rgba(156, 39, 176, 0.1)',
                                                        },
                                                        '&.Mui-selected': {
                                                            backgroundColor: 'rgba(156, 39, 176, 0.2)',
                                                            '&:hover': {
                                                                backgroundColor: 'rgba(156, 39, 176, 0.3)',
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        }}
                                    >
                                        {Object.values(EngineName).map((engine) => (
                                            <MenuItem key={engine} value={engine}>
                                                <Box>
                                                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                                        {getEngineDisplayName(engine)}
                                                    </Typography>
                                                    <Typography variant="caption" sx={{ color: 'grey.400', display: 'block' }}>
                                                        {getEngineDescription(engine)}
                                                    </Typography>
                                                </Box>
                                            </MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                            </Box>
                            <Box>
                                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                    {t("analysisDepth")}: {engineDepth}
                                </Typography>
                                <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                    {t("analysisDepthDesc")}
                                </Typography>
                                <Slider
                                    value={engineDepth}
                                    setValue={handleDepthChange}
                                    min={10}
                                    max={25}
                                    disable={stockfishLoading || isTransitioning}
                                />
                            </Box>
                            <Box>
                                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                    {t("numberOfLines")}: {engineLines}
                                </Typography>
                                <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                    {t("numberOfLinesDesc")}
                                </Typography>
                                <Slider
                                    value={engineLines}
                                    setValue={handleLinesChange}
                                    min={1}
                                    max={4}
                                    disable={stockfishLoading || isTransitioning}
                                />
                            </Box>
                        </Stack>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={handleSettingsClose} sx={{ color: "#9c27b0" }}>
                            {t("done")}
                        </Button>
                    </DialogActions>
                </Dialog>
            </Paper>
        );
    }

    return (
        <Box sx={{ transition: "all 0.3s ease" }}>
            {/* Header */}
            <Paper
                sx={{
                    p: 2,
                    backgroundColor: "#1a1a1a",
                    borderRadius: 2,
                    mb: 2,
                    transition: "all 0.3s ease",
                }}
            >
                <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Box
                            sx={{
                                width: 8,
                                height: 8,
                                borderRadius: "50%",
                                backgroundColor: "#9c27b0",
                                transition: "background-color 0.3s ease",
                            }}
                        />
                        <Typography variant="subtitle2" sx={{ color: "white", fontWeight: 600 }}>
                            Stockfish On
                        </Typography>
                    </Box>
                    <Switch
                        checked={engineEnabled}
                        onChange={handleEngineToggle}
                        disabled={isTransitioning}
                        sx={{
                            '& .MuiSwitch-switchBase.Mui-checked': {
                                color: '#9c27b0',
                            },
                            '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                                backgroundColor: '#9c27b0',
                            },
                            transition: "all 0.3s ease",
                        }}
                    />
                    <Box sx={{ flexGrow: 1 }} />
                    <IconButton
                        onClick={() => setSettingsOpen(true)}
                        sx={{ color: "white", p: 0.5 }}
                        size="small"
                    >
                        <SettingsIcon fontSize="small" />
                    </IconButton>
                </Stack>

                {/* Engine Info */}
                <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ color: "white", fontWeight: 500 }}>
                        {getCurrentEngineDisplayName()}
                    </Typography>
                    <Chip 
                        label={`${engineDepth}`} 
                        size="small" 
                        sx={{ 
                            backgroundColor: "rgba(156, 39, 176, 0.2)", 
                            color: "#9c27b0",
                            fontSize: "0.7rem",
                            fontWeight: 600,
                            transition: "all 0.3s ease",
                        }} 
                    />
                    <Typography variant="caption" sx={{ color: "grey.400" }}>
                        {t("for")}
                    </Typography>
                    <Chip
                        label={`${engineLines}`}
                        size="small"
                        sx={{
                            backgroundColor: "rgba(156, 39, 176, 0.2)",
                            color: "#9c27b0",
                            fontSize: "0.7rem",
                            fontWeight: 600,
                            transition: "all 0.3s ease",
                        }}
                    />
                    <Typography variant="caption" sx={{ color: "grey.400" }}>
                        {t("lines")}
                    </Typography>
                </Stack>

                {/* Column Headers */}
                <Stack direction="row" spacing={2} sx={{ mb: 1 }}>
                    <Typography variant="caption" sx={{ color: "grey.400", minWidth: "60px" }}>
                        {t("eval")}
                    </Typography>
                    <Typography variant="caption" sx={{ color: "grey.400", minWidth: "60px" }}>
                        {t("winPercent")}
                    </Typography>
                    <Typography variant="caption" sx={{ color: "grey.400", flex: 1 }}>
                        {t("moves")}
                    </Typography>
                </Stack>
            </Paper>

            {/* Analysis Lines */}
            <Stack spacing={0} sx={{ transition: "all 0.3s ease" }}>
                {stockfishAnalysisResult?.lines?.map((line, index) => (
                    <Paper
                        key={`line-${index}-${line.depth}-${line.cp || line.mate}`}
                        onClick={() => handleEngineLineClick(line, index)}
                        sx={{
                            p: 2,
                            backgroundColor: "#1a1a1a",
                            borderRadius: 0,
                            borderBottom: index < stockfishAnalysisResult.lines.length - 1 ? "1px solid rgba(255,255,255,0.1)" : "none",
                            borderLeft: index === 0 ? "3px solid #9c27b0" : "3px solid transparent",
                            cursor: llmLoading ? "not-allowed" : "pointer",
                            transition: "all 0.3s ease",
                            opacity: isTransitioning ? 0.5 : 1,
                            "&:hover": {
                                backgroundColor: llmLoading ? "#1a1a1a" : "rgba(156, 39, 176, 0.1)",
                            },
                            filter: llmLoading ? "grayscale(50%)" : "none",
                        }}
                    >
                        <Stack direction="row" alignItems="center" spacing={2}>
                            {/* Evaluation */}
                            <Typography
                                variant="body2"
                                sx={{
                                    color: line.cp !== undefined 
                                        ? (line.cp > 0 ? "#4caf50" : line.cp < 0 ? "#f44336" : "white")
                                        : line.mate !== undefined
                                        ? (line.mate > 0 ? "#4caf50" : "#f44336")
                                        : "white",
                                    fontWeight: "bold",
                                    minWidth: "60px",
                                    fontFamily: "monospace",
                                    fontSize: "0.85rem",
                                    transition: "color 0.3s ease",
                                }}
                            >
                                {formatEvaluation(line)}
                            </Typography>

                            {/* Win Percentage */}
                            <Typography
                                variant="body2"
                                sx={{
                                    color: "grey.300",
                                    minWidth: "60px",
                                    fontFamily: "monospace",
                                    fontSize: "0.85rem",
                                    transition: "color 0.3s ease",
                                }}
                            >
                                {line.cp !== undefined 
                                    ? `${Math.max(0, Math.min(100, 50 + (line.cp / 100) * 10)).toFixed(1)}%`
                                    : line.mate !== undefined
                                    ? (line.mate > 0 ? "100%" : "0%")
                                    : "50.0%"
                                }
                            </Typography>

                            {/* Principal Variation */}
                            <Typography
                                variant="body2"
                                sx={{ 
                                    color: "white", 
                                    fontFamily: "monospace", 
                                    flex: 1,
                                    fontSize: "0.85rem",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                    transition: "color 0.3s ease",
                                }}
                            >
                                {formatPrincipalVariation(line.pv, line.fen)}
                            </Typography>

                            {/* Loading indicator for incomplete lines */}
                            {(stockfishLoading || isTransitioning) && line.depth < engineDepth && (
                                <CircularProgress size={16} sx={{ color: "#9c27b0" }} />
                            )}
                        </Stack>
                    </Paper>
                ))}

                {/* Placeholder lines while loading */}
                {(stockfishLoading || isTransitioning) &&
                    stockfishAnalysisResult?.lines &&
                    stockfishAnalysisResult.lines.length < engineLines &&
                    Array.from({
                        length: engineLines - stockfishAnalysisResult.lines.length,
                    }).map((_, index) => (
                        <Paper
                            key={`placeholder-${index}`}
                            sx={{
                                p: 2,
                                backgroundColor: "#1a1a1a",
                                borderRadius: 0,
                                borderBottom: "1px solid rgba(255,255,255,0.1)",
                                opacity: 0.5,
                                transition: "all 0.3s ease",
                            }}
                        >
                            <Stack direction="row" alignItems="center" spacing={2}>
                                <CircularProgress size={16} sx={{ color: "#9c27b0" }} />
                                <Typography
                                    variant="body2"
                                    sx={{ color: "grey.400", fontFamily: "monospace", fontSize: "0.85rem" }}
                                >
                                    {isTransitioning ? t("restartingAnalysis") : t("calculatingLine", { line: stockfishAnalysisResult.lines.length + index + 1 })}
                                </Typography>
                            </Stack>
                        </Paper>
                    ))}
            </Stack>

            {/* Footer Info */}
            {stockfishAnalysisResult && (
                <Paper
                    sx={{
                        p: 1.5,
                        backgroundColor: "#1a1a1a",
                        borderRadius: 0,
                        mt: 0,
                        transition: "all 0.3s ease",
                    }}
                >
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="caption" sx={{ color: "grey.400" }}>
                            {t("reachedDepth")}: {stockfishAnalysisResult.lines?.[0]?.depth || engineDepth}
                        </Typography>
                        <Typography variant="caption" sx={{ color: "grey.400" }}>
                            {t("speed")}: {stockfishAnalysisResult.lines?.[0]?.nps
                                ? `${(stockfishAnalysisResult.lines[0].nps / 1000000).toFixed(2)} Mn/s`
                                : "1.35 Mn/s"
                            }
                        </Typography>
                    </Stack>
                </Paper>
            )}

            {/* Settings Dialog */}
            <Dialog
                open={settingsOpen}
                onClose={handleSettingsClose}
                PaperProps={{
                    sx: {
                        backgroundColor: "#1a1a1a",
                        color: "white",
                        minWidth: 450
                    }
                }}
            >
                <DialogTitle>Stockfish Settings</DialogTitle>
                <DialogContent>
                    <Stack spacing={3} sx={{ pt: 1 }}>
                        <Box>
                            <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                Engine Version
                            </Typography>
                            <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                Choose which Stockfish version to use for analysis
                            </Typography>
                            <FormControl fullWidth>
                                <Select
                                    value={enginePicked}
                                    onChange={(e) => handleEngineChange(e.target.value as EngineName)}
                                    disabled={stockfishLoading || isTransitioning}
                                    sx={{
                                        color: 'white',
                                        '& .MuiOutlinedInput-notchedOutline': {
                                            borderColor: 'rgba(255, 255, 255, 0.23)',
                                        },
                                        '&:hover .MuiOutlinedInput-notchedOutline': {
                                            borderColor: '#9c27b0',
                                        },
                                        '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                                            borderColor: '#9c27b0',
                                        },
                                        '& .MuiSvgIcon-root': {
                                            color: 'white',
                                        },
                                    }}
                                    MenuProps={{
                                        PaperProps: {
                                            sx: {
                                                backgroundColor: '#2a2a2a',
                                                '& .MuiMenuItem-root': {
                                                    color: 'white',
                                                    '&:hover': {
                                                        backgroundColor: 'rgba(156, 39, 176, 0.1)',
                                                    },
                                                    '&.Mui-selected': {
                                                        backgroundColor: 'rgba(156, 39, 176, 0.2)',
                                                        '&:hover': {
                                                            backgroundColor: 'rgba(156, 39, 176, 0.3)',
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    }}
                                >
                                    {Object.values(EngineName).map((engine) => (
                                        <MenuItem key={engine} value={engine}>
                                            <Box>
                                                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                                    {getEngineDisplayName(engine)}
                                                </Typography>
                                                <Typography variant="caption" sx={{ color: 'grey.400', display: 'block' }}>
                                                    {getEngineDescription(engine)}
                                                </Typography>
                                            </Box>
                                        </MenuItem>
                                    ))}
                                </Select>
                            </FormControl>
                        </Box>
                        <Box>
                            <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                Analysis Depth: {engineDepth}
                            </Typography>
                            <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                Higher depth provides more accurate analysis but takes longer
                            </Typography>
                            <Slider
                                value={engineDepth}
                                setValue={handleDepthChange}
                                min={10}
                                max={25}
                                disable={stockfishLoading || isTransitioning}
                            />
                        </Box>
                        <Box>
                            <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                                Number of Lines: {engineLines}
                            </Typography>
                            <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                                Show multiple best move candidates (AI will analyze all lines)
                            </Typography>
                            <Slider
                                value={engineLines}
                                setValue={handleLinesChange}
                                min={1}
                                max={4}
                                disable={stockfishLoading || isTransitioning}
                            />
                        </Box>
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleSettingsClose} sx={{ color: "#9c27b0" }}>
                        Done
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Hint */}
            <Box sx={{ mt: 2 }}>
                <Typography
                    variant="caption"
                    sx={{ color: "grey.500", fontStyle: "italic" }}
                >
                    {t("clickForAI")}
                </Typography>
            </Box>
        </Box>
    );
};

export default StockfishAnalysisTab;