from src.textkit import slugify


def test_spaces_become_one_dash():
    assert slugify("Hello World") == "hello-world"


def test_a_run_of_separators_is_one_dash():
    assert slugify("Hello -- World") == "hello-world"


def test_punctuation_does_not_reach_the_slug():
    assert slugify("Hello World!") == "hello-world"


def test_no_leading_or_trailing_dash():
    assert slugify(" -- Hello World -- ") == "hello-world"
