import { kamishibaiCuts } from "./kamishibaiCuts";
import { KamishibaiSlideshow } from "./KamishibaiSlideshow";

const imageBase = "assets/13th-register/kamishibai";

export const KamishibaiRealPV: React.FC = () => {
  return <KamishibaiSlideshow cuts={kamishibaiCuts} imageBase={imageBase} />;
};
