import orthofill


def test_version():
    assert orthofill.__version__ == "0.1.0b1"
    assert orthofill.VERSION_LABEL == "0.1 beta"
