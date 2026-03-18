from transcribe.clipboard_content import ClipboardContent, pick_best_target


class TestClipboardContent:
    def test_dataclass_fields(self):
        c = ClipboardContent(data=b"hello", mime_type="text/plain")
        assert c.data == b"hello"
        assert c.mime_type == "text/plain"

    def test_pick_best_target_prefers_png(self):
        targets = ["text/plain", "image/jpeg", "image/png", "UTF8_STRING"]
        assert pick_best_target(targets) == "image/png"

    def test_pick_best_target_image_jpeg(self):
        targets = ["text/plain", "image/jpeg"]
        assert pick_best_target(targets) == "image/jpeg"

    def test_pick_best_target_text_fallback(self):
        targets = ["text/plain", "STRING"]
        assert pick_best_target(targets) == "text/plain"

    def test_pick_best_target_utf8_preferred_over_plain(self):
        targets = ["text/plain", "UTF8_STRING"]
        assert pick_best_target(targets) == "UTF8_STRING"

    def test_pick_best_target_empty(self):
        assert pick_best_target([]) is None

    def test_pick_best_target_unknown_types(self):
        assert (
            pick_best_target(["application/octet-stream", "x-special/gnome"])
            is None
        )
