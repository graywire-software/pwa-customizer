"""Create a Chrome Web Store / manual-install ZIP with no dev files."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
destination = root / "PWA-Customizer.zip"
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    archive.write(root / "LICENSE", "LICENSE")
    for path in sorted((root / "extension").rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            archive.write(path, path.relative_to(root / "extension"))
print(destination)
