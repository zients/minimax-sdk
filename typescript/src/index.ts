/**
 * MiniMax SDK for TypeScript.
 *
 * Usage:
 *   import MiniMax from "@zients/minimax-sdk";
 *   const client = new MiniMax(); // reads MINIMAX_API_KEY from env
 *   const result = await client.text.create({ ... });
 */

// Client
export { MiniMax, type ClientOptions } from "./client.js";
export { default } from "./client.js";

// Errors
export {
  MiniMaxError,
  AuthError,
  RateLimitError,
  InsufficientBalanceError,
  ContentSafetyError,
  InputSafetyError,
  OutputSafetyError,
  InvalidParameterError,
  APITimeoutError,
  PollTimeoutError,
  VoiceError,
  VoiceCloneError,
  VoiceDuplicateError,
  VoicePermissionError,
  ServerError,
} from "./error.js";

// Audio
export { AudioResponse, type AudioResponseData } from "./audio.js";

// Text types
export type {
  TextBlock,
  ToolUseBlock,
  ThinkingBlock,
  ContentBlock,
  Usage,
  Message,
  TextDelta,
  InputJsonDelta,
  ThinkingDelta,
  SignatureDelta,
  Delta,
  MessageDelta,
  MessageStartEvent,
  ContentBlockStartEvent,
  ContentBlockDeltaEvent,
  ContentBlockStopEvent,
  MessageDeltaEvent,
  MessageStopEvent,
  StreamEvent,
  TextCreateParams,
} from "./resources/text.js";

// Speech types
export { SpeechConnection } from "./resources/speech.js";

export type {
  VoiceSetting,
  AudioSetting,
  VoiceModify,
  PronunciationDict,
  TimbreWeight,
  TTSParams,
  AsyncCreateParams,
  AsyncGenerateParams,
  TaskResult,
} from "./resources/speech.js";

// Voice types
export type {
  ClonePrompt,
  VoiceCloneResult,
  VoiceDesignResult,
  VoiceInfo,
  VoiceList,
} from "./resources/voice.js";

// Video types
export type { SubjectReference, VideoCreateParams, VideoResult } from "./resources/video.js";

// Image types
export type { ImageSubjectReference, ImageGenerateParams, ImageResult } from "./resources/image.js";

// Music types
export type {
  MusicAudioSetting,
  MusicGenerateParams,
  MusicGenerateStreamParams,
  LyricsGenerateParams,
  LyricsResult,
} from "./resources/music.js";

// Files types
export type { FileInfo } from "./resources/files.js";
