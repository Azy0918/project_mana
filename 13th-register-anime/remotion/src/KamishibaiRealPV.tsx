import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { useState } from "react";
import { kamishibaiCuts } from "./kamishibaiCuts";

const fps = 30;
const imageBase = "assets/13th-register/kamishibai";

const palette = [
  ["#07111f", "#102d42", "#79e7ff"],
  ["#11161b", "#26343a", "#ffd89a"],
  ["#0b1018", "#1f2440", "#9ab7ff"],
  ["#0c1715", "#17392f", "#8bffcf"],
  ["#160f14", "#35202a", "#ff9aae"],
];

const cutStartFrames = kamishibaiCuts.reduce<number[]>((starts, cut, index) => {
  if (index === 0) {
    return [0];
  }
  const previous = starts[index - 1] + Math.round(kamishibaiCuts[index - 1].duration * fps);
  return [...starts, previous];
}, []);

const getCurrentCut = (frame: number) => {
  let index = 0;
  for (let i = 0; i < cutStartFrames.length; i += 1) {
    if (frame >= cutStartFrames[i]) {
      index = i;
    }
  }
  const cut = kamishibaiCuts[index];
  const start = cutStartFrames[index];
  const duration = Math.round(cut.duration * fps);
  const local = frame - start;
  return { cut, index, local, duration };
};

const Placeholder: React.FC<{ index: number; caption: string; location: string; characters: string }> = ({
  index,
  caption,
  location,
  characters,
}) => {
  const [base, mid, accent] = palette[index % palette.length];
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(circle at 50% 38%, ${mid}, ${base} 62%, #030507 100%)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(145deg, rgba(255,255,255,0.09), transparent 34%), repeating-linear-gradient(0deg, rgba(255,255,255,0.035) 0 1px, transparent 1px 18px)",
          mixBlendMode: "screen",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 70,
          right: 70,
          top: 230,
          bottom: 300,
          border: `2px solid ${accent}`,
          boxShadow: `0 0 48px ${accent}55, inset 0 0 42px rgba(255,255,255,0.08)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 96,
          right: 96,
          top: 278,
          color: "#f6fbff",
          fontFamily: "Yu Gothic, Meiryo, sans-serif",
        }}
      >
        <div style={{ fontSize: 42, fontWeight: 800, letterSpacing: 0 }}>{caption}</div>
        <div style={{ marginTop: 24, fontSize: 24, color: "#c9d5df" }}>{location}</div>
        {characters ? <div style={{ marginTop: 12, fontSize: 22, color: accent }}>{characters}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

const FrameImage: React.FC<{ image: string; index: number; progress: number; caption: string; location: string; characters: string }> = ({
  image,
  index,
  progress,
  caption,
  location,
  characters,
}) => {
  const [missing, setMissing] = useState(false);
  const zoom = interpolate(progress, [0, 1], [1.025, 1.075]);
  const y = interpolate(progress, [0, 1], [0, -16]);
  return (
    <AbsoluteFill>
      <Placeholder index={index} caption={caption} location={location} characters={characters} />
      {missing ? null : (
        <Img
          onError={() => setMissing(true)}
          src={staticFile(`${imageBase}/${image}`)}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${zoom}) translateY(${y}px)`,
          }}
        />
      )}
    </AbsoluteFill>
  );
};

export const KamishibaiRealPV: React.FC = () => {
  const frame = useCurrentFrame();
  const { cut, index, local, duration } = getCurrentCut(frame);
  const progress = Math.max(0, Math.min(1, local / duration));
  const fadeIn = interpolate(local, [0, 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(local, [duration - 8, duration], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <AbsoluteFill style={{ backgroundColor: "#05070b", overflow: "hidden" }}>
      <AbsoluteFill style={{ opacity }}>
        <FrameImage
          image={cut.image}
          index={index}
          progress={progress}
          caption={cut.caption}
          location={cut.location}
          characters={cut.characters}
        />
      </AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: 38,
          bottom: 34,
          padding: "8px 12px",
          background: "rgba(3,6,10,0.55)",
          color: "rgba(245,248,252,0.82)",
          fontSize: 19,
          fontFamily: "Yu Gothic, Meiryo, sans-serif",
        }}
      >
        {cut.id} / {index + 1}
      </div>
    </AbsoluteFill>
  );
};
