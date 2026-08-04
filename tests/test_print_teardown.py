"""Guards for Utskrift on mobile/tablet browsers.

`printTables()` prints by appending a hidden `#print-root` holding the shift
tables and hiding everything else through `@media print`. The whole thing turns
on *when the injected state is torn down again*.

Chrome on Android does not block in `window.print()`. It returns immediately,
fires `afterprint` right away, and hands the actual rendering to the Android
print framework, which snapshots the page some time later. Any teardown hung
off `afterprint` — or off a `matchMedia('print')` change — therefore runs
**before** the snapshot exists: `#print-root` and `body.is-printing` are gone by
the time the page is captured, so the tablet prints the live page instead. With
the mobile menu still open that is a full-screen overlay repeated across every
page, which is what "Utskrift prints 10x the menu" was.

Reproduced 2026-08-04 by firing `afterprint` synchronously from a stubbed
`window.print()` at an 820px viewport: the control run produced 19 pages of
shift tables, the early-`afterprint` run 13 pages of page chrome.

So: teardown must not be driven by print events, and the navigation chrome must
not be printable even if the injected state is missing.
"""

import re
from pathlib import Path

import pytest

JS_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
PRINT_CSS = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "static"
    / "css"
    / "base"
    / "print.css"
)


_JS_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def _js_modules():
    """Every JS module, paired with its comment-stripped source.

    These guards describe themselves in the comments they police, so they have
    to read code rather than prose.
    """
    return [
        (p.relative_to(JS_DIR).as_posix(), _JS_COMMENT.sub("", p.read_text()))
        for p in sorted(JS_DIR.rglob("*.js"))
    ]


class TestNoPrintEventTeardown:
    """The teardown must not race the asynchronous mobile print snapshot."""

    @pytest.mark.parametrize("event", ["afterprint", "beforeprint"])
    def test_no_print_event_listener(self, event):
        offenders = [
            name
            for name, src in _js_modules()
            if f"'{event}'" in src or f'"{event}"' in src
        ]
        assert offenders == [], (
            f"{offenders} listens for {event!r}. Chrome Android fires it before "
            "the print snapshot is rendered, so anything it removes is missing "
            "from the printout."
        )

    def test_no_print_media_query_listener(self):
        """matchMedia('print') has the same timing problem as afterprint."""
        offenders = [
            name
            for name, src in _js_modules()
            if re.search(r"matchMedia\(\s*['\"]print['\"]", src)
        ]
        assert offenders == [], (
            f"{offenders} watches matchMedia('print'). On mobile the change "
            "event does not reliably straddle the snapshot."
        )


class TestSinglePrintImplementation:
    """Two copies of printTables() meant a fix could land on the dead one.

    Both `utils.js` and `print-utils.js` used to define printTables and assign
    `window.printTables`; which one survived depended on ES module evaluation
    order, so editing the wrong file changed nothing at runtime.
    """

    def test_only_one_module_registers_print_tables(self):
        registrars = [
            name for name, src in _js_modules() if "window.printTables" in src
        ]
        assert len(registrars) == 1, (
            f"window.printTables is registered by {registrars}; the last module "
            "evaluated silently wins."
        )

    def test_only_one_module_defines_print_html(self):
        definers = [name for name, src in _js_modules() if "_printHtml" in src]
        assert len(definers) == 1, f"_printHtml duplicated across {definers}"


class TestChromeNeverPrints:
    """Defence in depth: page chrome must be unprintable on its own.

    These rules sit outside the `body.is-printing` guard on purpose. If the
    injected state is ever lost again the printout degrades to the page
    content — never to a stack of navbars and menu overlays.
    """

    def _print_media_block(self):
        # Comments stripped first: they explain these very rules, so prose
        # would otherwise satisfy the assertions the rules are meant to carry.
        css = re.sub(r"/\*.*?\*/", "", PRINT_CSS.read_text(), flags=re.S)
        opening = re.search(r"@media\s+print\s*\{", css)
        assert opening, "no @media print block in print.css"
        start = opening.start()
        depth, i = 0, opening.end() - 1
        for j in range(i, len(css)):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    return css[start : j + 1]
        raise AssertionError("unterminated @media print block")

    @pytest.mark.parametrize(
        "selector", ["header", ".modern-navbar", ".dropdown-menu"]
    )
    def test_chrome_hidden_unconditionally(self, selector):
        block = self._print_media_block()
        rule = re.search(
            r"(^|[,\s{])" + re.escape(selector) + r"\s*[,{]", block, re.M
        )
        assert rule, f"{selector} is not hidden in @media print"
        # …and not only behind the is-printing guard.
        guarded = re.findall(
            r"body\.is-printing[^{}]*" + re.escape(selector), block
        )
        assert not guarded, (
            f"{selector} is only hidden while body.is-printing is set; that "
            "class is exactly what goes missing when the teardown races."
        )
