import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth } from '@clerk/nextjs';
import { apiFetch, ApiError } from '@/lib/api';

interface UseVoiceRecorderOptions {
  onTranscriptionComplete?: (text: string) => void;
  onError?: (error: string) => void;
}

interface UseVoiceRecorderReturn {
  isRecording: boolean;
  isTranscribing: boolean;
  isSupported: boolean;
  recordingDuration: number;
  error: string | null;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  cancelRecording: () => void;
}

export default function useVoiceRecorder(
  options: UseVoiceRecorderOptions = {}
): UseVoiceRecorderReturn {
  const { onTranscriptionComplete, onError } = options;
  const { getToken } = useAuth();

  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Check support on mount
  // Note: navigator.mediaDevices is only available on secure contexts (HTTPS/localhost).
  // On plain HTTP, we still show the button but handle the error gracefully at record time.
  useEffect(() => {
    const supported =
      typeof window !== 'undefined' &&
      typeof MediaRecorder !== 'undefined';
    setIsSupported(supported);
  }, []);

  const releaseStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const sendToTranscribe = useCallback(
    async (blob: Blob) => {
      setIsTranscribing(true);
      setError(null);

      try {
        const reader = new FileReader();
        const base64Promise = new Promise<string>((resolve, reject) => {
          reader.onloadend = () => {
            const result = reader.result as string;
            const base64 = result.split(',')[1];
            if (base64) {
              resolve(base64);
            } else {
              reject(new Error('Failed to convert audio to base64'));
            }
          };
          reader.onerror = () => reject(new Error('Failed to read audio blob'));
        });
        reader.readAsDataURL(blob);

        const base64 = await base64Promise;
        const token = await getToken();

        const data = await apiFetch<any>('/api/chat/transcribe', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ audio: base64 }),
        });

        if (data.success && data.text) {
          onTranscriptionComplete?.(data.text);
        } else {
          const errMsg = data.error || 'Transcription returned no text';
          setError(errMsg);
          onError?.(errMsg);
        }
      } catch (err: any) {
        const errMsg = err.message || 'Transcription failed';
        setError(errMsg);
        onError?.(errMsg);
      } finally {
        setIsTranscribing(false);
      }
    },
    [getToken, onTranscriptionComplete, onError]
  );

  const startRecording = useCallback(async () => {
    setError(null);
    setRecordingDuration(0);

    try {
      // Check if getUserMedia is available (requires HTTPS or localhost)
      if (!navigator.mediaDevices?.getUserMedia) {
        const errMsg = 'Microphone requires a secure connection (HTTPS). Please ask your admin to enable HTTPS.';
        setError(errMsg);
        onError?.(errMsg);
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      // Try different MIME types
      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = 'audio/webm';
      }
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = 'audio/mp4';
      }

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        // Handled by stopRecording
      };

      mediaRecorder.start(250); // Collect data every 250ms
      setIsRecording(true);

      // Start duration timer
      timerRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      const errMsg =
        err.name === 'NotAllowedError'
          ? 'Microphone access denied. Please allow microphone access.'
          : err.message || 'Failed to start recording';
      setError(errMsg);
      onError?.(errMsg);
      releaseStream();
    }
  }, [onError, releaseStream]);

  const stopRecording = useCallback(() => {
    clearTimer();

    const mediaRecorder = mediaRecorderRef.current;
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      // Set up handler before stopping
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: mediaRecorder.mimeType,
        });
        chunksRef.current = [];
        releaseStream();
        sendToTranscribe(blob);
      };
      mediaRecorder.stop();
    }

    setIsRecording(false);
    setRecordingDuration(0);
  }, [clearTimer, releaseStream, sendToTranscribe]);

  const cancelRecording = useCallback(() => {
    clearTimer();

    const mediaRecorder = mediaRecorderRef.current;
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.onstop = () => {
        // Discard chunks
        chunksRef.current = [];
      };
      mediaRecorder.stop();
    }

    chunksRef.current = [];
    releaseStream();
    setIsRecording(false);
    setRecordingDuration(0);
    setError(null);
  }, [clearTimer, releaseStream]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimer();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      releaseStream();
    };
  }, [clearTimer, releaseStream]);

  return {
    isRecording,
    isTranscribing,
    isSupported,
    recordingDuration,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
