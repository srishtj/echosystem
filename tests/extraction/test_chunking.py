from extraction.chunking import dynamic_chunks


def test_empty_input_returns_empty_list():
    assert dynamic_chunks("") == []


def test_short_text_returns_single_chunk():
    text = "The quick brown fox jumps over the lazy dog."
    assert dynamic_chunks(text, max_tokens=3000) == [text]


def test_respects_token_boundary_and_preserves_words():
    text = " ".join(["word"] * 500)
    chunks = dynamic_chunks(text, max_tokens=50)

    assert len(chunks) > 1
    # No words should be lost or reordered across the chunk split.
    assert " ".join(chunks).split() == text.split()


def test_single_word_over_limit_is_not_dropped():
    long_word = "supercalifragilisticexpialidocious" * 50
    chunks = dynamic_chunks(long_word, max_tokens=5)

    assert long_word in " ".join(chunks)
