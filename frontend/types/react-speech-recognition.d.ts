declare module "react-speech-recognition" {
  export interface ListeningOptions {
    continuous?: boolean;
    language?: string;
    interimResults?: boolean;
    maxAlternatives?: number;
    fuzzyMatching?: boolean;
  }

  export interface SpeechRecognitionHook {
    transcript: string;
    listening: boolean;
    resetTranscript: () => void;
    browserSupportsSpeechRecognition: boolean;
    interimTranscript: string;
    finalTranscript: string;
    isMicrophoneAvailable: boolean;
  }

  export function useSpeechRecognition(options?: ListeningOptions): SpeechRecognitionHook;

  const SpeechRecognition: {
    startListening: (options?: ListeningOptions) => Promise<void>;
    stopListening: () => void;
    abortListening: () => void;
    getRecognition: () => any;
  };
  export default SpeechRecognition;
}
