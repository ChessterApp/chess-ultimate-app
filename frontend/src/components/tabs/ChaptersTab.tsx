import { useState, useRef, useCallback, useEffect } from 'react';
import { Stack, Card, CardContent, Typography, Chip, Box, } from '@mui/material';
import OpenInFullIcon from '@mui/icons-material/OpenInFull';
import { useLocalStorage } from 'usehooks-ts';
import { DEFAULT_CHAPTER_DIMENIONS } from '@/lib/setting/helper';

interface ResizableChapterSelectorProps {
  chapters: { title: string; url: string; pgn: string }[];
  onChapterSelect: (pgn: string) => void;
}

const ResizableChapterSelector: React.FC<ResizableChapterSelectorProps> = ({
  chapters,
  onChapterSelect,
}) => {
  const [dimensions, setDimensions] = useLocalStorage<{width: number, height: number}>(
    "chapter_ui_dimensions",
    DEFAULT_CHAPTER_DIMENIONS
  )
  const [isResizing, setIsResizing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);

    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = dimensions.width;
    const startHeight = dimensions.height;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      moveEvent.preventDefault();

      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      const minWidth = 500;
      const maxWidth = 1200;
      const minHeight = 300;
      const maxHeight = 700;

      const newWidth = Math.max(minWidth, Math.min(maxWidth, startWidth + deltaX));
      const newHeight = Math.max(minHeight, Math.min(maxHeight, startHeight + deltaY));

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

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      setIsResizing(false);
    };
  }, []);

  return (
    <Card
      ref={containerRef}
      sx={(theme) => ({
        backgroundColor: "background.paper",
        borderRadius: 3,
        boxShadow: `0 4px 20px rgba(138, 43, 226, 0.1)`,
        width: dimensions.width,
        height: dimensions.height,
        position: 'relative',
        overflow: 'hidden',
        border: isResizing ? `2px solid ${theme.palette.primary.light}` : `1px solid ${theme.palette.secondary.main}40`,
        userSelect: isResizing ? 'none' : 'auto',
      })}
    >
      <CardContent sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, flexShrink: 0 }}>
          <Typography
            variant="h6"
            sx={{ color: "text.primary", fontWeight: 600 }}
          >
            Study Chapters
          </Typography>


        </Box>



        <Box
          sx={(theme) => ({
            flex: 1,
            overflow: 'auto',
            '&::-webkit-scrollbar': {
              width: '8px',
            },
            '&::-webkit-scrollbar-track': {
              background: theme.palette.background.paper,
              borderRadius: '4px',
            },
            '&::-webkit-scrollbar-thumb': {
              background: theme.palette.secondary.main,
              borderRadius: '4px',
              '&:hover': {
                background: theme.palette.primary.light,
              },
            },
          })}
        >
          <Stack spacing={1}>
            {chapters.map((ch, index) => (
              <Chip
                key={index}
                label={ch.title}
                onClick={() => !isResizing && onChapterSelect(ch.pgn)}
                sx={{
                  backgroundColor: "background.paper",
                  color: "text.primary",
                  '&:hover': {
                    backgroundColor: isResizing ? "background.paper" : "secondary.main",
                  },
                  borderRadius: 2,
                  justifyContent: 'flex-start',
                  width: '100%',
                  height: 'auto',
                  minHeight: '36px',
                  cursor: isResizing ? 'default' : 'pointer',
                  transition: 'background-color 0.2s ease',
                  '& .MuiChip-label': {
                    whiteSpace: 'normal',
                    wordBreak: 'break-word',
                    textAlign: 'left',
                    padding: '10px 16px',
                    lineHeight: 1.3,
                    fontSize: '0.9rem',
                  },
                }}
              />
            ))}
          </Stack>
        </Box>
      </CardContent>

      {/* Resize Handle - Bottom Left */}
      <Box
        onMouseDown={handleMouseDown}
        sx={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          width: '16px',
          height: '16px',
          cursor: 'nw-resize',
          backgroundColor: "primary.light",
          borderTopRightRadius: '3px',
          opacity: 0.7,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          '&:hover': {
            opacity: 1,
            backgroundColor: "primary.dark",
          },
        }}
      >
        <OpenInFullIcon
          sx={{
            fontSize: '10px',
            color: "text.primary",
            transform: 'rotate(180deg)'
          }}
        />
      </Box>


    </Card>
  );
};

export default ResizableChapterSelector;
