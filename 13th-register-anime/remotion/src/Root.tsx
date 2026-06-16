import "./index.css";
import { Composition } from "remotion";
import { ThirteenthRegisterPv } from "./Composition";
import { NoSubtitleAnimePV, TrailerAnimePV } from "./NoSubtitleAnime";
import { VerticalShortPV } from "./VerticalShortPV";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ThirteenthRegisterPV"
        component={ThirteenthRegisterPv}
        durationInFrames={1800}
        fps={30}
        width={1280}
        height={720}
      />
      <Composition
        id="NoSubtitleAnimePV"
        component={NoSubtitleAnimePV}
        durationInFrames={1800}
        fps={30}
        width={1280}
        height={720}
      />
      <Composition
        id="TrailerAnimePV"
        component={TrailerAnimePV}
        durationInFrames={1800}
        fps={30}
        width={1280}
        height={720}
      />
      <Composition
        id="VerticalShortPV"
        component={VerticalShortPV}
        durationInFrames={750}
        fps={30}
        width={1080}
        height={1920}
      />
    </>
  );
};
