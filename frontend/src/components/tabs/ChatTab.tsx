import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useTranslations } from "next-intl";
import { Send, MenuBook, Close, ContentCopy, History, Stop, Settings as SettingsIcon, VolumeUp, VolumeOff, Visibility, DeleteOutline, Mic, Stop as StopIcon } from "@mui/icons-material";
import OpenInFullIcon from '@mui/icons-material/OpenInFull';
import { BookmarkAdd } from "@mui/icons-material";
import { Bookmark } from "@mui/icons-material";
import ReactMarkdown from "react-markdown";
import { Chessboard } from "react-chessboard";
import {
  Stack,
  Box,
  Typography,
  Switch,
  Button,
  Paper,
  TextField,
  CircularProgress,
  Chip,
  Avatar,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  Tooltip,
  Snackbar,
  Alert,
  Menu,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  Select,
  FormControl,
  InputLabel,
  useTheme,
} from "@mui/material";
// ModelSetting removed - using server-managed LLM
// import ModelSetting from "./ModelSetting";
import { ChatMessage } from "../../hooks/useChesster";
import useVoiceRecorder from "../../hooks/useVoiceRecorder";
import CoachToggle from "../coach/CoachToggle";
import { calculateChatPrice } from "@/libs/docs/helper";
import { useLocalStorage } from "usehooks-ts";
import { DEFAULT_CHAT_AUTOSCROLL, DEFAULT_CHAT_COMPACT_VIEW, DEFAULT_CHAT_FONT_SIZE, DEFAULT_CHAT_DIMENSIONS, DEFAULT_CHAT_SHOW_TIMESTAMP, DEFAULT_CHAT_SPEECH_PITCH, DEFAULT_CHAT_SPEECH_RATE, DEFAULT_CHAT_SPEECH_VOICE, DEFAULT_CHAT_SPEECH_VOLUME, DEFAULT_CHAT_TECHNICAL_INFO } from "@/libs/setting/helper";

export interface ChatTabProps {
  sessionMode: boolean;
  setSessionMode: (checked: boolean) => void;
  clearChatHistory: () => void;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  isStreaming: boolean;
  gameInfo?: string;
  currentMove?: string;
  chatInput: string;
  puzzleMode?: boolean;
  playMode?: boolean;
  puzzleQuery?: string;
  setChatInput: (value: string) => void;
  handleChatKeyPress: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  sendChatMessage: (
    gameInfo?: string,
    currentMove?: string,
    puzzleMode?: boolean,
    puzzleQuery?: string,
    playMode?: boolean,
    questionMode?: boolean
  ) => void;
  abortChatMessage?: () => void;
  isCoachMode?: boolean;
  onCoachModeToggle?: (enabled: boolean) => void;
}

interface SavedPosition {
  id: string;
  fen: string;
  analysis: string;
  timestamp: Date;
  title?: string;
}


// Prompt key arrays — values come from useTranslations('chat') inside the component
const sessionPromptKeys = [
  "promptSilman", "promptFine", "promptHowPlay", "promptEyeCatch",
  "promptGoodBad", "promptGutFeeling", "promptTactics", "promptApproach",
  "promptWhatDo", "promptInteresting", "promptThoughts", "promptFeelsRight",
  "promptWhatThink",
];

const puzzlePromptKeys = [
  "promptHints", "promptPuzzleApproach", "promptWhatSee",
  "promptIdeas", "promptFirstThought", "promptNudge",
];

const playPromptKeys = [
  "promptPlayHere", "promptCastle", "promptAttack", "promptThreat",
  "promptOpponent", "promptTrade", "promptSafe", "promptPlan",
  "promptPawns", "promptCoordinate", "promptTacticsBrewing", "promptDevelop",
];

const chatPromptKeys = [
  "promptBasics", "promptImprove", "promptFavTactics", "promptStories",
  "promptOpenings", "promptEndgames", "promptStratVsTact", "promptStrongPlayers",
  "promptPrinciples", "promptCalculate", "promptPawnStructures",
  "promptPositionalVsTactical", "promptTimeManagement", "promptOpeningMistakes",
  "promptKingSafety", "promptPatterns",
];

export const ChatTab: React.FC<ChatTabProps> = ({
  sessionMode,
  setSessionMode,
  clearChatHistory,
  chatMessages,
  chatLoading,
  isStreaming,
  chatInput,
  setChatInput,
  handleChatKeyPress,
  sendChatMessage,
  abortChatMessage,
  gameInfo,
  currentMove,
  puzzleMode = false,
  playMode = false,
  puzzleQuery,
  isCoachMode = false,
  onCoachModeToggle,
}) => {
  const t = useTranslations('chat');
  const theme = useTheme();

  // Translated prompt arrays (memoized to avoid re-creating on every render)
  const sessionPrompts = useMemo(() => sessionPromptKeys.map(k => t(k)), [t]);
  const puzzlePrompts = useMemo(() => puzzlePromptKeys.map(k => t(k)), [t]);
  const playPrompts = useMemo(() => playPromptKeys.map(k => t(k)), [t]);
  const chatPrompts = useMemo(() => chatPromptKeys.map(k => t(k)), [t]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [copySnackbar, setCopySnackbar] = useState(false);
  const [copyMenuAnchor, setCopyMenuAnchor] = useState<null | HTMLElement>(null);
  const [chessboardModalOpen, setChessboardModalOpen] = useState(false);
  const [selectedFen, setSelectedFen] = useState<string>("");
  
  const [savedPositions, setSavedPositions] = useLocalStorage<SavedPosition[]>(
    "agine_position_library",
    []
  );
  const [questionMode, setQuestionMode] = useLocalStorage<boolean>(
    "agine_question_mode",
    false
  )
 
  const [libraryOpen, setLibraryOpen] = useState(false);

  const [autoScroll, setAutoScroll] = useLocalStorage<boolean>(
    "chat_ui_autoscroll",
    DEFAULT_CHAT_AUTOSCROLL
  )
  const [fontSize, setFontSize] = useLocalStorage<number>(
    "chat_ui_font_size",
    DEFAULT_CHAT_FONT_SIZE
  )
  const [showTimestamps, setShowTimestamps] = useLocalStorage<boolean>(
    "chat_ui_timestamp",
    DEFAULT_CHAT_SHOW_TIMESTAMP
  )
  const [showTechnicalInfo, setTechnicalInfo] = useLocalStorage<boolean>(
    "chat_ui_technical_info",
    DEFAULT_CHAT_TECHNICAL_INFO
  )
  const [compactView, setCompactView] = useLocalStorage<boolean>(
    "chat_ui_compact_view",
    DEFAULT_CHAT_COMPACT_VIEW
  )
  
  // Voice Input state
  const [autoSendVoice, setAutoSendVoice] = useLocalStorage<boolean>("chat_voice_autosend", true);
  const [voiceErrorSnackbar, setVoiceErrorSnackbar] = useState<string | null>(null);
  const [pendingVoiceSend, setPendingVoiceSend] = useState(false);

  const {
    isRecording,
    isTranscribing,
    isSupported: voiceSupported,
    recordingDuration,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useVoiceRecorder({
    onTranscriptionComplete: (text) => {
      setChatInput(text);
      if (autoSendVoice) {
        setPendingVoiceSend(true);
      }
    },
    onError: (err) => {
      setVoiceErrorSnackbar(err);
    },
  });

  // Auto-send voice message after chatInput state has been updated by React
  useEffect(() => {
    if (pendingVoiceSend && chatInput.trim()) {
      setPendingVoiceSend(false);
      sendChatMessage(gameInfo, currentMove, puzzleMode, puzzleQuery, playMode, questionMode);
    }
  }, [pendingVoiceSend, chatInput]);

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Text-to-Speech state
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [currentSpeakingId, setCurrentSpeakingId] = useState<string | null>(null);
  const [speechRate, setSpeechRate] = useLocalStorage<number>(
    "chat_ui_speech_rate",
    DEFAULT_CHAT_SPEECH_RATE
  )
  const [speechPitch, setSpeechPitch] = useLocalStorage<number>(
    "chat_ui_speech_pitch",
    DEFAULT_CHAT_SPEECH_PITCH
  )
  const [speechVolume, setSpeechVolume] = useLocalStorage<number>(
    "chat_ui_speech_volume",
    DEFAULT_CHAT_SPEECH_VOLUME
  )
  const [selectedVoice, setSelectedVoice] = useLocalStorage<string>(
    "chat_ui_speech_voice",
    DEFAULT_CHAT_SPEECH_VOICE
  )
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [speechEnabled, setSpeechEnabled] = useState(true);
  
  // Resize functionality
  const [dimensions, setDimensions] = useLocalStorage<{width: number, height: number}>(
    "chat_ui_chat_dimensions",
    DEFAULT_CHAT_DIMENSIONS
  )
  const [isResizing, setIsResizing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const startPosRef = useRef({ x: 0, y: 0 });
  const startDimensionsRef = useRef({ width: 0, height: 0 });
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Initialize speech synthesis
  useEffect(() => {
    if ('speechSynthesis' in window) {
      const loadVoices = () => {
        const voices = speechSynthesis.getVoices();
        setAvailableVoices(voices);
        
        // Try to find a good default voice
        const englishVoices = voices.filter(voice => voice.lang.startsWith('en'));
        const preferredVoice = englishVoices.find(voice => voice.name.includes('Female')) || 
                              englishVoices.find(voice => voice.name.includes('Natural')) ||
                              englishVoices[0];
        
        if (preferredVoice && !selectedVoice) {
          setSelectedVoice(preferredVoice.name);
        }
      };

      // Load voices immediately if available
      loadVoices();
      
      // Also listen for the voiceschanged event (needed for some browsers)
      speechSynthesis.addEventListener('voiceschanged', loadVoices);
      
      return () => {
        speechSynthesis.removeEventListener('voiceschanged', loadVoices);
      };
    } else {
      setSpeechEnabled(false);
    }
  }, [selectedVoice]);

  // Clean up speech when component unmounts
  useEffect(() => {
    return () => {
      if ('speechSynthesis' in window) {
        speechSynthesis.cancel();
      }
    };
  }, []);

  // Smooth auto-scroll during streaming
  useEffect(() => {
    if (!isStreaming || !autoScroll) return;

    const interval = setInterval(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 100);

    return () => clearInterval(interval);
  }, [isStreaming, autoScroll]);

  // Position Library functions
  const savePositionToLibrary = (message: ChatMessage) => {
    if (!message.fen || message.role !== 'assistant') return;
    
    const newPosition: SavedPosition = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      fen: message.fen,
      analysis: message.content,
      timestamp: message.timestamp,
      title: `Analysis from ${message.timestamp.toLocaleDateString()}`
    };
    
    setSavedPositions(prev => [newPosition, ...prev]);
  };

  const deletePositionFromLibrary = (positionId: string) => {
    setSavedPositions(prev => prev.filter(pos => pos.id !== positionId));
  };

  const viewPositionFromLibrary = (position: SavedPosition) => {
    setSelectedFen(position.fen);
    setChessboardModalOpen(true);
    setLibraryOpen(false);
  };

  const isPositionSaved = (fen: string) => {
    return savedPositions.some(pos => pos.fen === fen);
  };

  // Text-to-Speech functions
  const stripMarkdown = (text: string): string => {
    return text
      .replace(/[*_`~]/g, '') // Remove markdown formatting
      .replace(/#+\s/g, '') // Remove headers
      .replace(/>\s/g, '') // Remove blockquotes
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // Convert links to just text
      .replace(/\n+/g, ' ') // Replace newlines with spaces
      .trim();
  };

  const speakMessage = (messageId: string, content: string) => {
    if (!speechEnabled || !('speechSynthesis' in window)) return;

    // Stop any current speech
    speechSynthesis.cancel();
    
    if (currentSpeakingId === messageId && isSpeaking) {
      // If clicking the same message that's playing, stop it
      setIsSpeaking(false);
      setCurrentSpeakingId(null);
      return;
    }

    const cleanText = stripMarkdown(content);
    
    if (!cleanText.trim()) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    
    // Find the selected voice
    const voice = availableVoices.find(v => v.name === selectedVoice);
    if (voice) {
      utterance.voice = voice;
    }
    
    utterance.rate = speechRate;
    utterance.pitch = speechPitch;
    utterance.volume = speechVolume;

    utterance.onstart = () => {
      setIsSpeaking(true);
      setCurrentSpeakingId(messageId);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      setCurrentSpeakingId(null);
    };

    utterance.onerror = () => {
      setIsSpeaking(false);
      setCurrentSpeakingId(null);
    };

    speechSynthesis.speak(utterance);
  };

  const stopSpeaking = () => {
    if ('speechSynthesis' in window) {
      speechSynthesis.cancel();
      setIsSpeaking(false);
      setCurrentSpeakingId(null);
    }
  };

  // Chessboard modal functions
  const openChessboardModal = (fen: string) => {
    setSelectedFen(fen);
    setChessboardModalOpen(true);
  };

  const openLibraryModal = () => {
    setLibraryOpen(true);
  }

  const closeLibraryModal = () => {
    setLibraryOpen(false);
  }

  const closeChessboardModal = () => {
    setChessboardModalOpen(false);
    setSelectedFen("");
  };

  // Resize handler
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    startPosRef.current = { x: e.clientX, y: e.clientY };
    startDimensionsRef.current = { ...dimensions };

    const handleMouseMove = (e: MouseEvent) => {
      const deltaX = e.clientX - startPosRef.current.x;
      const deltaY = e.clientY - startPosRef.current.y;
      
      // Set min and max limits
      const minWidth = 350;
      const maxWidth = 1200;
      const minHeight = 400;
      const maxHeight = 900;
      
      const newWidth = Math.min(maxWidth, Math.max(minWidth, startDimensionsRef.current.width + deltaX));
      const newHeight = Math.min(maxHeight, Math.max(minHeight, startDimensionsRef.current.height + deltaY));
      
      setDimensions({ width: newWidth, height: newHeight });
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [dimensions]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current && autoScroll) {
      messagesEndRef.current.scrollIntoView({ 
        behavior: "smooth",
        block: "end"
      });
    }
  }, [chatMessages, chatLoading, autoScroll]);

  const handlePromptSelect = (prompt: string) => {
    setChatInput(prompt);
    setDrawerOpen(false);
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopySnackbar(true);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const copyMessage = (content: string) => {
    copyToClipboard(content);
  };

  const copyEntireChat = () => {
    const chatHistory = chatMessages
      .map((msg) => `**${msg.role === 'user' ? 'You' : 'Chesster'}** (${msg.timestamp.toLocaleString()}):\n${msg.content}`)
      .join('\n\n---\n\n');
    
    copyToClipboard(chatHistory);
    setCopyMenuAnchor(null);
  };

  const handleCopyMenuClick = (event: React.MouseEvent<HTMLElement>) => {
    setCopyMenuAnchor(event.currentTarget);
  };

  const handleCopyMenuClose = () => {
    setCopyMenuAnchor(null);
  };

  const handleAbortMessage = () => {
    if (abortChatMessage) {
      abortChatMessage();
    }
  };

  const handleSettingsClose = () => {
    setSettingsOpen(false);
  };

  // Determine which prompts to show based on mode
  let currentPrompts = sessionMode ? sessionPrompts : chatPrompts;
  let modeTitle = sessionMode ? t("modeBuddyAnalysis") : t("modeChat");
  let modeDescription = sessionMode ? t("descBuddyAnalysis") : t("descChat");

  if (puzzleMode) {
    currentPrompts = puzzlePrompts;
    modeTitle = t("modePuzzle");
    modeDescription = t("descPuzzle");
  } else if (playMode) {
    currentPrompts = playPrompts;
    modeTitle = t("modeGame");
    modeDescription = t("descGame");
  }

  const drawerContent = (
    <Box sx={{ width: { xs: 280, sm: 350 }, height: "100%" }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          p: 2,
          borderBottom: 1, borderColor: 'divider',
          backgroundColor: "background.paper",
        }}
      >
        <Typography variant="subtitle1" sx={{ color: "text.primary", fontWeight: 600 }}>
          {modeTitle}
        </Typography>
        <IconButton
          onClick={() => setDrawerOpen(false)}
          sx={{ color: "text.primary" }}
          size="small"
        >
          <Close />
        </IconButton>
      </Box>
      
      <List sx={{ p: 0, backgroundColor: "background.paper", height: "calc(100% - 80px)" }}>
        {currentPrompts.map((prompt, index) => (
          <ListItem key={index} disablePadding>
            <ListItemButton
              onClick={() => handlePromptSelect(prompt)}
              sx={{
                py: 1.5,
                px: 2,
                borderBottom: index < currentPrompts.length - 1 ? 1 : "none", borderColor: 'divider',
                "&:hover": {
                  backgroundColor: "action.hover",
                },
              }}
            >
              <ListItemText
                primary={prompt}
                sx={{
                  "& .MuiListItemText-primary": {
                    color: "text.primary",
                    fontSize: "0.9rem",
                    lineHeight: 1.4,
                  },
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      
      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider', backgroundColor: "background.paper" }}>
        <Typography variant="caption" sx={{ color: "grey.400", fontStyle: "italic" }}>
          💡 Click any prompt to get started
        </Typography>
      </Box>
    </Box>
  );

  const libraryContent = (
  <Box sx={{
    width: { xs: "100%", sm: 700, md: 800 },
    maxWidth: "100%",
    height: "100%",
    display: "flex",
    flexDirection: "column"
  }}>
    {/* Content Area */}
    <Box sx={{ 
      flex: 1,
      overflowY: "auto",
      backgroundColor: "background.paper",
      '&::-webkit-scrollbar': {
        width: '6px',
      },
      '&::-webkit-scrollbar-track': {
        background: 'var(--surface-card)',
      },
      '&::-webkit-scrollbar-thumb': {
        background: 'var(--text-secondary)',
        borderRadius: '3px',
      },
    }}>
      {savedPositions.length === 0 ? (
        <Box sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          p: 3,
          color: "text.secondary"
        }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            No saved positions
          </Typography>
          <Typography variant="body2" sx={{ textAlign: "center" }}>
            Save positions with analysis to build your library
          </Typography>
        </Box>
      ) : (
        <Stack spacing={0}>
          {savedPositions.map((position, index) => (
            <Box 
              key={position.id}
              sx={{ 
                display: "flex",
                minHeight: 140,
                borderBottom: index < savedPositions.length - 1 ? 1 : "none", borderColor: 'divider',
                "&:hover": {
                  backgroundColor: "action.hover"
                }
              }}
            >
              {/* Left side - Actual Chessboard */}
              <Box sx={{ 
                width: 200, 
                height: 200, 
                p: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: "background.default",
                borderRight: 1, borderColor: 'divider'
              }}>
                <Box 
                  onClick={() => viewPositionFromLibrary(position)}
                  sx={{
                    cursor: "pointer",
                    "&:hover": {
                      opacity: 0.8
                    }
                  }}
                >
                  <Chessboard
                    position={position.fen || "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}
                    arePiecesDraggable={false}
                    boardWidth={190}
                    customBoardStyle={{
                      borderRadius: "4px",
                      border: `1px solid ${theme.palette.divider}`
                    }}

                  />
                </Box>
              </Box>

              {/* Right side - Position info */}
              <Box sx={{ 
                flex: 1, 
                p: 2,
                display: "flex",
                flexDirection: "column"
              }}>
                {/* Title and date */}
                <Box sx={{ 
                  display: "flex", 
                  justifyContent: "space-between", 
                  alignItems: "flex-start",
                  mb: 1
                }}>
                  <Typography variant="subtitle1" sx={{
                    color: "text.primary",
                    fontWeight: 600,
                    flex: 1
                  }}>
                    {position.title}
                  </Typography>
                  <Typography variant="caption" sx={{
                    color: "text.secondary",
                    ml: 2
                  }}>
                    {new Date(position.timestamp).toLocaleDateString()}
                  </Typography>
                </Box>

                {/* Analysis text */}
                <Typography 
                  variant="body2" 
                  sx={{ 
                    color: "text.primary",
                    lineHeight: 1.5,
                    flex: 1,
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical"
                  }}
                >
                  {position.analysis}
                </Typography>

                {/* Action buttons */}
                <Box sx={{ 
                  display: "flex", 
                  gap: 1, 
                  mt: 1,
                  justifyContent: "flex-end"
                }}>
                  <IconButton
                    onClick={(e) => {
                      e.stopPropagation();
                      viewPositionFromLibrary(position);
                    }}
                    size="small"
                    sx={{
                      color: "text.secondary",
                      "&:hover": { color: "text.primary" }
                    }}
                  >
                    <Visibility fontSize="small" />
                  </IconButton>
                  
                  <IconButton
                    onClick={(e) => {
                      e.stopPropagation();
                      copyMessage(position.analysis);
                    }}
                    size="small"
                    sx={{
                      color: "text.secondary",
                      "&:hover": { color: "text.primary" }
                    }}
                  >
                    <ContentCopy fontSize="small" />
                  </IconButton>
                  
                  <IconButton
                    onClick={(e) => {
                      e.stopPropagation();
                      deletePositionFromLibrary(position.id);
                    }}
                    size="small"
                    sx={{
                      color: "text.secondary",
                      "&:hover": { color: "error.main" }
                    }}
                  >
                    <DeleteOutline fontSize="small" />
                  </IconButton>
                </Box>
              </Box>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  </Box>
);

  return (
    <>
      <style>
        {`
          @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0; }
          }
        `}
      </style>
      <Box
        ref={containerRef}
        sx={{
          width: "100%",
          maxWidth: `${dimensions.width}px`,
          flex: 1,
          minHeight: 0,
          display: "flex",
        flexDirection: "column",
        backgroundColor: "background.paper",
        overflow: "hidden",
        minWidth: 0,
        position: "relative",
        border: 1, borderColor: 'divider',
        borderRadius: 1,
        userSelect: isResizing ? 'none' : 'auto',
      }}
    >
      {/* Header */}
      <Paper
        sx={{
          p: 1.5,
          backgroundColor: "background.paper",
          borderRadius: 0,
          borderBottom: 1, borderColor: 'divider',
          flexShrink: 0,
        }}
      >
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Avatar
              src="/static/images/chesster-logo-v3.png"
              sx={{
                width: 20,
                height: 20,
                backgroundColor: "white",
                p: 0.25,
              }}
            />
            <Typography variant="subtitle2" sx={{
              color: "text.primary",
              fontWeight: 600,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: "200px"
            }}>
              {t("title")}
            </Typography>
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          
          {/* Action Buttons */}
          <Stack direction="row" spacing={0.5}>
            <Tooltip title={t("conversationStarters")} arrow>
              <IconButton
                onClick={() => setDrawerOpen(true)}
                sx={{ color: "text.primary", p: 0.5 }}
                size="small"
              >
                <MenuBook fontSize="small" />
              </IconButton>
            </Tooltip>

            <Tooltip title={t("positionLibrary")} arrow>
              <IconButton
                onClick={openLibraryModal}
                sx={{ 
                  color: savedPositions.length > 0 ? "primary.main" : "text.primary",
                  p: 0.5,
                  position: "relative"
                }}
                size="small"
              >
                <Bookmark fontSize="small" />
                {savedPositions.length > 0 && (
                  <Box
                    sx={{
                      position: "absolute",
                      top: -2,
                      right: -2,
                      width: 12,
                      height: 12,
                      backgroundColor: "primary.main",
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "8px",
                      fontWeight: "bold",
                      color: "white"
                    }}
                  >
                    {savedPositions.length > 9 ? "9+" : savedPositions.length}
                  </Box>
                )}
              </IconButton>
            </Tooltip>

            {chatMessages.length > 0 && (
              <Tooltip title={t("chatHistory")} arrow>
                <IconButton
                  onClick={handleCopyMenuClick}
                  sx={{ color: "text.primary", p: 0.5 }}
                  size="small"
                >
                  <History fontSize="small" />
                </IconButton>
              </Tooltip>
            )}

            {speechEnabled && isSpeaking && (
              <Tooltip title={t("stopSpeaking")} arrow>
                <IconButton
                  onClick={stopSpeaking}
                  sx={{ color: "error.main", p: 0.5 }}
                  size="small"
                >
                  <VolumeOff fontSize="small" />
                </IconButton>
              </Tooltip>
            )}

            <CoachToggle
              isCoachMode={isCoachMode}
              onToggle={onCoachModeToggle ?? (() => {})}
            />

            <Tooltip title={t("settings")} arrow>
              <IconButton
                onClick={() => setSettingsOpen(true)}
                sx={{ color: "text.primary", p: 0.5 }}
                size="small"
              >
                <SettingsIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>

        {/* Mode Controls moved to Settings dialog */}

        {(puzzleMode || playMode) && (
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Chip 
              label={modeTitle}
              size="small"
              sx={{ 
                backgroundColor: "primary.main",
                color: "white",
                fontWeight: 500,
                fontSize: '11px'
              }} 
            />
            <Typography variant="caption" sx={{ color: "grey.400", fontSize: '10px' }}>
              {modeDescription}
            </Typography>
            <Box sx={{ flexGrow: 1 }} />
            {chatMessages.length > 0 && (
              <Button
                variant="outlined"
                size="small"
                onClick={clearChatHistory}
                sx={{
                  color: "text.primary",
                  borderColor: "divider",
                  fontSize: '11px',
                  py: 0.5,
                  px: 1,
                  "&:hover": {
                    borderColor: "primary.main",
                    backgroundColor: "rgba(156, 39, 176, 0.1)",
                  }
                }}
              >
                {t("clear")}
              </Button>
            )}
          </Stack>
        )}
      </Paper>

      {/* Chat Messages */}
      <Box
        ref={chatContainerRef}
        sx={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          overflowX: "hidden",
          backgroundColor: "background.paper",
          position: "relative",
          px: 1.5,
          py: 1,
          '&::-webkit-scrollbar': {
            width: '6px',
          },
          '&::-webkit-scrollbar-track': {
            background: 'var(--surface-card)',
            borderRadius: '3px',
          },
          '&::-webkit-scrollbar-thumb': {
            background: 'var(--text-secondary)',
            borderRadius: '3px',
            '&:hover': {
              background: 'var(--text-secondary)',
            },
          },
        }}
      >
        {chatMessages.length === 0 ? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              color: "text.primary",
              p: 2,
            }}
          >
            <Avatar
              src="/static/images/chesster-logo-v3.png"
              sx={{
                width: 50,
                height: 50,
                mb: 2,
                backgroundColor: "white",
                p: 0.5,
              }}
            />
            <Typography variant="subtitle1" sx={{
              mb: 1,
              textAlign: "center",
              fontWeight: 500,
              maxWidth: "100%",
              wordWrap: "break-word"
            }}>
              {playMode
                ? t("welcomePlay")
                : puzzleMode
                ? t("welcomePuzzle")
                : t("welcomeDefault")
              }
            </Typography>
            <Typography variant="caption" sx={{
              mb: 2,
              textAlign: "center",
              color: "grey.300",
              maxWidth: "90%",
              wordWrap: "break-word"
            }}>
              {playMode
                ? t("subtitlePlay")
                : puzzleMode
                ? t("subtitlePuzzle")
                : sessionMode
                ? t("subtitleSession")
                : t("subtitleChat")
              }
            </Typography>
            
            {/* Conversation starters removed for cleaner mobile UX */}
          </Box>
        ) : (
          <Stack spacing={compactView ? 0.5 : 1} sx={{ width: "100%", minWidth: 0 }}>
            {chatMessages.map((message, index) => {
              const isLastMessage = index === chatMessages.length - 1;
              const isLastAssistantMessage = message.role === "assistant" && isLastMessage;
              const shouldShowCursor = isStreaming && isLastAssistantMessage;
              const shouldDeferMarkdown = isStreaming && isLastAssistantMessage;

              return (
              <Box
                key={message.id}
                sx={{
                  display: "flex",
                  justifyContent: message.role === "user" ? "flex-end" : "flex-start",
                  alignItems: "flex-start",
                  width: "100%",
                  minWidth: 0,
                }}
              >
                {/* Avatar for assistant messages */}
                {message.role === "assistant" && (
                  <Avatar
                    src="/static/images/chesster-logo-v3.png"
                    sx={{
                      width: compactView ? 24 : 28,
                      height: compactView ? 24 : 28,
                      mr: 1,
                      mt: 0.5,
                      flexShrink: 0,
                      backgroundColor: "white",
                      p: 0.25,
                    }}
                  />
                )}

                <Paper
                  sx={{
                    p: compactView ? 1 : 1.5,
                    maxWidth: "80%",
                    minWidth: 0,
                    backgroundColor: message.role === "user" ? "info.main" : "primary.dark",
                    color: "white",
                    borderRadius: 2,
                    position: "relative",
                    wordWrap: "break-word",
                    overflowWrap: "break-word",
                    wordBreak: "break-word",
                    whiteSpace: "pre-wrap",
                    "&:hover .message-actions": {
                      opacity: 1,
                    },
                  }}
                >
                  {/* Message Actions */}
                  {message.role === "assistant" && (
                    <Box
                      className="message-actions"
                      sx={{
                        position: "absolute",
                        top: 4,
                        right: 4,
                        opacity: 0,
                        transition: "opacity 0.2s",
                        display: "flex",
                        gap: 0.25,
                        flexWrap: "wrap",
                        maxWidth: "80px",
                        justifyContent: "flex-end",
                      }}
                    >
                       {/* Save to Library icon - only show for assistant messages with FEN */}
                      {message.fen && (
                        <Tooltip title={isPositionSaved(message.fen) ? "Position already saved" : "Save to position library"} arrow>
                          <IconButton
                            onClick={() => savePositionToLibrary(message)}
                            disabled={isPositionSaved(message.fen)}
                            sx={{
                              color: isPositionSaved(message.fen) ? "rgba(156, 39, 176, 0.5)" : "rgba(255, 255, 255, 0.7)",
                              backgroundColor: "rgba(0, 0, 0, 0.2)",
                              "&:hover": {
                                backgroundColor: "rgba(0, 0, 0, 0.4)",
                                color: isPositionSaved(message.fen) ? "rgba(156, 39, 176, 0.7)" : "primary.main",
                              },
                              "&:disabled": {
                                color: "rgba(156, 39, 176, 0.5)",
                              }
                            }}
                            size="small"
                          >
                            <BookmarkAdd fontSize="inherit" />
                          </IconButton>
                        </Tooltip>
                      )}

                      {/* Eye icon for viewing chessboard - only show if FEN exists */}
                      {message.fen && (
                        <Tooltip title={t("viewOnBoard")} arrow>
                          <IconButton
                            onClick={() => openChessboardModal(message.fen!)}
                            sx={{
                              color: "rgba(255, 255, 255, 0.7)",
                              backgroundColor: "rgba(0, 0, 0, 0.2)",
                              "&:hover": {
                                backgroundColor: "rgba(0, 0, 0, 0.4)",
                                color: "white",
                              },
                            }}
                            size="small"
                          >
                            <Visibility fontSize="inherit" />
                          </IconButton>
                        </Tooltip>
                      )}
                      
                      {speechEnabled && (
                        <Tooltip title={currentSpeakingId === message.id && isSpeaking ? t("stopSpeaking") : t("listenToMessage")} arrow>
                          <IconButton
                            onClick={() => speakMessage(message.id, message.content)}
                            sx={{
                              color: currentSpeakingId === message.id && isSpeaking ? "error.main" : "rgba(255, 255, 255, 0.7)",
                              backgroundColor: "rgba(0, 0, 0, 0.2)",
                              "&:hover": {
                                backgroundColor: "rgba(0, 0, 0, 0.4)",
                                color: "white",
                              },
                            }}
                            size="small"
                          >
                            {currentSpeakingId === message.id && isSpeaking ? (
                              <VolumeOff fontSize="inherit" />
                            ) : (
                              <VolumeUp fontSize="inherit" />
                            )}
                          </IconButton>
                        </Tooltip>
                      )}
                      <Tooltip title={t("copyMessage")} arrow>
                        <IconButton
                          onClick={() => copyMessage(message.content)}
                          sx={{
                            color: "rgba(255, 255, 255, 0.7)",
                            backgroundColor: "rgba(0, 0, 0, 0.2)",
                            "&:hover": {
                              backgroundColor: "rgba(0, 0, 0, 0.4)",
                              color: "white",
                            },
                          }}
                          size="small"
                        >
                          <ContentCopy fontSize="inherit" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  )}
                  
                  {message.role === "assistant" ? (
                    shouldDeferMarkdown ? (
                      <Typography
                        variant="body2"
                        sx={{
                          fontSize: `${fontSize}px`,
                          lineHeight: compactView ? 1.2 : 1.4,
                          wordWrap: "break-word",
                          overflowWrap: "break-word",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {message.content}
                        {shouldShowCursor && (
                          <span
                            style={{
                              display: "inline-block",
                              width: "8px",
                              height: "1em",
                              marginLeft: "2px",
                              backgroundColor: "currentColor",
                              animation: "blink 530ms step-end infinite",
                            }}
                          />
                        )}
                      </Typography>
                    ) : (
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => (
                            <Typography
                              variant="body2"
                              component="p"
                              sx={{
                                mb: 0.5,
                                "&:last-child": { mb: 0 },
                                fontSize: `${fontSize}px`,
                                lineHeight: compactView ? 1.2 : 1.4,
                                wordWrap: "break-word",
                                overflowWrap: "break-word",
                              }}
                            >
                              {children}
                            </Typography>
                          ),
                          ul: ({ children }) => (
                            <Box component="ul" sx={{
                              pl: 2,
                              mb: 0.5,
                              maxWidth: "100%",
                              overflow: "hidden"
                            }}>
                              {children}
                            </Box>
                          ),
                          li: ({ children }) => (
                            <Typography
                              component="li"
                              variant="body2"
                              sx={{
                                mb: 0.25,
                                fontSize: `${fontSize}px`,
                                wordWrap: "break-word",
                                overflowWrap: "break-word",
                              }}
                            >
                              {children}
                            </Typography>
                          ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    )
                  ) : (
                    <Typography
                      variant="body2"
                      sx={{
                        fontSize: `${fontSize}px`,
                        lineHeight: compactView ? 1.2 : 1.4,
                        wordWrap: "break-word",
                        overflowWrap: "break-word",
                      }}
                    >
                      {message.content}
                    </Typography>
                  )}
                  {showTimestamps && (
                    <Typography
                      variant="caption"
                      sx={{
                        opacity: 0.7,
                        display: "block",
                        mt: 0.5,
                        fontSize: `${fontSize - 2}px`,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis"
                      }}
                    >
                      {message.timestamp.toLocaleTimeString()}
                    </Typography>
                  )}
                  {showTechnicalInfo && message.maxTokens && message.model && message.provider && (
                    <Typography
                      variant="caption"
                      sx={{
                        opacity: 0.7,
                        display: "block",
                        mt: 0.5,
                        fontSize: `${fontSize - 2}px`,
                        wordWrap: "break-word",
                        overflowWrap: "break-word"
                      }}
                    >
                      Tokens: {message.maxTokens} Cost: ${calculateChatPrice(message.maxTokens, message.model)}, {message.provider}: {message.model}
                    </Typography>
                  )}

                </Paper>
              </Box>
            );
            })}
            {chatLoading && !isStreaming && (
              <Box
                sx={{
                  display: "flex",
                  justifyContent: "flex-start",
                  alignItems: "flex-start",
                }}
              >
                <Avatar
                  src="/static/images/chesster-logo-v3.png"
                  sx={{
                    width: compactView ? 24 : 28,
                    height: compactView ? 24 : 28,
                    mr: 1,
                    mt: 0.5,
                    flexShrink: 0,
                    backgroundColor: "white",
                    p: 0.25,
                  }}
                />
                <Paper
                  sx={{
                    p: compactView ? 1 : 1.5,
                    backgroundColor: "primary.dark",
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    borderRadius: 2,
                    maxWidth: "80%",
                  }}
                >
                  <CircularProgress size={14} sx={{ color: "white" }} />
                  <Typography variant="caption" sx={{ color: "white", fontSize: `${fontSize}px` }}>
                    Chesster is thinking...
                  </Typography>
                  {abortChatMessage && (
                    <Tooltip title={t("stopResponse")} arrow>
                      <IconButton
                        onClick={handleAbortMessage}
                        size="small"
                        sx={{
                          color: "white",
                          ml: 0.5,
                          "&:hover": {
                            backgroundColor: "rgba(255, 255, 255, 0.1)",
                          },
                        }}
                      >
                        <Stop fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Paper>
              </Box>
            )}
            {/* Invisible div for auto-scroll */}
            <div ref={messagesEndRef} />
          </Stack>
        )}
      </Box>

      {/* Chat Input */}
      <Paper
        sx={{
          p: 1.5,
          backgroundColor: "background.paper",
          borderRadius: 0,
          borderTop: 1, borderColor: 'divider',
          flexShrink: 0,
        }}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          {isRecording ? (
            <>
              <Box sx={{ display: 'flex', alignItems: 'center', flex: 1, gap: 1, px: 1 }}>
                <Box
                  sx={{
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    backgroundColor: "error.main",
                    animation: 'pulse 1.5s ease-in-out infinite',
                    '@keyframes pulse': {
                      '0%, 100%': { opacity: 1 },
                      '50%': { opacity: 0.3 },
                    },
                  }}
                />
                <Typography variant="body2" sx={{ color: "error.main", fontWeight: 500 }}>
                  {t("recording", { duration: formatDuration(recordingDuration) })}
                </Typography>
              </Box>
              <IconButton
                onClick={stopRecording}
                size="small"
                sx={{ color: "error.main", '&:hover': { backgroundColor: 'rgba(244,67,54,0.1)' } }}
              >
                <StopIcon fontSize="small" />
              </IconButton>
              <IconButton
                onClick={cancelRecording}
                size="small"
                sx={{ color: 'grey.500', '&:hover': { backgroundColor: 'rgba(255,255,255,0.05)' } }}
              >
                <Close fontSize="small" />
              </IconButton>
            </>
          ) : isTranscribing ? (
            <Box sx={{ display: 'flex', alignItems: 'center', flex: 1, gap: 1, px: 1 }}>
              <CircularProgress size={18} sx={{ color: "primary.main" }} />
              <Typography variant="body2" sx={{ color: 'grey.400' }}>
                Transcribing your message...
              </Typography>
            </Box>
          ) : (
            <>
              <TextField
                fullWidth
                multiline
                maxRows={3}
                placeholder={
                  playMode
                    ? t("placeholderPlay")
                    : puzzleMode
                      ? t("placeholderPuzzle")
                      : sessionMode
                        ? t("placeholderSession")
                        : t("placeholderChat")
                }
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={handleChatKeyPress}
                disabled={chatLoading}
                size="small"
                sx={{
                  minWidth: 0,
                  "& .MuiOutlinedInput-root": {
                    backgroundColor: "rgba(255,255,255,0.05)",
                    "& fieldset": {
                      borderColor: "rgba(255,255,255,0.2)",
                    },
                    "&:hover fieldset": {
                      borderColor: "rgba(255,255,255,0.3)",
                    },
                    "&.Mui-focused fieldset": {
                      borderColor: "primary.main",
                    },
                  },
                }}
                slotProps={{
                  input: {
                    sx: {
                      color: "text.primary",
                      fontSize: `${fontSize}px`
                    },
                  },
                }}
              />
              {voiceSupported && (
                <IconButton
                  onClick={startRecording}
                  disabled={chatLoading}
                  size="small"
                  sx={{
                    color: 'grey.400',
                    flexShrink: 0,
                    '&:hover': { color: "primary.main", backgroundColor: 'rgba(156,39,176,0.1)' },
                    '&:disabled': { color: 'rgba(255,255,255,0.2)' },
                  }}
                >
                  <Mic fontSize="small" />
                </IconButton>
              )}
              <Button
                variant="contained"
                size="small"
                onClick={() => sendChatMessage(gameInfo, currentMove, puzzleMode, puzzleQuery, playMode, questionMode)}
                disabled={chatLoading || !chatInput.trim()}
                sx={{
                  minWidth: "auto",
                  px: 1.5,
                  flexShrink: 0,
                  backgroundColor: "primary.main",
                  "&:hover": {
                    backgroundColor: "primary.dark",
                  },
                  "&:disabled": {
                    backgroundColor: "rgba(156, 39, 176, 0.3)",
                  }
                }}
              >
                <Send fontSize="small" />
              </Button>
            </>
          )}
        </Stack>
      </Paper>

      {/* Resize Handle */}
      <Box
        onMouseDown={handleMouseDown}
        sx={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          width: '16px',
          height: '16px',
          cursor: 'nw-resize',
          backgroundColor: 'action.hover',
          borderTopRightRadius: '3px',
          opacity: 0.7,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          '&:hover': {
            opacity: 1,
            backgroundColor: 'action.selected',
          },
        }}
      >
        <OpenInFullIcon
          sx={{
            fontSize: '10px',
            color: 'text.secondary',
            transform: 'rotate(180deg)'
          }} 
        />
      </Box>

      {/* Library Modal */}
      <Dialog
        open={libraryOpen}
        onClose={closeLibraryModal}
        maxWidth="md"
        PaperProps={{
          sx: {
            backgroundColor: "background.paper",
            color: "text.primary",
            minWidth: { xs: "95%", sm: 450 },
            maxWidth: { xs: "95%", sm: 800 },
            maxHeight: "80vh"
          }
        }}
      >
        <DialogTitle sx={{ 
          display: "flex", 
          justifyContent: "space-between", 
          alignItems: "center",
          pb: 1
        }}>
         Chesster Position Library
        </DialogTitle>
        <DialogContent sx={{ p: 2 }}>
          {libraryContent}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeLibraryModal} sx={{ color: "primary.main" }}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Chessboard Modal */}
      <Dialog
        open={chessboardModalOpen}
        onClose={closeChessboardModal}
        maxWidth="md"
        PaperProps={{
          sx: {
            backgroundColor: "background.paper",
            color: "text.primary",
            minWidth: { xs: "95%", sm: 450 },
            maxHeight: "80vh"
          }
        }}
      >
        <DialogTitle sx={{ 
          display: "flex", 
          justifyContent: "space-between", 
          alignItems: "center",
          pb: 1
        }}>
          <Typography variant="h6" sx={{ color: "text.primary" }}>
            Position View
          </Typography>
          <IconButton onClick={closeChessboardModal} sx={{ color: "text.primary" }}>
            <Close />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 2 }}>
          <Box sx={{ 
            display: "flex", 
            justifyContent: "center",
            maxWidth: 400,
            mx: "auto"
          }}>
            {selectedFen && (
              <Chessboard 
                position={selectedFen}
                arePiecesDraggable={false}
                boardWidth={350}
                customBoardStyle={{
                  borderRadius: "8px",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.3)"
                }}
              />
            )}
          </Box>
          <Typography 
            variant="caption" 
            sx={{ 
              color: "grey.400", 
              display: "block", 
              textAlign: "center", 
              mt: 2,
              fontFamily: "monospace"
            }}
          >
            FEN: {selectedFen}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={() => copyToClipboard(selectedFen)}
            sx={{ color: "primary.main" }}
          >
            Copy FEN
          </Button>
          <Button onClick={closeChessboardModal} sx={{ color: "primary.main" }}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Settings Dialog */}
      <Dialog
        open={settingsOpen}
        onClose={handleSettingsClose}
        PaperProps={{
          sx: {
            backgroundColor: "background.paper",
            color: "text.primary",
            minWidth: { xs: "95%", sm: 400 },
            maxWidth: { xs: "95%", sm: 500 },
            maxHeight: "80vh"
          }
        }}
      >
        <DialogTitle>{t("settingsTitle")}</DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ pt: 1 }}>
            {/* Chat Mode (moved from header) */}
            {!puzzleMode && !playMode && (
              <Box>
                <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                  {t("chatMode")}
                </Typography>
                <Stack spacing={2}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Box>
                      <Typography variant="body2" sx={{ color: "grey.300" }}>
                        {t("positionContext")}
                      </Typography>
                      <Typography variant="caption" sx={{ color: "grey.500" }}>
                        {sessionMode ? t("lookingAtBoard") : t("generalChat")}
                      </Typography>
                    </Box>
                    <Switch
                      checked={sessionMode}
                      onChange={(e) => setSessionMode(e.target.checked)}
                      sx={{
                        '& .MuiSwitch-switchBase.Mui-checked': { color: "primary.main" },
                        '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: "primary.main" },
                      }}
                    />
                  </Stack>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Box>
                      <Typography variant="body2" sx={{ color: "grey.300" }}>
                        {t("interactiveQA")}
                      </Typography>
                      <Typography variant="caption" sx={{ color: "grey.500" }}>
                        {questionMode ? t("interactiveMode") : t("positionalAnalysis")}
                      </Typography>
                    </Box>
                    <Switch
                      checked={questionMode}
                      onChange={(e) => setQuestionMode(e.target.checked)}
                      sx={{
                        '& .MuiSwitch-switchBase.Mui-checked': { color: "primary.main" },
                        '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: "primary.main" },
                      }}
                    />
                  </Stack>
                  {chatMessages.length > 0 && (
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => { clearChatHistory(); handleSettingsClose(); }}
                      sx={{
                        color: "error.main",
                        borderColor: "rgba(244,67,54,0.3)",
                        fontSize: '12px',
                        "&:hover": {
                          borderColor: "error.main",
                          backgroundColor: "rgba(244,67,54,0.1)",
                        }
                      }}
                    >
                      {t("clear")}
                    </Button>
                  )}
                </Stack>
              </Box>
            )}
            {!puzzleMode && !playMode && (
              <Divider sx={{ borderColor: "divider" }} />
            )}

            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                {t("displayOptions")}
              </Typography>
              <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" sx={{ color: "grey.300" }}>
                    {t("autoScroll")}
                  </Typography>
                  <Switch
                    checked={autoScroll}
                    onChange={(e) => setAutoScroll(e.target.checked)}
                    sx={{
                      '& .MuiSwitch-switchBase.Mui-checked': {
                        color: "primary.main",
                      },
                      '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                        backgroundColor: "primary.main",
                      },
                    }}
                  />
                </Stack>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" sx={{ color: "grey.300" }}>
                    {t("showTimestamps")}
                  </Typography>
                  <Switch
                    checked={showTimestamps}
                    onChange={(e) => setShowTimestamps(e.target.checked)}
                    sx={{
                      '& .MuiSwitch-switchBase.Mui-checked': {
                        color: "primary.main",
                      },
                      '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                        backgroundColor: "primary.main",
                      },
                    }}
                  />
                </Stack>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" sx={{ color: "grey.300" }}>
                    {t("showTokensModel")}
                  </Typography>
                  <Switch
                    checked={showTechnicalInfo}
                    onChange={(e) => setTechnicalInfo(e.target.checked)}
                    sx={{
                      '& .MuiSwitch-switchBase.Mui-checked': {
                        color: "primary.main",
                      },
                      '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                        backgroundColor: "primary.main",
                      },
                    }}
                  />
                </Stack>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" sx={{ color: "grey.300" }}>
                    {t("compactView")}
                  </Typography>
                  <Switch
                    checked={compactView}
                    onChange={(e) => setCompactView(e.target.checked)}
                    sx={{
                      '& .MuiSwitch-switchBase.Mui-checked': {
                        color: "primary.main",
                      },
                      '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                        backgroundColor: "primary.main",
                      },
                    }}
                  />
                </Stack>
              </Stack>
            </Box>
            <Divider sx={{ borderColor: "divider" }} />

            {/* Voice Input Settings */}
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                {t("voiceInput")}
              </Typography>
              <Stack spacing={2}>
                {voiceSupported ? (
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Box>
                      <Typography variant="body2" sx={{ color: "grey.300" }}>
                        {t("autoSendTranscription")}
                      </Typography>
                      <Typography variant="caption" sx={{ color: "grey.500" }}>
                        {t("autoSendDescription")}
                      </Typography>
                    </Box>
                    <Switch
                      checked={autoSendVoice}
                      onChange={(e) => setAutoSendVoice(e.target.checked)}
                      sx={{
                        '& .MuiSwitch-switchBase.Mui-checked': { color: "primary.main" },
                        '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: "primary.main" },
                      }}
                    />
                  </Stack>
                ) : (
                  <Typography variant="body2" sx={{ color: "grey.500" }}>
                    {t("voiceUnavailable")}
                  </Typography>
                )}
              </Stack>
            </Box>
            <Divider sx={{ borderColor: "divider" }} />

            {/* Text-to-Speech Settings */}
            {speechEnabled && (
              <>
                <Box>
                  <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                    {t("ttsSettings")}
                  </Typography>
                  <Stack spacing={2}>
                    <FormControl size="small" fullWidth>
                      <InputLabel sx={{ color: "grey.300" }}>{t("voice")}</InputLabel>
                      <Select
                        value={selectedVoice}
                        onChange={(e) => setSelectedVoice(e.target.value)}
                        label={t("voice")}
                        sx={{
                          color: "text.primary",
                          "& .MuiOutlinedInput-notchedOutline": {
                            borderColor: "rgba(255,255,255,0.2)",
                          },
                          "&:hover .MuiOutlinedInput-notchedOutline": {
                            borderColor: "rgba(255,255,255,0.3)",
                          },
                          "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                            borderColor: "primary.main",
                          },
                        }}
                        MenuProps={{
                          PaperProps: {
                            sx: {
                              backgroundColor: "action.hover",
                              color: "text.primary",
                            },
                          },
                        }}
                      >
                        {availableVoices.map((voice) => (
                          <MenuItem key={voice.name} value={voice.name}>
                            {voice.name} ({voice.lang})
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <Box>
                      <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                        {t("speechRate", { rate: speechRate.toFixed(1) })}
                      </Typography>
                      <Box sx={{ px: 1 }}>
                        <input
                          type="range"
                          min={0.5}
                          max={2}
                          step={0.1}
                          value={speechRate}
                          onChange={(e) => setSpeechRate(Number(e.target.value))}
                          style={{
                            width: '100%',
                            accentColor: theme.palette.primary.main
                          }}
                        />
                      </Box>
                    </Box>

                    <Box>
                      <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                        {t("pitch", { pitch: speechPitch.toFixed(1) })}
                      </Typography>
                      <Box sx={{ px: 1 }}>
                        <input
                          type="range"
                          min={0.5}
                          max={2}
                          step={0.1}
                          value={speechPitch}
                          onChange={(e) => setSpeechPitch(Number(e.target.value))}
                          style={{
                            width: '100%',
                            accentColor: theme.palette.primary.main
                          }}
                        />
                      </Box>
                    </Box>

                    <Box>
                      <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                        {t("volume", { volume: Math.round(speechVolume * 100) })}
                      </Typography>
                      <Box sx={{ px: 1 }}>
                        <input
                          type="range"
                          min={0}
                          max={1}
                          step={0.1}
                          value={speechVolume}
                          onChange={(e) => setSpeechVolume(Number(e.target.value))}
                          style={{
                            width: '100%',
                            accentColor: theme.palette.primary.main
                          }}
                        />
                      </Box>
                    </Box>
                  </Stack>
                </Box>
                <Divider sx={{ borderColor: "divider" }} />
              </>
            )}

            {/* Server-managed LLM - No API key configuration needed */}
            <Box sx={{ p: 2, bgcolor: "rgba(156, 39, 176, 0.1)", borderRadius: 1 }}>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1, fontWeight: 500 }}>
                {t("aiModel")}
              </Typography>
              <Typography variant="caption" sx={{ color: "grey.400" }}>
                {t("aiModelDescription")}
              </Typography>
            </Box>

            <Divider sx={{ borderColor: "divider" }} />
            
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                {t("fontSizeLabel", { size: fontSize })}
              </Typography>
              <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                {t("fontSizeDescription")}
              </Typography>
              <Box sx={{ px: 1 }}>
                <input
                  type="range"
                  min={12}
                  max={18}
                  value={fontSize}
                  onChange={(e) => setFontSize(Number(e.target.value))}
                  style={{
                    width: '100%',
                    accentColor: theme.palette.primary.main
                  }}
                />
              </Box>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleSettingsClose} sx={{ color: "primary.main" }}>
            {t("done")}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Copy Menu */}
      <Menu
        anchorEl={copyMenuAnchor}
        open={Boolean(copyMenuAnchor)}
        onClose={handleCopyMenuClose}
        PaperProps={{
          sx: {
            backgroundColor: "background.paper",
            color: "text.primary",
            border: 1, borderColor: 'divider',
          },
        }}
      >
        <MenuItem onClick={copyEntireChat}>
          <ContentCopy sx={{ mr: 1 }} fontSize="small" />
          {t("copyEntireChat")}
        </MenuItem>
      </Menu>

      {/* Copy Success Snackbar */}
      <Snackbar
        open={copySnackbar}
        autoHideDuration={2000}
        onClose={() => setCopySnackbar(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert 
          onClose={() => setCopySnackbar(false)} 
          severity="success" 
          variant="filled"
          sx={{ 
            backgroundColor: "primary.main",
            color: "white"
          }}
        >
          {t("copiedToClipboard")}
        </Alert>
      </Snackbar>

      {/* Voice Error Snackbar */}
      <Snackbar
        open={!!voiceErrorSnackbar}
        autoHideDuration={4000}
        onClose={() => setVoiceErrorSnackbar(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="error" variant="filled" onClose={() => setVoiceErrorSnackbar(null)}>
          {voiceErrorSnackbar}
        </Alert>
      </Snackbar>

      {/* Prompts Drawer */}
      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        PaperProps={{
          sx: {
            backgroundColor: "background.paper",
            color: "text.primary",
          },
        }}
      >
        {drawerContent}
      </Drawer>
      </Box>
    </>
  );
};

export default ChatTab;