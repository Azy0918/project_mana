import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  random,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { timeline, type TimelineBundle, type TimelineEvent } from "./timeline";
import { trailerTimeline } from "./trailerTimeline";

const assetBase = "assets/13th-register";

const activeEventAt = (events: TimelineEvent[], ms: number): TimelineEvent => {
  return (
    events.find(
      (event) => ms >= event.startMs && ms < event.startMs + event.durationMs,
    ) ?? events[events.length - 1]
  );
};

const bgFor = (event: TimelineEvent, shot: number): string => {
  const number = Number(event.number || 0);
  const set = ["store_wide.png", "aisle_night.png", "register_close.png"];
  if (event.cast === "第十三レジ") {
    return shot % 2 === 0 ? "anomaly.png" : "register_close.png";
  }
  if (number >= 45) {
    return shot % 3 === 0 ? "register_close.png" : "aisle_night.png";
  }
  if (event.cast === "ナレーション") {
    return set[shot % set.length];
  }
  if (event.cast === "ミナ") {
    return shot % 2 === 0 ? "store_wide.png" : "aisle_night.png";
  }
  return shot % 2 === 0 ? "aisle_night.png" : "store_wide.png";
};

const charFiles = (event: TimelineEvent): string[] => {
  if (event.cast === "タクミ") {
    return ["タクミ_tsukkomi.png", "タクミ_surprised.png"];
  }
  if (event.cast === "ミナ") {
    return ["ミナ_neutral.png", "ミナ_cold.png"];
  }
  if (event.cast === "未来の会社員") {
    return ["未来の会社員_tired.png", "未来の会社員_anxious.png"];
  }
  if (event.cast === "常連のおじいさん") {
    return ["常連のおじいさん_neutral.png"];
  }
  return [];
};

type RigProfile = {
  mouth: { left: number; top: number; width: number; height: number };
  blink: { left: number; top: number; width: number; height: number };
  mood: "active" | "calm" | "tired" | "gentle";
  floorFade?: number;
};

const rigProfiles: Record<string, RigProfile> = {
  タクミ: {
    mouth: { left: 0.46, top: 0.35, width: 0.10, height: 0.025 },
    blink: { left: 0.34, top: 0.235, width: 0.30, height: 0.022 },
    mood: "active",
    floorFade: 78,
  },
  ミナ: {
    mouth: { left: 0.48, top: 0.35, width: 0.08, height: 0.018 },
    blink: { left: 0.36, top: 0.235, width: 0.28, height: 0.018 },
    mood: "calm",
    floorFade: 76,
  },
  未来の会社員: {
    mouth: { left: 0.47, top: 0.34, width: 0.10, height: 0.023 },
    blink: { left: 0.34, top: 0.225, width: 0.28, height: 0.020 },
    mood: "tired",
    floorFade: 80,
  },
  常連のおじいさん: {
    mouth: { left: 0.47, top: 0.36, width: 0.09, height: 0.020 },
    blink: { left: 0.35, top: 0.245, width: 0.28, height: 0.020 },
    mood: "gentle",
    floorFade: 80,
  },
};

const castAccent = (cast: string): string => {
  if (cast === "タクミ") {
    return "255,215,150";
  }
  if (cast === "ミナ") {
    return "122,235,255";
  }
  if (cast === "未来の会社員") {
    return "150,190,255";
  }
  if (cast === "常連のおじいさん") {
    return "255,235,184";
  }
  return "112,255,225";
};

const shotLengthFrames = (event: TimelineEvent): number => {
  if (event.cast === "ナレーション") {
    return 24;
  }
  if (event.cast === "第十三レジ") {
    return 14;
  }
  return 18;
};

const CharacterSprite: React.FC<{
  file: string;
  headTilt: number;
  headLift: number;
}> = ({ file, headTilt, headLift }) => {
  const charPath = `${assetBase}/characters/${file}`;
  return (
    <Img
      src={staticFile(charPath)}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        objectFit: "contain",
        transform: `translate(${headTilt * 0.18}px, ${headLift * 0.12}px)`,
      }}
    />
  );
};

const Background: React.FC<{
  event: TimelineEvent;
  shot: number;
  shotProgress: number;
}> = ({ event, shot, shotProgress }) => {
  const jitter = event.cast === "第十三レジ" ? Math.sin(shotProgress * Math.PI * 18) * 9 : 0;
  const zoom = 1.08 + shotProgress * 0.08 + (shot % 4) * 0.012;
  const x = interpolate((shot % 5) / 4, [0, 1], [-42, 42]) + jitter;
  const y = interpolate(((shot + 2) % 5) / 4, [0, 1], [-22, 22]);
  return (
    <>
      <Img
        src={staticFile(`${assetBase}/backgrounds/${bgFor(event, shot)}`)}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${zoom}) translate(${x}px, ${y}px)`,
          filter:
            event.cast === "第十三レジ"
              ? "saturate(1.35) contrast(1.2) brightness(0.72) hue-rotate(8deg)"
              : "saturate(1.16) contrast(1.08) brightness(0.82)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 40%, transparent 24%, rgba(0,0,0,0.28) 68%, rgba(0,0,0,0.68) 100%)",
        }}
      />
    </>
  );
};

const CharacterLayer: React.FC<{
  event: TimelineEvent;
  shot: number;
  shotProgress: number;
}> = ({ event, shot, shotProgress }) => {
  const files = charFiles(event);
  if (files.length === 0) {
    return null;
  }

  const file = files[shot % files.length];
  const isRight = event.cast === "ミナ" || event.cast === "未来の会社員";
  const close = shot % 3 === 0;
  const width = close ? 620 : 460;
  const left = isRight ? (close ? 640 : 720) : close ? 20 : 70;
  const bottom = close ? -116 : -42;
  const profile = rigProfiles[event.cast];
  const enter = interpolate(shotProgress, [0, 0.22, 1], [isRight ? 70 : -70, 0, 6], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const breath = profile?.mood === "tired" ? 9 : profile?.mood === "calm" ? 3 : 6;
  const bob = Math.sin(shotProgress * Math.PI * 2) * breath;
  const headTilt =
    profile?.mood === "calm"
      ? Math.sin(shotProgress * Math.PI * 2 + 0.4) * 0.45
      : Math.sin(shotProgress * Math.PI * 2 + 0.2) * 1.1;
  const headLift = Math.sin(shotProgress * Math.PI * 2 + 0.8) * (profile?.mood === "calm" ? 1.2 : 2.2);
  const talk = event.cast !== "ナレーション" && event.text.length > 0;
  const mouthOpen = talk && Math.sin(shotProgress * Math.PI * 18 + shot * 0.6) > 0.15;
  const blink = shotProgress > 0.46 && shotProgress < 0.54;
  const scale = 1 + shotProgress * 0.035;
  const floorFade = profile?.floorFade ?? 80;
  const accent = castAccent(event.cast);
  const talkPulse = talk ? 0.36 + Math.abs(Math.sin(shotProgress * Math.PI * 10 + shot)) * 0.28 : 0.16;
  const faceSweep = interpolate(Math.sin(shotProgress * Math.PI * 2 + shot), [-1, 1], [-16, 16]);

  return (
    <div
      style={{
        position: "absolute",
        left,
        bottom,
        width,
        height: 760,
        transform: `translateX(${enter}px) translateY(${bob}px) scale(${scale})`,
        transformOrigin: isRight ? "bottom right" : "bottom left",
        filter: "drop-shadow(0 28px 30px rgba(0,0,0,0.56))",
        WebkitMaskImage: `linear-gradient(to bottom, #000 0%, #000 ${floorFade}%, rgba(0,0,0,0) 99%)`,
        maskImage: `linear-gradient(to bottom, #000 0%, #000 ${floorFade}%, rgba(0,0,0,0) 99%)`,
      }}
    >
      <CharacterSprite file={file} headTilt={headTilt} headLift={headLift} />
      {profile ? (
        <>
          <div
            style={{
              position: "absolute",
              left: "20%",
              top: "10%",
              width: "62%",
              height: "34%",
              borderRadius: "50%",
              background: `radial-gradient(circle at ${isRight ? 62 : 42}% 46%, rgba(${accent},0.20), transparent 58%)`,
              opacity: talkPulse,
              mixBlendMode: "screen",
              transform: `translateX(${faceSweep}px)`,
              filter: "blur(2px)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: isRight ? "58%" : "8%",
              top: "22%",
              width: "26%",
              height: "56%",
              background: `linear-gradient(${isRight ? 270 : 90}deg, rgba(${accent},0.22), transparent 78%)`,
              opacity: talk ? 0.32 : 0.16,
              mixBlendMode: "screen",
              transform: `skewY(${Math.sin(shotProgress * Math.PI * 2) * 2}deg)`,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: `${profile.mouth.left * 100}%`,
              top: `${profile.mouth.top * 100}%`,
              width: `${profile.mouth.width * 100}%`,
              height: `${profile.mouth.height * 100}%`,
              borderRadius: "999px",
              background: mouthOpen ? "rgba(30,16,18,0.62)" : "rgba(36,18,18,0.18)",
              transform: `scaleY(${mouthOpen ? 1.35 : 0.35})`,
              boxShadow: mouthOpen ? "0 0 4px rgba(255,210,210,0.12)" : "none",
              opacity: talk ? 0.78 : 0.18,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: `${profile.blink.left * 100}%`,
              top: `${profile.blink.top * 100}%`,
              width: `${profile.blink.width * 100}%`,
              height: `${profile.blink.height * 100}%`,
              borderTop: blink ? "3px solid rgba(18,16,18,0.72)" : "0 solid transparent",
              borderRadius: "50%",
              opacity: blink ? 1 : 0,
            }}
          />
        </>
      ) : null}
    </div>
  );
};

const GuestMontage: React.FC<{
  event: TimelineEvent;
  shot: number;
  shotProgress: number;
}> = ({ event, shot, shotProgress }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const show =
    event.cast === "ナレーション" ||
    Number(event.number || 0) >= 19 ||
    (frame > fps * 52 && frame < fps * 59);
  if (!show) {
    return null;
  }

  const fade = interpolate(shotProgress, [0, 0.18, 0.82, 1], [0, 0.55, 0.55, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const futureX = interpolate(Math.sin(frame * 0.017), [-1, 1], [760, 790]);
  const elderX = interpolate(Math.sin(frame * 0.013 + 1.1), [-1, 1], [52, 76]);
  const elderVisible = event.cast === "ナレーション" || shot % 4 === 1 || frame > fps * 52;
  const futureVisible = Number(event.number || 0) >= 19 || shot % 4 === 2 || frame > fps * 45;

  return (
    <>
      {elderVisible ? (
        <div
          style={{
            position: "absolute",
            left: elderX,
            bottom: -80 + Math.sin(frame * 0.035) * 4,
            width: 340,
            height: 620,
            opacity: fade * 0.86,
            transform: `rotate(${Math.sin(frame * 0.02) * 0.6}deg)`,
            filter: "drop-shadow(0 18px 24px rgba(0,0,0,0.48)) saturate(0.96)",
            WebkitMaskImage: "linear-gradient(to bottom, #000 0%, #000 80%, transparent 99%)",
            maskImage: "linear-gradient(to bottom, #000 0%, #000 80%, transparent 99%)",
          }}
        >
          <Img
            src={staticFile(`${assetBase}/characters/常連のおじいさん_neutral.png`)}
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
        </div>
      ) : null}
      {futureVisible ? (
        <div
          style={{
            position: "absolute",
            left: futureX,
            bottom: -94 + Math.sin(frame * 0.029 + 0.4) * 8,
            width: 410,
            height: 660,
            opacity: fade * 0.9,
            transform: `rotate(${Math.sin(frame * 0.021 + 0.5) * -0.8}deg)`,
            filter: "drop-shadow(0 22px 28px rgba(0,0,0,0.52)) saturate(0.98)",
            WebkitMaskImage: "linear-gradient(to bottom, #000 0%, #000 80%, transparent 99%)",
            maskImage: "linear-gradient(to bottom, #000 0%, #000 80%, transparent 99%)",
          }}
        >
          <Img
            src={staticFile(`${assetBase}/characters/未来の会社員_tired.png`)}
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
        </div>
      ) : null}
    </>
  );
};

const AllCastFinale: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame - fps * 52;
  if (local < 0) {
    return null;
  }
  const opacity = interpolate(local, [0, 20, 210, 240], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const cast = [
    { cast: "常連のおじいさん", file: "常連のおじいさん_neutral.png", left: 70, width: 300, delay: 0, y: -72 },
    { cast: "タクミ", file: "タクミ_tsukkomi.png", left: 250, width: 390, delay: 8, y: -62 },
    { cast: "ミナ", file: "ミナ_cold.png", left: 600, width: 350, delay: 16, y: -56 },
    { cast: "未来の会社員", file: "未来の会社員_tired.png", left: 850, width: 360, delay: 24, y: -74 },
  ];
  return (
    <AbsoluteFill style={{ opacity, pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(0deg, rgba(0,0,0,0.58), transparent 34%, rgba(0,0,0,0.18))",
        }}
      />
      {cast.map((item, index) => {
        const t = Math.max(0, local - item.delay);
        const enter = interpolate(t, [0, 22], [44, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const bob = Math.sin((frame + index * 11) * 0.055) * (index === 2 ? 2.5 : 6);
        const rotate = Math.sin((frame + index * 9) * 0.028) * (index === 2 ? 0.25 : 0.7);
        const headTilt = Math.sin((frame + index * 13) * 0.045) * (index === 2 ? 0.35 : 0.85);
        const headLift = Math.sin((frame + index * 17) * 0.052) * (index === 2 ? 1 : 2);
        const accent = castAccent(item.cast);
        const glow = 0.16 + Math.abs(Math.sin((frame + index * 18) * 0.055)) * 0.18;
        return (
          <div
            key={item.file}
            style={{
              position: "absolute",
              left: item.left,
              bottom: item.y,
              width: item.width,
              height: 620,
              transform: `translateY(${enter + bob}px) rotate(${rotate}deg)`,
              transformOrigin: "50% 88%",
              filter: "drop-shadow(0 24px 28px rgba(0,0,0,0.62))",
              WebkitMaskImage: "linear-gradient(to bottom, #000 0%, #000 80%, transparent 99%)",
              maskImage: "linear-gradient(to bottom, #000 0%, #000 80%, transparent 99%)",
            }}
          >
            <CharacterSprite file={item.file} headTilt={headTilt} headLift={headLift} />
            <div
              style={{
                position: "absolute",
                left: "20%",
                top: "12%",
                width: "62%",
                height: "34%",
                borderRadius: "50%",
                background: `radial-gradient(circle, rgba(${accent},0.22), transparent 64%)`,
                opacity: glow,
                mixBlendMode: "screen",
                transform: `translateY(${Math.sin((frame + index * 7) * 0.04) * 5}px)`,
              }}
            />
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const ForegroundShade: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        background:
          "linear-gradient(to bottom, transparent 0%, transparent 63%, rgba(5,7,12,0.30) 76%, rgba(5,7,12,0.76) 100%)",
      }}
    />
  );
};

const RegisterLayer: React.FC<{
  event: TimelineEvent;
  shot: number;
  shotProgress: number;
}> = ({ event, shot, shotProgress }) => {
  const show = event.cast === "第十三レジ" || Number(event.number || 0) >= 19;
  if (!show) {
    return null;
  }
  const opacity = event.cast === "第十三レジ" ? 1 : 0.48;
  const facePulse = Math.sin(shotProgress * Math.PI * 6 + shot) * 0.018;
  const scale = event.cast === "第十三レジ" ? 0.62 + shotProgress * 0.05 + facePulse : 0.38;
  const x = event.cast === "第十三レジ" ? 430 + Math.sin(shot * 1.3) * 40 : 858;
  const y = event.cast === "第十三レジ" ? 36 : 152;
  const glitch = event.cast === "第十三レジ" ? Math.sin(shotProgress * Math.PI * 22) * 4 : 0;
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: 430,
        height: 600,
        opacity,
        transform: `translateX(${glitch}px) scale(${scale})`,
        transformOrigin: "center top",
        filter: "drop-shadow(0 0 36px rgba(112,255,225,0.55))",
      }}
    >
      <Img
        src={staticFile(`${assetBase}/props/第十三レジ.png`)}
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
      />
      <div
        style={{
          position: "absolute",
          left: "32%",
          top: "31%",
          width: "34%",
          height: "3%",
          background: "rgba(112,255,225,0.72)",
          borderRadius: 999,
          transform: `scaleY(${0.5 + Math.abs(Math.sin(shotProgress * Math.PI * 16)) * 1.9})`,
          boxShadow: "0 0 16px rgba(112,255,225,0.75)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "26%",
          top: "22%",
          width: "46%",
          height: "24%",
          border: "2px solid rgba(112,255,225,0.32)",
          boxShadow: "inset 0 0 18px rgba(112,255,225,0.42), 0 0 28px rgba(112,255,225,0.34)",
          transform: `scale(${1 + Math.abs(Math.sin(shotProgress * Math.PI * 10)) * 0.025})`,
        }}
      />
    </div>
  );
};

const MusicPulse: React.FC = () => {
  const frame = useCurrentFrame();
  const beat = Math.sin(frame * 0.16);
  const opacity = interpolate(beat, [-1, 1], [0.04, 0.11]);
  return (
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(135deg, rgba(112,255,225,0.08), transparent 42%, rgba(255,80,135,0.07))",
        opacity,
        mixBlendMode: "screen",
      }}
    />
  );
};

const eventLocalProgress = (event: TimelineEvent, ms: number): number => {
  if (event.durationMs <= 0) {
    return 0;
  }
  return Math.min(Math.max((ms - event.startMs) / event.durationMs, 0), 1);
};

const StoryLightCues: React.FC<{
  event: TimelineEvent;
  ms: number;
  shotProgress: number;
}> = ({ event, ms, shotProgress }) => {
  const frame = useCurrentFrame();
  const local = eventLocalProgress(event, ms);
  const registerSpeaking = event.cast === "第十三レジ";
  const futureSpeaking = event.cast === "未来の会社員";
  const takumiOrMina = event.cast === "タクミ" || event.cast === "ミナ";
  const cueStrength = interpolate(Math.sin(local * Math.PI), [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sweep = ((frame * 7) % 1640) - 180;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {registerSpeaking ? (
        <>
          <div
            style={{
              position: "absolute",
              left: 320 + Math.sin(frame * 0.07) * 22,
              top: 34 + Math.sin(frame * 0.05) * 8,
              width: 620,
              height: 620,
              borderRadius: "50%",
              border: "2px solid rgba(112,255,225,0.30)",
              opacity: cueStrength * 0.72,
              transform: `scale(${0.74 + local * 0.52})`,
              boxShadow: "0 0 46px rgba(112,255,225,0.42), inset 0 0 30px rgba(112,255,225,0.20)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: sweep,
              top: 80,
              width: 170,
              height: 560,
              background: "linear-gradient(90deg, transparent, rgba(112,255,225,0.24), transparent)",
              transform: "skewX(-18deg)",
              opacity: 0.42 + Math.sin(shotProgress * Math.PI * 8) * 0.08,
              mixBlendMode: "screen",
            }}
          />
        </>
      ) : null}
      {futureSpeaking ? (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: 0,
            width: "54%",
            height: "100%",
            background:
              "radial-gradient(circle at 64% 48%, rgba(90,210,255,0.22), transparent 34%), linear-gradient(90deg, transparent, rgba(30,120,150,0.20))",
            opacity: 0.38 + cueStrength * 0.28,
            mixBlendMode: "screen",
          }}
        />
      ) : null}
      {takumiOrMina ? (
        <div
          style={{
            position: "absolute",
            left: event.cast === "ミナ" ? 610 : 0,
            top: 0,
            width: event.cast === "ミナ" ? 560 : 520,
            height: "100%",
            background:
              "radial-gradient(circle at 52% 45%, rgba(255,242,198,0.14), transparent 38%)",
            opacity: 0.26 + cueStrength * 0.22,
            mixBlendMode: "screen",
          }}
        />
      ) : null}
      {ms > 52000 ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(circle at 50% 52%, rgba(255,245,202,0.16), transparent 44%), radial-gradient(circle at 74% 30%, rgba(112,255,225,0.16), transparent 28%)",
            opacity: interpolate(ms, [52000, 54800, 60000], [0, 0.95, 0.45], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            mixBlendMode: "screen",
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};

const ForegroundMotion: React.FC<{ event: TimelineEvent; ms: number }> = ({ event, ms }) => {
  const frame = useCurrentFrame();
  const suspense = Number(event.number || 0) >= 49 || ms > 33000;
  const leftSweep = ((frame * 2.2) % 1500) - 180;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: leftSweep,
          top: 58,
          width: 92,
          height: 610,
          background: "linear-gradient(90deg, rgba(0,0,0,0), rgba(0,0,0,0.22), rgba(0,0,0,0))",
          transform: "skewX(-8deg)",
          opacity: suspense ? 0.42 : 0.18,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 54 + Math.sin(frame * 0.04) * 4,
          height: 116,
          background:
            "linear-gradient(to bottom, transparent, rgba(1,3,8,0.28) 44%, rgba(1,3,8,0.60))",
        }}
      />
    </AbsoluteFill>
  );
};

const Effects: React.FC<{
  event: TimelineEvent;
  shot: number;
  shotProgress: number;
}> = ({ event, shot, shotProgress }) => {
  const flash = shotProgress < 0.08 ? interpolate(shotProgress, [0, 0.08], [0.25, 0]) : 0;
  const register = event.cast === "第十三レジ";
  const suspense = Number(event.number || 0) >= 19;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `rgba(255,255,255,${flash})`,
        }}
      />
      {register ? (
        <>
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "repeating-linear-gradient(0deg, rgba(112,255,225,0.12) 0 1px, transparent 1px 13px)",
              mixBlendMode: "screen",
            }}
          />
          {Array.from({ length: 9 }).map((_, index) => {
            const top = 80 + index * 62 + Math.sin(shot + index) * 18;
            return (
              <div
                key={index}
                style={{
                  position: "absolute",
                  left: 0,
                  top,
                  width: "100%",
                  height: 4 + (index % 3) * 4,
                  background: "rgba(112,255,225,0.22)",
                  transform: `translateX(${Math.sin(shotProgress * Math.PI * 8 + index) * 28}px)`,
                }}
              />
            );
          })}
        </>
      ) : null}
      {suspense ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(90deg, rgba(0,0,0,0.52), transparent 28%, transparent 72%, rgba(0,0,0,0.48))",
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};

const SilentTitle: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 14, 86, 116], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const x = interpolate(frame, [0, 35], [-54, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        opacity,
        background:
          "linear-gradient(90deg, rgba(0,0,0,0.72), rgba(0,0,0,0.2), transparent)",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 86 + x,
          top: 74,
          color: "#f8f6e9",
          fontFamily: "Yu Gothic, Meiryo, sans-serif",
        }}
      >
        <div style={{ fontSize: 78, fontWeight: 900, letterSpacing: 0 }}>第十三レジ</div>
        <div
          style={{
            marginTop: 14,
            width: 420,
            height: 5,
            background: "#70ffe1",
            boxShadow: "0 0 20px #70ffe1",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

const ShotBars: React.FC<{ shotProgress: number }> = ({ shotProgress }) => {
  const slide = interpolate(shotProgress, [0, 0.2, 1], [58, 0, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: -slide,
          height: 58,
          background: "#05070c",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: -slide,
          height: 58,
          background: "#05070c",
        }}
      />
    </>
  );
};

const AnimePV: React.FC<{ bundle: TimelineBundle; audioFile: string }> = ({ bundle, audioFile }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const event = activeEventAt(bundle.events, ms);
  const shotLen = shotLengthFrames(event);
  const shot = Math.floor(frame / shotLen);
  const shotProgress = (frame % shotLen) / shotLen;
  const finale = frame >= fps * 52;
  const shake =
    event.cast === "第十三レジ"
      ? Math.sin(frame * 1.7) * 7 + (random(`shake-${frame}`) - 0.5) * 4
      : 0;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#05070c",
        overflow: "hidden",
        transform: `translate(${shake}px, ${-shake * 0.4}px)`,
      }}
    >
      <Audio src={staticFile(`${assetBase}/audio/${audioFile}`)} />
      <Background event={event} shot={shot} shotProgress={shotProgress} />
      <RegisterLayer event={event} shot={shot} shotProgress={shotProgress} />
      {!finale ? <GuestMontage event={event} shot={shot} shotProgress={shotProgress} /> : null}
      {!finale ? <CharacterLayer event={event} shot={shot} shotProgress={shotProgress} /> : null}
      <AllCastFinale />
      <StoryLightCues event={event} ms={ms} shotProgress={shotProgress} />
      <ForegroundMotion event={event} ms={ms} />
      <ForegroundShade />
      <Effects event={event} shot={shot} shotProgress={shotProgress} />
      <MusicPulse />
      <ShotBars shotProgress={shotProgress} />
      <SilentTitle />
    </AbsoluteFill>
  );
};

export const NoSubtitleAnimePV: React.FC = () => {
  return <AnimePV bundle={timeline} audioFile="voice_drama.wav" />;
};

export const TrailerAnimePV: React.FC = () => {
  return <AnimePV bundle={trailerTimeline} audioFile="trailer_voice.wav" />;
};
