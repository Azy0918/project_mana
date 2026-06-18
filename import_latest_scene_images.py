from pathlib import Path
import shutil

from PIL import Image


GENERATED_DIR = Path(r"C:\Users\qvf03\.codex\generated_images\019ed5cd-695e-7752-9859-d406484ab069")
SOURCE_DIR = Path("outputs/scene_sources")
PUBLIC_DIR = Path("13th-register-kamishibai/assets/scenes")
SITE_DIR = Path("site/assets/scenes")

SCENE_NAMES = [
    "scene_01_opening",
    "scene_02_onigiri_shelf",
    "scene_03_register",
    "scene_04_future_worker_enters",
    "scene_05_future_onigiri_scan",
    "scene_06_microwave",
    "scene_07_receipt",
    "scene_08_back_to_normal",
]


def main() -> None:
    files = sorted(
        [path for path in GENERATED_DIR.iterdir() if path.is_file()],
        key=lambda path: path.stat().st_mtime,
    )[-len(SCENE_NAMES):]

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    for source, scene_name in zip(files, SCENE_NAMES):
        raw_path = SOURCE_DIR / f"{scene_name}{source.suffix.lower()}"
        shutil.copy2(source, raw_path)

        image = Image.open(source).convert("RGB")
        public_path = PUBLIC_DIR / f"{scene_name}.jpg"
        image.save(public_path, quality=88, optimize=True, progressive=False)
        try:
            shutil.copy2(public_path, SITE_DIR / public_path.name)
        except PermissionError:
            pass
        print(scene_name, source.name, image.size, public_path.stat().st_size)


if __name__ == "__main__":
    main()
