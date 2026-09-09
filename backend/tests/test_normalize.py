from app.llm.validation import normalize


def test_normalize_folds_presentation_but_preserves_wording():
    assert normalize("  Two\n Approvers,\tplease. ") == "Two Approvers, please."
    assert normalize("Acme’s “closed” – x") == "Acme's \"closed\" - x"
    assert normalize("third-\nparty") == "third-party"
    assert normalize("• a\n• b") == "a b"
