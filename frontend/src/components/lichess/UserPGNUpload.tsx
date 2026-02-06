import React, { useState } from "react";
import {
    Button,
    Typography,
    Stack,
    Paper,
    Box,
    Alert
} from "@mui/material";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { purpleTheme } from "@/theme/theme";

interface PGNUploaderProps {
    loadPGN: (pgn: string) => void;
}

const UserPGNUploader: React.FC<PGNUploaderProps> = ({ loadPGN }) => {
    const [fileName, setFileName] = useState("");
    const [error, setError] = useState("");

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setError(""); // Clear any previous errors

        if (!file.name.endsWith(".pgn")) {
            setError("Please upload a valid .pgn file");
            return;
        }

        const reader = new FileReader();
        reader.onload = (event) => {
            const content = event.target?.result as string;
            if (content.trim()) {
                setFileName(file.name);
                loadPGN(content);
            } else {
                setError("The selected file appears to be empty");
            }
        };
        
        reader.onerror = () => {
            setError("Error reading the file");
        };
        
        reader.readAsText(file);
    };

    return (
        <Paper
            elevation={3}
            sx={{
                p: 3,
                backgroundColor: purpleTheme.background.paper,
                color: purpleTheme.text.primary,
            }}
        >
            <Typography 
                variant="h6" 
                sx={{ 
                    color: purpleTheme.text.primary,
                    mb: 2,
                    textAlign: "center"
                }}
            >
                Upload PGN File
            </Typography>
            
            <Typography 
                variant="subtitle2" 
                sx={{ 
                    color: purpleTheme.text.secondary,
                    mb: 3,
                    textAlign: "center"
                }}
            >
                Upload a single PGN file to analyze your game
            </Typography>

            {error && (
                <Alert 
                    severity="error" 
                    sx={{ 
                        mb: 2,
                        backgroundColor: purpleTheme.background.card,
                        color: purpleTheme.text.primary,
                        '& .MuiAlert-icon': {
                            color: purpleTheme.accent
                        }
                    }}
                >
                    {error}
                </Alert>
            )}

            <Stack spacing={2} alignItems="center">
                <Button
                    variant="contained"
                    component="label"
                    startIcon={<UploadFileIcon />}
                    sx={{
                        backgroundColor: purpleTheme.primary,
                        color: purpleTheme.text.primary,
                        '&:hover': {
                            backgroundColor: purpleTheme.primaryDark,
                        },
                        minWidth: 200,
                        py: 1.5,
                    }}
                >
                    Choose PGN File
                    <input
                        type="file"
                        accept=".pgn"
                        hidden
                        onChange={handleFileChange}
                    />
                </Button>

                {fileName && (
                    <Box
                        sx={{
                            p: 2,
                            backgroundColor: purpleTheme.background.card,
                            borderRadius: 1,
                            border: `1px solid ${purpleTheme.secondary}`,
                            textAlign: "center",
                        }}
                    >
                        <Typography 
                            variant="body2" 
                            sx={{ color: purpleTheme.text.secondary }}
                        >
                            Selected file:
                        </Typography>
                        <Typography 
                            variant="body1" 
                            sx={{ 
                                color: purpleTheme.text.accent,
                                fontWeight: "medium"
                            }}
                        >
                            {fileName}
                        </Typography>
                    </Box>
                )}
            </Stack>
        </Paper>
    );
};

export default UserPGNUploader;