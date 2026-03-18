from dataclasses import dataclass


@dataclass
class ClipboardContent:
    data: bytes
    mime_type: str


_IMAGE_TYPES = ("image/png", "image/jpeg", "image/bmp", "image/tiff")
_TEXT_TYPES = (
    "UTF8_STRING",
    "text/plain;charset=utf-8",
    "text/plain",
    "STRING",
)


def pick_best_target(targets: list[str]) -> str | None:
    for t in _IMAGE_TYPES:
        if t in targets:
            return t
    for t in _TEXT_TYPES:
        if t in targets:
            return t
    return None
