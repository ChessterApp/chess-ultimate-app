// The page's iOS audio session (WebKit's navigator.audioSession, iOS 17+).
//
// The prize wheel and tug-of-war set it to 'playback' so their sounds ignore
// the silent switch. That type stays for the whole page, and while it holds,
// WebKit refuses the microphone: getUserMedia rejects with "InvalidStateError:
// AudioSession category is not compatible with audio capture" (chess-empire,
// 02.11). Anything that records asks for 'play-and-record' first, whoever set
// the session before.

type AudioSessionNavigator = Navigator & { audioSession?: { type: string } };

/** Let the page record (and keep playing). Call right before getUserMedia. */
export function allowAudioCapture(): void {
  try {
    const nav = navigator as AudioSessionNavigator;
    if (nav.audioSession && nav.audioSession.type !== 'play-and-record') {
      nav.audioSession.type = 'play-and-record';
    }
  } catch {
    /* not supported — nothing to change */
  }
}

/** getUserMedia with the session made fit for capture first. */
export function getMicrophone(constraints: MediaStreamConstraints): Promise<MediaStream> {
  allowAudioCapture();
  return navigator.mediaDevices.getUserMedia(constraints);
}
