"""Skills-library tests: the inherited experience stays generic, whole and wired.

`docs/SKILLS_LIBRARY.md` is the genericized experience of earlier deployments,
shipped so a crew starts with judgment instead of relearning it. Four
properties are pinned here.

1. **Generic.** No product, project or person name from the deployments it was
   mined from. The library's value is that it applies to any product; a name
   turns a lesson back into an anecdote about somebody else's system.
2. **Shaped.** Sections run 1..N without gaps, every entry carries Why, Check
   and Roles, and a collapsed duplicate points at an entry that exists.
3. **Cited correctly.** Every failure class it names exists in the registry or
   the shipped library -- a citation to a class that is not there sends the
   reader nowhere.
4. **Wired.** Every role sheet carries a Starting skills block that cites the
   library, and every section or entry number it names exists. A library no
   role is told to read is a library nobody reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
LIBRARY = KIT / "docs" / "SKILLS_LIBRARY.md"
AGENTS = KIT / ".claude" / "agents"
REGISTRIES = (KIT / "FAILURE_PATTERNS.md", KIT / "templates" / "FAILURE_PATTERNS.md.template")

ROLES = ("adjudicator", "architect", "builder", "foreman", "integrator",
         "researcher", "reviewer", "warden")

#: Names of the deployments the library was mined from, their code names and
#: their people. Case-sensitive where the word is also ordinary English in
#: lower case (a "max" value, a "reef" metaphor); case-insensitive otherwise.
FORBIDDEN_EXACT = re.compile(r"\b(MAX|MAX3|MAX3000|MARA|REEF|MRC|Scout|Hawkeye|Bouncer)\b")
FORBIDDEN_ANY = re.compile(
    r"netsniff|feed ?hacker|neuroster|linkedin|max ?research ?collective|\bjason\b|\bmax3",
    re.IGNORECASE)

ENTRY = re.compile(r"(?ms)^\*\*(\d+)\.(\d+) (.*?)(?=^\*\*\d+\.\d+ |^#|\Z)")
POINTER = re.compile(r"Stated once, as (\d+\.\d+);")


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _entries(text: str) -> dict[str, str]:
    return {"%s.%s" % (m.group(1), m.group(2)): m.group(3) for m in ENTRY.finditer(text)}


def _starting_skills(role: str) -> str:
    t = _text(AGENTS / ("%s.md" % role))
    m = re.search(r"(?ms)^## (?:0\. )?Starting skills\n(.*?)(?=^## )", t)
    assert m, "%s.md has no Starting skills section" % role
    return m.group(1)


def forbidden_names(text: str) -> list[str]:
    return FORBIDDEN_EXACT.findall(text) + FORBIDDEN_ANY.findall(text)


# ------------------------------------------------------------------ 1. generic

def test_library_names_no_product_project_or_person():
    hits = forbidden_names(_text(LIBRARY))
    assert not hits, "the skills library names a source deployment: %s" % sorted(set(hits))


@pytest.mark.parametrize("role", ROLES)
def test_starting_skills_blocks_name_no_product(role):
    hits = forbidden_names(_starting_skills(role))
    assert not hits, "%s Starting skills names a source deployment: %s" % (role, hits)


@pytest.mark.parametrize("sample", [
    "a lesson from MAX3 about probes", "the REEF appliance", "as MRC found",
    "Scout reviewed it", "the Neuroster save format", "a LinkedIn feed",
    "--profile max3", "package max3000",
])
def test_the_name_guard_catches_each_form(sample):
    """Mutation: each form the guard exists for is caught on its own."""
    assert forbidden_names(sample), sample


@pytest.mark.parametrize("sample", [
    "set max-age=31536000", "cap at max(n, 1)", "a resident app (3)",
])
def test_the_name_guard_passes_ordinary_words(sample):
    assert not forbidden_names(sample), sample


def test_library_is_ascii():
    raw = LIBRARY.read_bytes()
    bad = [i for i, b in enumerate(raw) if b > 127]
    assert not bad, "non-ASCII byte at offset %d" % bad[0]


# ------------------------------------------------------------------- 2. shaped

def test_sections_run_without_gaps():
    nums = [int(n) for n in re.findall(r"(?m)^## (\d+)\. ", _text(LIBRARY))]
    assert nums == list(range(1, len(nums) + 1)), nums
    assert len(nums) >= 19


#: How many entries each section holds, written down independently of the file
#: so that losing one -- a deleted block, a heading the parser no longer sees --
#: fails here instead of passing every count and numbering check. A pointer
#: ("Stated once, as ...") counts: it keeps its number. Retiring or adding an
#: entry is deliberate, and this table is where that is recorded.
ENTRIES_PER_SECTION = {
    1: 22, 2: 10, 3: 9, 4: 9, 5: 12, 6: 15, 7: 10, 8: 14, 9: 5,
    10: 8, 11: 17, 12: 5, 13: 8, 14: 8, 15: 26, 16: 15, 17: 12, 18: 6,
}


def test_every_entry_sits_under_its_own_section_heading():
    """An entry whose number disagrees with the heading above it is read by
    the wrong role: section 18's readers never see an 18.6 filed under 17."""
    current = None
    seen: list[str] = []
    for line in _text(LIBRARY).splitlines():
        head = re.match(r"^## (\d+)\. ", line)
        if head:
            current = head.group(1)
            continue
        m = re.match(r"^\*\*(\d+)\.(\d+) ", line)
        if m:
            assert m.group(1) == current, "entry %s.%s sits under section %s" % (
                m.group(1), m.group(2), current)
            seen.append("%s.%s" % (m.group(1), m.group(2)))
    assert len(seen) == len(set(seen)), "an entry number is used twice"


def test_the_entry_set_matches_the_recorded_baseline():
    expected = {"%d.%d" % (s, n) for s, count in ENTRIES_PER_SECTION.items()
                for n in range(1, count + 1)}
    actual = set(_entries(_text(LIBRARY)))
    assert actual == expected, "missing %s, unexpected %s" % (
        sorted(expected - actual), sorted(actual - expected))


def test_every_entry_carries_why_check_and_roles_or_points_at_one_that_does():
    entries = _entries(_text(LIBRARY))
    for num, body in entries.items():
        ptr = POINTER.search(body)
        if ptr:
            target = entries.get(ptr.group(1))
            assert target is not None, "%s points at missing entry %s" % (num, ptr.group(1))
            assert not POINTER.search(target), "%s points at another pointer" % num
            continue
        for field in ("*Why:*", "*Check:*", "*Roles:*"):
            assert field in body, "entry %s lacks %s" % (num, field)


# ----------------------------------------------------------- 3. cited correctly

def test_every_cited_failure_class_exists():
    known: set[str] = set()
    for reg in REGISTRIES:
        known |= set(re.findall(r"(?m)^#{2,3} (F-[A-Z0-9-]+) - ", _text(reg)))
    cited = set(re.findall(r"\bF-[A-Z][A-Z0-9-]*-\d{3}\b", _text(LIBRARY)))
    missing = sorted(cited - known)
    assert not missing, "the library cites classes that do not exist: %s" % missing


def test_every_cited_kit_path_exists():
    paths = set(re.findall(r"`((?:docs|templates|tools|tests|\.claude)/[^`\s]+)`", _text(LIBRARY)))
    missing = sorted(p for p in paths if not (KIT / p).exists())
    assert not missing, missing


# -------------------------------------------------------------------- 4. wired

@pytest.mark.parametrize("role", ROLES)
def test_every_role_sheet_points_at_the_library(role):
    block = _starting_skills(role)
    assert "docs/SKILLS_LIBRARY.md" in block


@pytest.mark.parametrize("role", ROLES)
def test_every_number_a_role_sheet_cites_exists(role):
    text = _text(LIBRARY)
    sections = set(re.findall(r"(?m)^## (\d+)\. ", text))
    entries = _entries(text)
    block = _starting_skills(role)
    for num in re.findall(r"(?m)^- (\d+\.\d+) ", block):
        assert num in entries, "%s cites entry %s, which does not exist" % (role, num)
        assert not POINTER.search(entries[num]), "%s cites %s, a pointer" % (role, num)
    for listed in re.findall(r"sections? ([\d, -]+)", block):
        for part in re.findall(r"\d+(?:-\d+)?", listed):
            lo, _, hi = part.partition("-")
            for n in range(int(lo), int(hi or lo) + 1):
                assert str(n) in sections, "%s cites section %d, which does not exist" % (role, n)


def test_the_role_map_covers_every_role():
    head = _text(LIBRARY).split("## Contents", 1)[0]
    for role in ROLES + ("maestro",):
        assert "**%s**" % role.capitalize() in head, "role map lacks %s" % role


def test_the_maestro_reads_it_and_the_brief_carries_it():
    assert "docs/SKILLS_LIBRARY.md" in _text(KIT / ".claude" / "MAESTRO.md")
    assert "docs/SKILLS_LIBRARY.md" in _text(KIT / ".claude" / "skills" / "wave" / "SKILL.md")
    assert "Skills library sections" in _text(KIT / "docs" / "handoffs" / "dispatch-brief.md")
