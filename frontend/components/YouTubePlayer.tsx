"use client";

import {
  useEffect,
  useRef,
  useImperativeHandle,
  forwardRef,
  useState,
} from "react";

interface YTPlayer {
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  pauseVideo(): void;
  getPlayerState(): number;
  getCurrentTime(): number;
  destroy(): void;
}

declare global {
  interface Window {
    YT?: {
      Player: new (id: string, config: Record<string, unknown>) => YTPlayer;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

interface YouTubePlayerProps {
  videoId: string;
  onReady?: (player: YTPlayer) => void;
}

export interface YouTubePlayerHandle {
  seekTo: (seconds: number) => void;
  getCurrentTime: () => number;
  getPlayerState: () => number;
}

const YouTubePlayer = forwardRef<YouTubePlayerHandle, YouTubePlayerProps>(
  function YouTubePlayer({ videoId, onReady }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const playerRef = useRef<YTPlayer | null>(null);
    const [ready, setReady] = useState(false);
    const [title, setTitle] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    // ── Imperative handle ──────────────────────────────────────────────
    useImperativeHandle(ref, () => ({
      seekTo: (seconds: number) => {
        if (playerRef.current) {
          playerRef.current.seekTo(seconds, true);
          playerRef.current.playVideo();
        }
      },
      getCurrentTime: () => playerRef.current?.getCurrentTime() ?? 0,
      getPlayerState: () => playerRef.current?.getPlayerState() ?? -1,
    }));

    // ── Fetch video title ──────────────────────────────────────────────
    useEffect(() => {
      if (!videoId) return;
      setTitle(null);
      setLoading(true);
      fetch(`https://noembed.com/embed?url=https://www.youtube.com/watch?v=${videoId}`)
        .then((r) => r.json())
        .then((data) => { if (data.title) setTitle(data.title); })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, [videoId]);

    // ── YouTube IFrame API init ────────────────────────────────────────
    useEffect(() => {
      if (!videoId || !containerRef.current) return;

      const containerId = `yt-player-${videoId}`;

      const initPlayer = () => {
        if (!window.YT?.Player) return;
        if (playerRef.current) return;

        playerRef.current = new window.YT.Player(containerId, {
          videoId,
          width: "100%",
          height: "100%",
          playerVars: {
            rel: 0,
            modestbranding: 1,
            controls: 1,
            fs: 0,
            cc_load_policy: 0,
          },
          events: {
            onReady: () => {
              setReady(true);
              onReady?.(playerRef.current!);
            },
          },
        });
      };

      if (!window.YT) {
        const tag = document.createElement("script");
        tag.src = "https://www.youtube.com/iframe_api";
        document.head.appendChild(tag);
      }

      if (window.YT?.Player) {
        initPlayer();
      } else {
        const interval = setInterval(() => {
          if (window.YT?.Player) {
            clearInterval(interval);
            initPlayer();
          }
        }, 100);
        return () => {
          clearInterval(interval);
          playerRef.current?.destroy();
          playerRef.current = null;
        };
      }

      return () => {
        playerRef.current?.destroy();
        playerRef.current = null;
      };
    }, [videoId, onReady]);

    return (
      <div
        style={{
          display: "flex",
          alignItems: "stretch",
          gap: 10,
          padding: "8px 14px",
          background: "var(--gray-50)",
          border: "1px solid var(--gray-200)",
          borderRadius: 10,
          marginBottom: 16,
        }}
      >
        {/* ── Player (always in DOM, small) ─────────────────────────── */}
        <div
          ref={containerRef}
          id={`yt-player-${videoId}`}
          style={{
            width: 280,
            height: 158,
            borderRadius: 6,
            overflow: "hidden",
            flexShrink: 0,
            background: "#000",
            position: "relative",
          }}
        >
          {!ready && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "#000",
                color: "var(--gray-400)",
                fontSize: 11,
              }}
            >
              {loading ? (
                <div style={{ textAlign: "center" }}>
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      border: "2px solid var(--gray-400)",
                      borderTopColor: "transparent",
                      borderRadius: "50%",
                      animation: "spin 0.8s linear infinite",
                      margin: "0 auto 4px",
                    }}
                  />
                  Loading…
                </div>
              ) : (
                <span style={{ fontSize: 10, fontFamily: "JetBrains Mono" }}>{videoId}</span>
              )}
            </div>
          )}
        </div>

        {/* ── Title + meta ──────────────────────────────────────────── */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 4,
            minWidth: 0,
            flex: 1,
          }}
        >
          <p
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: "var(--gray-700)",
              margin: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {title || videoId}
          </p>
          <p
            style={{
              fontSize: 10,
              color: "var(--gray-400)",
              fontFamily: "JetBrains Mono, monospace",
              margin: 0,
            }}
          >
            {videoId} · Click timestamps to play
          </p>
        </div>

        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }
);

export default YouTubePlayer;
