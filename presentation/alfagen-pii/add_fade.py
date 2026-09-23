"""Add one root-level fade transition to each generated PPTX slide."""

import re
import sys
import zipfile
from pathlib import Path


def add_fade(source: Path) -> int:
    temporary = source.with_suffix(".fade-tmp.pptx")
    changed = 0
    try:
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(
            temporary, "w"
        ) as updated:
            for entry in original.infolist():
                data = original.read(entry.filename)
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", entry.filename):
                    text = data.decode("utf-8")
                    if "<p:transition" in text:
                        raise ValueError(f"Existing transition: {entry.filename}")
                    marker = "</p:cSld></p:sld>"
                    if text.count(marker) != 1:
                        raise ValueError(f"Unexpected slide XML: {entry.filename}")
                    text = text.replace(
                        marker,
                        "</p:cSld><p:transition><p:fade/></p:transition></p:sld>",
                    )
                    data = text.encode("utf-8")
                    changed += 1
                updated.writestr(entry, data)
        if changed == 0:
            raise ValueError("No slides found")
        with zipfile.ZipFile(temporary) as checked:
            if checked.testzip() is not None:
                raise ValueError("PPTX integrity check failed")
        temporary.replace(source)
        return changed
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    count = add_fade(Path(sys.argv[1]))
    print(f"Fade transitions added: {count}")
