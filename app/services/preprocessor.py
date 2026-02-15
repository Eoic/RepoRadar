"""Text preprocessing pipeline for RepoRadar.

Pure functions for cleaning README content, extracting dependencies from
manifest files, and composing text inputs for the dual-vector embedding model.
"""

from __future__ import annotations

import json
import re
import tomllib

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_README_CHARS = 1800  # ~450 tokens, leaves room for description+topics within 512-token limit

_BADGE_PATTERNS = re.compile(
    r"shields\.io|img\.shields|badge\.fury|codecov\.io|travis-ci|badge|github\.com/.+/(badge|actions)",
    re.IGNORECASE,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_IMAGE_LINK_RE = re.compile(r"!\[.*?\]\(.*?\)")
_LINK_ONLY_LINE_RE = re.compile(r"^\s*\[.*\]\(.*\)\s*$")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

# Version specifier regex for requirements.txt / PEP 508 style
_VERSION_SPEC_RE = re.compile(r"[><=!~]+.*$")
_EXTRAS_RE = re.compile(r"\[.*?\]")

# Gradle dependency patterns
_GRADLE_DEP_RE = re.compile(
    r"""(?:implementation|compile|api|testImplementation)\s*"""
    r"""[('"]([^'"()]+)['")\s]""",
    re.MULTILINE,
)

# go.mod patterns
_GO_REQUIRE_BLOCK_RE = re.compile(r"require\s*\((.*?)\)", re.DOTALL)
_GO_SINGLE_REQUIRE_RE = re.compile(r"^require\s+(\S+)", re.MULTILINE)

# Gemfile pattern
_GEMFILE_GEM_RE = re.compile(r"""gem\s+['"]([^'"]+)['"]""")

# pom.xml dependency block pattern
_POM_DEPENDENCY_BLOCK_RE = re.compile(r"<dependency>(.*?)</dependency>", re.DOTALL)
_POM_ARTIFACT_ID_RE = re.compile(r"<artifactId>\s*(.*?)\s*</artifactId>")


# ---------------------------------------------------------------------------
# README cleaning
# ---------------------------------------------------------------------------


def clean_readme(raw_readme: str) -> str:
    """Clean README markdown content for embedding.

    Steps:
      1. Remove HTML tags.
      2. Remove markdown image links ``![...](...)``
      3. Remove badge lines (shields.io, CI badges, etc.).
      4. Remove lines that are only markdown links.
      5. Collapse multiple blank lines to a single blank line.
      6. Strip leading/trailing whitespace.
      7. Truncate to ~1800 characters (~450 tokens).
    """
    if not raw_readme:
        return ""

    text = raw_readme

    # 1. Remove HTML tags
    text = _HTML_TAG_RE.sub("", text)

    # 2. Remove markdown image links
    text = _IMAGE_LINK_RE.sub("", text)

    # 3. Remove badge lines and 4. Remove link-only lines
    lines: list[str] = []
    for line in text.splitlines():
        if _BADGE_PATTERNS.search(line):
            continue
        if _LINK_ONLY_LINE_RE.match(line):
            continue
        lines.append(line)
    text = "\n".join(lines)

    # 5. Collapse multiple blank lines
    text = _MULTI_BLANK_RE.sub("\n\n", text)

    # 6. Strip leading/trailing whitespace
    text = text.strip()

    # 7. Truncate
    if len(text) > _MAX_README_CHARS:
        text = text[:_MAX_README_CHARS]

    return text


# ---------------------------------------------------------------------------
# Dependency extraction
# ---------------------------------------------------------------------------


def extract_dependencies(content: str, manifest_type: str) -> list[str]:
    """Parse dependency names from a manifest file.

    Args:
        content: Raw text content of the manifest file.
        manifest_type: The filename of the manifest (e.g. ``"requirements.txt"``).

    Returns:
        A list of lowercase package names without version specifiers.
        Returns an empty list for unknown manifest types.
    """
    parsers: dict[str, object] = {
        "requirements.txt": _parse_requirements_txt,
        "pyproject.toml": _parse_pyproject_toml,
        "package.json": _parse_package_json,
        "Cargo.toml": _parse_cargo_toml,
        "pubspec.yaml": _parse_pubspec_yaml,
        "go.mod": _parse_go_mod,
        "Gemfile": _parse_gemfile,
        "pom.xml": _parse_pom_xml,
        "build.gradle": _parse_build_gradle,
    }
    parser = parsers.get(manifest_type)
    if parser is None:
        return []
    return parser(content)  # type: ignore[operator]


# -- Individual parsers -----------------------------------------------------


def _parse_requirements_txt(content: str) -> list[str]:
    deps: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        # Skip empty, comments, -r includes, and -- flags
        if not line or line.startswith("#") or line.startswith("-r") or line.startswith("--"):
            continue
        # Strip inline comments
        if " #" in line:
            line = line[: line.index(" #")]
        # Strip extras like [security]
        line = _EXTRAS_RE.sub("", line)
        # Strip version specifiers
        name = _VERSION_SPEC_RE.sub("", line).strip()
        if name:
            deps.append(name.lower())
    return deps


def _parse_pyproject_toml(content: str) -> list[str]:
    data = tomllib.loads(content)
    deps: list[str] = []

    # PEP 621: project.dependencies
    for dep_str in data.get("project", {}).get("dependencies", []):
        name = _strip_pep508(dep_str)
        if name:
            deps.append(name.lower())

    # Poetry: tool.poetry.dependencies
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name in poetry_deps:
        if name.lower() == "python":
            continue
        deps.append(name.lower())

    return deps


def _strip_pep508(dep: str) -> str:
    """Extract the package name from a PEP 508 dependency string."""
    # Remove extras
    dep = _EXTRAS_RE.sub("", dep)
    # Remove version specifiers and environment markers
    dep = re.split(r"[><=!~;]", dep, maxsplit=1)[0]
    return dep.strip()


def _parse_package_json(content: str) -> list[str]:
    data = json.loads(content)
    deps: list[str] = []
    for section in ("dependencies", "devDependencies"):
        for name in data.get(section, {}):
            deps.append(name.lower())
    return deps


def _parse_cargo_toml(content: str) -> list[str]:
    data = tomllib.loads(content)
    deps: list[str] = []
    for section in ("dependencies", "dev-dependencies"):
        for name in data.get(section, {}):
            deps.append(name.lower())
    return deps


def _parse_pubspec_yaml(content: str) -> list[str]:
    data = yaml.safe_load(content) or {}
    skip = {"flutter", "flutter_test"}
    deps: list[str] = []
    for section in ("dependencies", "dev_dependencies"):
        for name in data.get(section, {}) or {}:
            if name.lower() in skip:
                continue
            deps.append(name.lower())
    return deps


def _parse_go_mod(content: str) -> list[str]:
    deps: list[str] = []

    # Multi-line require blocks: require ( ... )
    for block_match in _GO_REQUIRE_BLOCK_RE.finditer(content):
        block = block_match.group(1)
        for line in block.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split()
            if parts:
                deps.append(parts[0].lower())

    # Single-line require statements: require module/path v1.2.3
    for match in _GO_SINGLE_REQUIRE_RE.finditer(content):
        module = match.group(1).lower()
        if module not in deps:
            deps.append(module)

    return deps


def _parse_gemfile(content: str) -> list[str]:
    return [m.group(1).lower() for m in _GEMFILE_GEM_RE.finditer(content)]


def _parse_pom_xml(content: str) -> list[str]:
    deps: list[str] = []
    for block in _POM_DEPENDENCY_BLOCK_RE.finditer(content):
        m = _POM_ARTIFACT_ID_RE.search(block.group(1))
        if m:
            deps.append(m.group(1).strip().lower())
    return deps


def _parse_build_gradle(content: str) -> list[str]:
    deps: list[str] = []
    for match in _GRADLE_DEP_RE.finditer(content):
        raw = match.group(1).strip()
        # Handle group:name:version notation
        parts = raw.split(":")
        if len(parts) >= 2:
            # Use group:name
            deps.append(f"{parts[0]}:{parts[1]}".lower())
        else:
            deps.append(raw.lower())
    return deps


# ---------------------------------------------------------------------------
# Text composition for embeddings
# ---------------------------------------------------------------------------


def compose_purpose_text(
    description: str | None,
    topics: list[str],
    readme: str,
) -> str:
    """Compose the purpose embedding input text.

    Format: ``"{readme}. {description}. Topics: {topics}."``

    README is placed first because it carries the richest signal about what a
    repository does.  If the embedding model truncates the input, the less
    important description and topics are what gets dropped.
    """
    parts: list[str] = []

    if readme:
        truncated = readme[:_MAX_README_CHARS]
        parts.append(truncated)

    if description:
        parts.append(description.rstrip("."))

    if topics:
        parts.append("Topics: " + ", ".join(topics))

    return ". ".join(parts) + "." if parts else ""


def compose_stack_text(
    primary_language: str | None,
    languages: dict[str, float],
    dependencies: list[str],
) -> str:
    """Compose the stack embedding input text.

    Format:
        ``"Primary language: {lang}. Languages: {list}. Dependencies: {list}."``
    """
    parts: list[str] = []

    if primary_language:
        parts.append(f"Primary language: {primary_language}")

    if languages:
        lang_list = ", ".join(f"{name} {pct:.0f}%" for name, pct in languages.items())
        parts.append(f"Languages: {lang_list}")

    if dependencies:
        dep_list = ", ".join(dependencies)
        parts.append(f"Dependencies: {dep_list}")

    return ". ".join(parts) + "." if parts else ""
