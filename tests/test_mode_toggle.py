"""
Work-mode button — GWT, 3x depth.

GIVEN: the chat UI has a mode toggle
WHEN:  the DOM is checked for the button's existence
THEN:  an element with id 'mode-toggle' or similar is present in the HTML

GIVEN: the mode toggle is present
WHEN:  the CSS classes are checked
THEN:  at least 2 modes are labelled (e.g. Quick / Deep)

GIVEN: the i18n system
WHEN:  mode labels are checked for translatable-ness
THEN:  the keys 'mode.quick' and 'mode.deep' exist in all languages
"""
from pathlib import Path
import re
import pytest


# Angle 1: DOM — the HTML contains the mode toggle

class TestModToggleHTMLPerspective:
    """GIVEN the HTML, WHEN inspected, THEN mode toggle element exists."""

    @pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")
    def test_given_html_when_checked_then_mode_toggle_present(self):
        """
        GIVEN: index.html is loaded
        WHEN:  the search looks for the mode toggle
        THEN:  an element with id 'mode-toggle' or data-mode is present
        """
        html = (Path(__file__).parent.parent / "app" / "src" / "index.html").read_text()

        # Angle 1: the toggle element is present
        has_toggle = "mode-toggle" in html or "data-mode" in html or "mode-btn" in html
        assert has_toggle, "THEN: HTML muss einen Mode-Toggle-Button enthalten"

        # Angle 2: has an accessible label
        assert "aria-label" in html or "title=" in html, (
            "THEN: Mode-Toggle muss ein Accessible Label haben"
        )

        # Angle 3: Quick and Deep as options
        html_lower = html.lower()
        has_quick = "quick" in html_lower or "schnell" in html_lower or "kurz" in html_lower
        has_deep = "deep" in html_lower or "tief" in html_lower or "detail" in html_lower
        assert has_quick and has_deep, (
            "THEN: HTML muss Quick- und Deep-Modus-Optionen enthalten"
        )


# Angle 2: i18n — mode labels in all languages

class TestModToggleI18nPerspective:
    """GIVEN i18n.js, WHEN mode keys inspected, THEN all 6 languages have them."""

    @pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")
    def test_given_i18n_when_mode_keys_checked_then_all_languages_have_them(self):
        """
        GIVEN: i18n.js is loaded
        WHEN:  the mode.quick and mode.deep keys are looked for
        THEN:  both keys exist in all 6 languages
        """
        i18n = (Path(__file__).parent.parent / "app" / "src" / "i18n.js").read_text()

        # Angle 1: the key exists at all
        assert "'mode.quick'" in i18n or '"mode.quick"' in i18n, (
            "THEN: i18n.js muss 'mode.quick' Key haben"
        )
        assert "'mode.deep'" in i18n or '"mode.deep"' in i18n, (
            "THEN: i18n.js muss 'mode.deep' Key haben"
        )

        # Angle 2: the number of occurrences matches the number of languages (6)
        quick_count = i18n.count("'mode.quick'") + i18n.count('"mode.quick"')
        assert quick_count >= 6, (
            f"THEN: mode.quick muss in mind. 6 Sprachen definiert sein, found: {quick_count}"
        )

        # Angle 3: mode.label or mode.title present as well
        assert "'mode'" in i18n or "mode.label" in i18n or "mode.toggle" in i18n, (
            "THEN: Mind. ein mode.* Label-Key muss in i18n existieren"
        )


# Angle 3: JS — mode toggle handler in main.js

class TestModeToggleJSHandlerPerspective:
    """GIVEN main.js, WHEN mode handler inspected, THEN toggle logic present."""

    @pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")
    def test_given_mainjs_when_mode_handler_checked_then_toggle_logic_present(self):
        """
        GIVEN: main.js is loaded
        WHEN:  the search looks for the mode toggle handler
        THEN:  handler logic for mode-toggle is present (click or change)
        """
        js = (Path(__file__).parent.parent / "app" / "src" / "main.js").read_text()
        js_bindings = (Path(__file__).parent.parent / "app" / "src" / "modules" / "bindings.js").read_text()
        js_combined = js + js_bindings

        # Angle 1: a handler for mode-toggle is present
        has_handler = "mode-toggle" in js_combined or "modeToggle" in js_combined or "mode_toggle" in js_combined
        assert has_handler, "THEN: main.js muss einen Mode-Toggle-Handler haben"

        # Angle 2: sets response_style or similar
        has_style_setter = (
            "response_style" in js_combined
            or "responseMode" in js_combined
            or "mode" in js_combined.lower()
        )
        assert has_style_setter, "THEN: Handler muss einen Response-Modus setzen"

        # Angle 3: persists the choice (localStorage or API call)
        has_persistence = "localStorage" in js_combined or "profile" in js_combined.lower()
        assert has_persistence, (
            "THEN: Modus-Auswahl muss persistiert werden (localStorage oder API)"
        )
