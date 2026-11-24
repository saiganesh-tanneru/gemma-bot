import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai_assistant import parse_natural_language_intent


def test_substring_false_positives_do_not_trigger():
    cmd_know = parse_natural_language_intent("know")
    assert "gesture" not in cmd_know
    assert "mood" not in cmd_know

    cmd_this = parse_natural_language_intent("this")
    assert "gesture" not in cmd_this
    assert "mood" not in cmd_this

    cmd_know_this = parse_natural_language_intent("I know this")
    assert "gesture" not in cmd_know_this
    assert "mood" not in cmd_know_this


def test_green_eyes_does_not_trigger_yes_nod():
    for phrase in ("green eyes", "change screen to green eyes"):
        cmd = parse_natural_language_intent(phrase)
        assert cmd.get("screen_color") == "GREEN"
        assert cmd.get("gesture") != "nod"
        assert cmd.get("mood") != "HAPPY"


def test_valid_word_matches():
    cmd_no = parse_natural_language_intent("no")
    assert cmd_no.get("gesture") == "shake"

    cmd_yes = parse_natural_language_intent("yes")
    assert cmd_yes.get("gesture") == "nod"
    assert cmd_yes.get("mood") == "HAPPY"

    cmd_hi = parse_natural_language_intent("hi")
    assert cmd_hi.get("mood") == "HAPPY"
    assert cmd_hi.get("gesture") == "nod"

    cmd_hello = parse_natural_language_intent("hello there")
    assert cmd_hello.get("mood") == "HAPPY"
    assert cmd_hello.get("gesture") == "nod"


def test_multi_word_phrase_precedence():
    # "dizzy spin" (2 words) should select dizzy_spin gesture rather than single-word dizzy mood alone
    cmd_spin = parse_natural_language_intent("dizzy spin")
    assert cmd_spin.get("gesture") == "dizzy_spin"
    assert cmd_spin.get("mood") == "DIZZY"

    # "look around" (2 words) should trigger scan
    cmd_scan = parse_natural_language_intent("look around")
    assert cmd_scan.get("gesture") == "scan"


def test_pytest_session_uses_keyword_intent_provider():
    from intent_parser import create_intent_parser

    # conftest.py forces the keyword provider so tests never hit the live
    # Sarvam API, even when SARVAM_API_KEY is set in the environment.
    parser = create_intent_parser()
    assert parser.provider is None
