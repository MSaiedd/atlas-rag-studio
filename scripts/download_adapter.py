"""Install the published, checksum-pinned development adapter into the local artifact directory."""

import hashlib
import io
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

URL = "https://github.com/MSaiedd/atlas-rag-studio/releases/download/v0.2.0/grounded-lora.zip"
SHA256 = "9aaf5469d35f621ceb528a35e1f96e09914cb279c23e8de8e251bdaff35201eb"


def main():
    destination = Path("artifacts/grounded-lora")
    if destination.exists():
        raise SystemExit(
            "artifacts/grounded-lora already exists. Preserve or move it before downloading."
        )
    with urlopen(URL, timeout=120) as response:
        raw = response.read(50 * 1024 * 1024 + 1)
    if len(raw) > 50 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != SHA256:
        raise SystemExit("Release adapter checksum mismatch; no weights were installed.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 100 * 1024 * 1024:
                raise SystemExit("Release archive exceeds the extraction budget.")
            for entry in archive.infolist():
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts or path.parts[0] != "grounded-lora":
                    raise SystemExit("Unexpected release archive path.")
                target = Path(temporary).joinpath(*path.parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(entry))
        shutil.move(str(Path(temporary) / "grounded-lora"), destination)
    print("Installed the released 128-step CPU development adapter. Restart Atlas to load it.")


if __name__ == "__main__":
    main()
