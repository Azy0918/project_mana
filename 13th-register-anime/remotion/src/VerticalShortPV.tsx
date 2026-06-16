import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const assetBase = "assets/13th-register";

type Shot = {
  title: string;
  background: string;
  character?: string;
  prop?: string;
  accent: string;
  mood: "mystery" | "active" | "calm" | "tired" | "glitch";
};

const shots: Shot[] = [
  {
    title: "MIDNIGHT",
    background: "exterior_night.png",
    accent: "112,255,225",
    mood: "mystery",
  },
  {
    title: "TAKUMI",
    background: "aisle_night.png",
    character: "タクミ_tsukkomi.png",
    prop: "第十三レジ.png",
    accent: "255,216,150",
    mood: "active",
  },
  {
    title: "MINA",
    background: "store_wide.png",
    character: "ミナ_cold.png",
    prop: "第十三レジ.png",
    accent: "122,235,255",
    mood: "calm",
  },
  {
    title: "FUTURE",
    background: "aisle_night.png",
    character: "未来の会社員_tired.png",
    accent: "150,190,255",
    mood: "tired",
  },
  {
    title: "REGISTER 13",
    background: "anomaly.png",
    prop: "第十三レジ.png",
    accent: "112,255,225",
    mood: "glitch",
  },
];

const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

const Background: React.FC<{ shot: Shot; progress: number; index: number }> = ({
  shot,
  progress,
  index,
}) => {
  const driftX = interpolate(progress, [0, 1], [index % 2 === 0 ? -42 : 42, index % 2 === 0 ? 42 : -42]);
  const driftY = interpolate(progress, [0, 1], [-22, 24]);
  const zoom = 1.24 + progress * 0.08;
  return (
    <>
      <Img
        src={staticFile(`${assetBase}/backgrounds/${shot.background}`)}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${zoom}) translate(${driftX}px, ${driftY}px)`,
          filter:
            shot.mood === "glitch"
              ? "saturate(1.45) contrast(1.24) brightness(0.72)"
              : "saturate(1.18) contrast(1.1) brightness(0.78)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(to bottom, rgba(3,6,14,0.34), transparent 22%, rgba(3,6,14,0.18) 58%, rgba(3,6,14,0.82))",
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 42%, rgba(${shot.accent},0.16), transparent 34%)`,
          mixBlendMode: "screen",
        }}
      />
    </>
  );
};

const Character: React.FC<{ shot: Shot; progress: number; frame: number }> = ({
  shot,
  progress,
  frame,
}) => {
  if (!shot.character) {
    return null;
  }
  const active = shot.mood === "active";
  const calm = shot.mood === "calm";
  const tired = shot.mood === "tired";
  const enter = interpolate(progress, [0, 0.2, 1], [80, 0, -10], clamp);
  const bob = Math.sin(frame * (tired ? 0.045 : calm ? 0.032 : 0.062)) * (tired ? 8 : calm ? 3 : 6);
  const tilt = Math.sin(frame * (calm ? 0.025 : 0.043)) * (active ? 1.2 : calm ? 0.35 : 0.75);
  const blink = progress > 0.44 && progress < 0.50;
  const talk = Math.sin(frame * 0.7) > 0.18;
  const width = active ? 1080 : tired ? 980 : 1000;
  const left = active ? -130 : calm ? 20 : 54;
  const bottom = active ? 235 : tired ? 185 : 220;

  return (
    <div
      style={{
        position: "absolute",
        left,
        bottom,
        width,
        height: 1420,
        transform: `translateY(${enter + bob}px) rotate(${tilt}deg) scale(${1 + progress * 0.035})`,
        transformOrigin: "50% 82%",
        filter: "drop-shadow(0 42px 42px rgba(0,0,0,0.66))",
        WebkitMaskImage: "linear-gradient(to bottom, #000 0%, #000 78%, transparent 98%)",
        maskImage: "linear-gradient(to bottom, #000 0%, #000 78%, transparent 98%)",
      }}
    >
      <Img
        src={staticFile(`${assetBase}/characters/${shot.character}`)}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "contain",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "27%",
          top: "12%",
          width: "50%",
          height: "30%",
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(${shot.accent},0.23), transparent 62%)`,
          opacity: 0.35 + Math.abs(Math.sin(frame * 0.06)) * 0.18,
          mixBlendMode: "screen",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: tired ? "46%" : calm ? "48%" : "47%",
          top: tired ? "34%" : "35%",
          width: active ? "10%" : "8%",
          height: active ? "2.8%" : "2.1%",
          borderRadius: 999,
          background: talk ? "rgba(28,12,16,0.65)" : "rgba(28,12,16,0.28)",
          transform: `scaleY(${talk ? 1.45 : 0.35})`,
          opacity: active ? 0.72 : 0.48,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "34%",
          top: "23%",
          width: "30%",
          height: "2.2%",
          borderTop: blink ? "4px solid rgba(20,16,18,0.76)" : "0 solid transparent",
          borderRadius: "50%",
          opacity: blink ? 1 : 0,
        }}
      />
    </div>
  );
};

const Register: React.FC<{ shot: Shot; progress: number; frame: number }> = ({
  shot,
  progress,
  frame,
}) => {
  if (!shot.prop) {
    return null;
  }
  const main = shot.mood === "glitch";
  const pulse = Math.abs(Math.sin(frame * 0.16));
  const x = main ? 235 : 600;
  const y = main ? 360 : 470;
  const size = main ? 620 : 440;
  const glitch = main ? Math.sin(frame * 1.6) * 8 : 0;
  return (
    <div
      style={{
        position: "absolute",
        left: x + glitch,
        top: y,
        width: size,
        height: size * 1.3,
        opacity: main ? 1 : 0.62,
        transform: `scale(${1 + progress * 0.035})`,
        filter: `drop-shadow(0 0 ${main ? 52 : 28}px rgba(${shot.accent},${0.34 + pulse * 0.28}))`,
      }}
    >
      <Img
        src={staticFile(`${assetBase}/props/${shot.prop}`)}
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
      />
      <div
        style={{
          position: "absolute",
          left: "27%",
          top: "22%",
          width: "46%",
          height: "25%",
          border: `3px solid rgba(${shot.accent},${0.28 + pulse * 0.34})`,
          boxShadow: `inset 0 0 24px rgba(${shot.accent},0.32), 0 0 34px rgba(${shot.accent},0.42)`,
        }}
      />
    </div>
  );
};

const VerticalText: React.FC<{ shot: Shot; progress: number }> = ({ shot, progress }) => {
  const opacity = interpolate(progress, [0, 0.16, 0.78, 1], [0, 1, 1, 0], clamp);
  const y = interpolate(progress, [0, 0.18, 1], [24, 0, -10], clamp);
  return (
    <div
      style={{
        position: "absolute",
        left: 58,
        top: 84 + y,
        opacity,
        color: "#f8f7ee",
        fontFamily: "Yu Gothic, Meiryo, sans-serif",
        letterSpacing: 0,
      }}
    >
      <div style={{ fontSize: 42, fontWeight: 800 }}>{shot.title}</div>
      <div
        style={{
          marginTop: 16,
          width: 190,
          height: 5,
          background: `rgb(${shot.accent})`,
          boxShadow: `0 0 18px rgba(${shot.accent},0.9)`,
        }}
      />
    </div>
  );
};

const GlobalEffects: React.FC<{ shot: Shot; progress: number; frame: number }> = ({
  shot,
  progress,
  frame,
}) => {
  const flash = interpolate(progress, [0, 0.08], [0.22, 0], clamp);
  const scan = shot.mood === "glitch";
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div style={{ position: "absolute", inset: 0, background: `rgba(255,255,255,${flash})` }} />
      {scan ? (
        <>
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "repeating-linear-gradient(0deg, rgba(112,255,225,0.13) 0 1px, transparent 1px 15px)",
              mixBlendMode: "screen",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: ((frame * 8) % 1300) - 140,
              top: 180,
              width: 160,
              height: 1280,
              transform: "skewX(-12deg)",
              background: "linear-gradient(90deg, transparent, rgba(112,255,225,0.24), transparent)",
              mixBlendMode: "screen",
            }}
          />
        </>
      ) : null}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 50% 48%, transparent 30%, rgba(0,0,0,0.42) 76%, rgba(0,0,0,0.76) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

export const VerticalShortPV: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const framesPerShot = fps * 5;
  const shotIndex = Math.min(shots.length - 1, Math.floor(frame / framesPerShot));
  const shot = shots[shotIndex];
  const local = frame - shotIndex * framesPerShot;
  const progress = local / framesPerShot;
  const shake = shot.mood === "glitch" ? Math.sin(frame * 1.7) * 5 : 0;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#05070c",
        overflow: "hidden",
        transform: `translate(${shake}px, ${-shake * 0.35}px)`,
      }}
    >
      <Audio src={staticFile(`${assetBase}/audio/trailer_voice.wav`)} volume={0.88} />
      <Background shot={shot} progress={progress} index={shotIndex} />
      <Register shot={shot} progress={progress} frame={frame} />
      <Character shot={shot} progress={progress} frame={frame} />
      <GlobalEffects shot={shot} progress={progress} frame={frame} />
      <VerticalText shot={shot} progress={progress} />
    </AbsoluteFill>
  );
};
