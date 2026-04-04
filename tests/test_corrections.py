from transcribe.corrections import (
    apply_corrections,
    build_whisper_prompt,
)


class TestExactReplacements:
    def test_simple_word_replacement(self):
        text = "push the comet to main"
        result = apply_corrections(
            text, replacements={"comet": "commit"}
        )
        assert result == "push the commit to main"

    def test_case_insensitive(self):
        text = "Push the Comet to main"
        result = apply_corrections(
            text, replacements={"comet": "commit"}
        )
        assert result == "Push the commit to main"

    def test_multi_word_replacement(self):
        text = "my name is martin poll eve"
        result = apply_corrections(
            text,
            replacements={"martin poll eve": "Martin Paul Eve"},
        )
        assert result == "my name is Martin Paul Eve"

    def test_no_match_leaves_text_unchanged(self):
        text = "nothing to change here"
        result = apply_corrections(
            text, replacements={"comet": "commit"}
        )
        assert result == "nothing to change here"

    def test_multiple_replacements(self):
        text = "the comet hit a meteorite"
        result = apply_corrections(
            text,
            replacements={
                "comet": "commit",
                "meteorite": "merge",
            },
        )
        assert result == "the commit hit a merge"

    def test_empty_text(self):
        assert apply_corrections("", replacements={"a": "b"}) == ""

    def test_none_text(self):
        assert apply_corrections(None, replacements={"a": "b"}) is None


class TestFuzzyMatching:
    def test_close_match_corrected(self):
        text = "my name is Martin Pole Eve"
        result = apply_corrections(
            text,
            custom_terms=["Martin Paul Eve"],
            threshold=0.8,
        )
        assert result == "my name is Martin Paul Eve"

    def test_distant_match_not_corrected(self):
        text = "the cat sat on the mat"
        result = apply_corrections(
            text,
            custom_terms=["Martin Paul Eve"],
            threshold=0.8,
        )
        assert result == "the cat sat on the mat"

    def test_single_word_fuzzy(self):
        text = "push the comit to main"
        result = apply_corrections(
            text,
            custom_terms=["commit"],
            threshold=0.8,
        )
        assert result == "push the commit to main"

    def test_threshold_boundary(self):
        # "Marton Poll Eave" vs "Martin Paul Eve" — somewhat close
        text = "hello Marton Poll Eave goodbye"
        # With a very high threshold, it should NOT match
        result = apply_corrections(
            text,
            custom_terms=["Martin Paul Eve"],
            threshold=0.99,
        )
        assert "Martin Paul Eve" not in result

    def test_short_text_fewer_words_than_term(self):
        text = "Martin Eve"
        result = apply_corrections(
            text,
            custom_terms=["Martin Paul Eve"],
            threshold=0.8,
        )
        # Text has fewer words than term; may or may not match
        # depending on ratio — just ensure no crash
        assert isinstance(result, str)

    def test_multiple_terms(self):
        text = "Martin Pole Eve works at Birkbek"
        result = apply_corrections(
            text,
            custom_terms=["Martin Paul Eve", "Birkbeck"],
            threshold=0.8,
        )
        assert "Martin Paul Eve" in result
        assert "Birkbeck" in result


class TestCombined:
    def test_replacements_and_fuzzy(self):
        text = "Martin Pole Eve will comet the code"
        result = apply_corrections(
            text,
            replacements={"comet": "commit"},
            custom_terms=["Martin Paul Eve"],
            threshold=0.8,
        )
        assert result == "Martin Paul Eve will commit the code"

    def test_no_corrections_configured(self):
        text = "hello world"
        result = apply_corrections(text)
        assert result == "hello world"


class TestBuildWhisperPrompt:
    def test_builds_from_replacements(self):
        prompt = build_whisper_prompt(
            replacements={"comet": "commit"}
        )
        assert prompt == "commit"

    def test_builds_from_custom_terms(self):
        prompt = build_whisper_prompt(
            custom_terms=["Martin Paul Eve", "Birkbeck"]
        )
        assert prompt == "Martin Paul Eve, Birkbeck"

    def test_combined_deduplicates(self):
        prompt = build_whisper_prompt(
            replacements={"comet": "commit"},
            custom_terms=["Martin Paul Eve", "commit"],
        )
        assert prompt == "commit, Martin Paul Eve"

    def test_empty_returns_none(self):
        assert build_whisper_prompt() is None
        assert build_whisper_prompt(replacements={}) is None
        assert (
            build_whisper_prompt(replacements={}, custom_terms=[])
            is None
        )
