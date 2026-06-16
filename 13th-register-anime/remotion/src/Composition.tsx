import {
  AbsoluteFill,
  Audio,
  Img,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { timeline, type TimelineEvent } from "./timeline";

const assetBase = "assets/13th-register";

const colors: Record<string, string> = {
  ナレーション: "#ece7cf",
  タクミ: "#62dafa",
  ミナ: "#f58ec6",
  第十三レジ: "#70ffe1",
  未来の会社員: "#bfd3f6",
  常連のおじいさん: "#ead28d",
  間: "#b8c1ca",
};

const backgroundFor = (event: TimelineEvent): string => {
  const number = Number(event.number || 0);
  if (event.cast === "第十三レジ") {
    return number >= 40 ? "anomaly.png" : "register_close.png";
  }
  if (event.cast === "未来の会社員") {
    return "anomaly.png";
  }
  if (number < 20) {
    return "store_wide.png";
  }
  if (number < 45) {
    return "aisle_night.png";
  }
  return "register_close.png";
};

const characterFor = (event: TimelineEvent): string | null => {
  if (event.cast === "タクミ") {
    return event.direction.includes("ツッコミ") || event.text.includes("はい？")
      ? "タクミ_tsukkomi.png"
      : "タクミ_surprised.png";
  }
  if (event.cast === "ミナ") {
    return event.direction.match(/淡々|無表情|冷静/)
      ? "ミナ_cold.png"
      : "ミナ_neutral.png";
  }
  if (event.cast === "未来の会社員") {
    return event.direction.match(/焦|困|不安/)
      ? "未来の会社員_anxious.png"
      : "未来の会社員_tired.png";
  }
  if (event.cast === "常連のおじいさん") {
    return "常連のおじいさん_neutral.png";
  }
  return null;
};

const activeEventAt = (ms: number): TimelineEvent => {
  return (
    timeline.events.find(
      (event) => ms >= event.startMs && ms < event.startMs + event.durationMs,
    ) ?? timeline.events[timeline.events.length - 1]
  );
};

const lineBreak = (text: string): string[] => {
  const normalized = text.replace(/。/g, "。\n").replace(/？/g, "？\n");
  const lines: string[] = [];
  for (const block of normalized.split("\n")) {
    const clean = block.trim();
    if (!clean) {
      continue;
    }
    for (let index = 0; index < clean.length; index += 30) {
      lines.push(clean.slice(index, index + 30));
    }
  }
  return lines.slice(0, 3);
};

const Background: React.FC<{ event: TimelineEvent; localProgress: number }> = ({
  event,
  localProgress,
}) => {
  const zoom = 1.035 + localProgress * 0.055;
  const pan = Math.sin(localProgress * Math.PI * 2) * 18;
  return (
    <>
      <Img
        src={staticFile(`${assetBase}/backgrounds/${backgroundFor(event)}`)}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${zoom}) translateX(${pan}px)`,
          filter: "saturate(1.08) contrast(1.06) brightness(0.9)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 42%, transparent 28%, rgba(2,6,13,0.36) 76%, rgba(0,0,0,0.64) 100%)",
        }}
      />
    </>
  );
};

const Character: React.FC<{ event: TimelineEvent; localProgress: number }> = ({
  event,
  localProgress,
}) => {
  const filename = characterFor(event);
  if (!filename) {
    return null;
  }
  const x =
    event.cast === "ミナ" || event.cast === "未来の会社員" ? "58%" : "5%";
  const y = 52 + Math.sin(localProgress * Math.PI * 2) * 5;
  const scale = event.cast === "未来の会社員" ? 1.03 : 1;
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        bottom: -18,
        width: 420,
        height: 640,
        transform: `translateY(${y - 52}px) scale(${scale})`,
        filter: "drop-shadow(0 24px 28px rgba(0,0,0,0.5))",
      }}
    >
      <Img
        src={staticFile(`${assetBase}/characters/${filename}`)}
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
      />
    </div>
  );
};

const RegisterSystem: React.FC<{
  event: TimelineEvent;
  localProgress: number;
}> = ({ event, localProgress }) => {
  if (event.cast !== "第十三レジ") {
    return null;
  }
  const pulse = interpolate(Math.sin(localProgress * Math.PI * 2), [-1, 1], [0, 1]);
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "repeating-linear-gradient(0deg, rgba(112,255,225,0.08) 0 1px, transparent 1px 18px), rgba(0,28,30,0.28)",
          mixBlendMode: "screen",
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 88,
          top: 112,
          width: 380,
          padding: 24,
          border: "2px solid rgba(112,255,225,0.82)",
          borderRadius: 14,
          background: "rgba(2,18,22,0.86)",
          boxShadow: "0 0 36px rgba(112,255,225,0.22)",
          color: "#dffff8",
          fontFamily: "Yu Gothic, Meiryo, sans-serif",
        }}
      >
        <div style={{ color: "#70ffe1", fontSize: 27, fontWeight: 800 }}>
          REG-13 SYSTEM
        </div>
        <div style={{ marginTop: 14, fontSize: 18, opacity: 0.9 }}>
          TEMPORAL RETURN MODE
        </div>
        <div style={{ marginTop: 8, fontSize: 18, opacity: 0.9 }}>
          LINE: {event.number}
        </div>
        <div
          style={{
            height: 8,
            background: "rgba(112,255,225,0.18)",
            marginTop: 22,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${42 + pulse * 48}%`,
              height: "100%",
              background: "#70ffe1",
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Subtitle: React.FC<{
  event: TimelineEvent;
  localProgress: number;
}> = ({ event, localProgress }) => {
  const accent = colors[event.cast] ?? "#e8edf4";
  const typed = event.text.slice(
    0,
    Math.max(1, Math.round(event.text.length * Math.min(1, localProgress * 1.7))),
  );
  return (
    <div
      style={{
        position: "absolute",
        left: 62,
        right: 62,
        bottom: 30,
        minHeight: 186,
        border: "2px solid rgba(235,240,230,0.92)",
        borderRadius: 18,
        background: "rgba(4,8,15,0.9)",
        boxShadow: "0 18px 38px rgba(0,0,0,0.42)",
        padding: "24px 36px",
        color: "#fbfbef",
        fontFamily: "Yu Gothic, Meiryo, sans-serif",
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          minWidth: 260,
          height: 50,
          border: `3px solid ${accent}`,
          borderRadius: 11,
          padding: "0 22px",
          marginBottom: 14,
          fontSize: 25,
          fontWeight: 800,
          letterSpacing: 0,
        }}
      >
        {event.cast || "間"}
      </div>
      <div style={{ fontSize: 35, lineHeight: 1.35, fontWeight: 800 }}>
        {lineBreak(typed).map((line) => (
          <div key={line}>{line}</div>
        ))}
      </div>
    </div>
  );
};

const TitleCard: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 18, 108, 135], [0, 1, 1, 0], {
    easing: Easing.bezier(0.33, 1, 0.68, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const x = interpolate(frame, [0, 28], [-42, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        opacity,
        background:
          "linear-gradient(90deg, rgba(0,0,0,0.58), rgba(0,0,0,0.12), transparent)",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 84 + x,
          top: 72,
          color: "#f8f6e9",
          fontFamily: "Yu Gothic, Meiryo, sans-serif",
        }}
      >
        <div style={{ fontSize: 76, fontWeight: 900, letterSpacing: 0 }}>
          第十三レジ
        </div>
        <div
          style={{
            marginTop: 8,
            color: "#70ffe1",
            fontSize: 24,
            fontWeight: 800,
          }}
        >
          1 minute anime pilot
        </div>
        <div
          style={{
            width: 390,
            height: 4,
            marginTop: 16,
            background: "#70ffe1",
            boxShadow: "0 0 18px #70ffe1",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

export const ThirteenthRegisterPv: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const event = activeEventAt(ms);
  const localProgress = Math.min(
    1,
    Math.max(0, (ms - event.startMs) / Math.max(event.durationMs, 1)),
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#05070c" }}>
      <Audio src={staticFile(`${assetBase}/audio/voice_drama.wav`)} />
      <Background event={event} localProgress={localProgress} />
      <Character event={event} localProgress={localProgress} />
      <RegisterSystem event={event} localProgress={localProgress} />
      <Subtitle event={event} localProgress={localProgress} />
      <TitleCard />
    </AbsoluteFill>
  );
};
