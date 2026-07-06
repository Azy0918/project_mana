import { kamishibaiCutsAseda } from "./kamishibaiCutsAseda";
import { KamishibaiSlideshow } from "./KamishibaiSlideshow";

const imageBase = "assets/13th-register/kamishibai_aseda";

export const KamishibaiAsedaPV: React.FC = () => {
  return <KamishibaiSlideshow cuts={kamishibaiCutsAseda} imageBase={imageBase} />;
};
