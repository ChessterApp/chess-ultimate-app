import { Box, Paper } from "@mui/material";
import ReactMarkdown from "react-markdown";

interface ChatBubbleProps {
  message: string;
  isUser?: boolean;
}

export default function ChatBubble({ message, isUser = false }: ChatBubbleProps) {
  return (
    <Box display="flex" justifyContent={isUser ? "flex-end" : "flex-start"} my={1}>
      <Paper
        sx={{
          p: 2,
          maxWidth: "75%",
          bgcolor: isUser ? "purple" : "#f5f5dc", 
          color: "black",
          borderRadius: 3,
          fontFamily: "monospace",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
        elevation={3}
      >
        <ReactMarkdown>{message}</ReactMarkdown>
      </Paper>
    </Box>
  );
}
