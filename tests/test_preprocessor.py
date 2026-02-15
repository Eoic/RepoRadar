"""Tests for the text preprocessing pipeline."""

from __future__ import annotations

import textwrap

from app.services.preprocessor import (
    clean_readme,
    compose_purpose_text,
    compose_stack_text,
    extract_dependencies,
)

# ===================================================================
# clean_readme
# ===================================================================


class TestCleanReadme:
    """Tests for README cleaning logic."""

    def test_normal_readme(self):
        raw = textwrap.dedent("""\
            # My Project

            A useful library for doing things.

            ## Installation

            ```bash
            pip install my-project
            ```

            ## Usage

            Import and use like so:

            ```python
            import my_project
            my_project.do_stuff()
            ```
        """)
        result = clean_readme(raw)
        assert "# My Project" in result
        assert "A useful library" in result
        assert "pip install my-project" in result

    def test_html_heavy_readme(self):
        raw = textwrap.dedent("""\
            <h1>Project</h1>
            <p>This is a <strong>great</strong> project.</p>
            <div class="warning">
            <p>Be careful!</p>
            </div>
            <a href="https://example.com">Link</a>
            <br/>
            Some plain text after HTML.
        """)
        result = clean_readme(raw)
        # HTML tags should be stripped
        assert "<h1>" not in result
        assert "<p>" not in result
        assert "<strong>" not in result
        assert "<div" not in result
        assert "<a " not in result
        assert "<br/>" not in result
        # Content text should remain
        assert "Project" in result
        assert "great" in result
        assert "Some plain text after HTML." in result

    def test_readme_with_only_badges(self):
        raw = textwrap.dedent("""\
            [![Build Status](https://img.shields.io/travis/user/repo.svg)](https://travis-ci.org/user/repo)
            [![Coverage](https://codecov.io/gh/user/repo/badge.svg)](https://codecov.io/gh/user/repo)
            [![npm](https://badge.fury.io/js/package.svg)](https://www.npmjs.com/package/package)
            [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
        """)
        result = clean_readme(raw)
        # All badge lines should be removed, leaving effectively nothing
        assert result.strip() == ""

    def test_empty_string(self):
        assert clean_readme("") == ""

    def test_very_long_readme_is_truncated(self):
        # Create a README larger than 1800 characters
        long_text = "A" * 10_000
        result = clean_readme(long_text)
        assert len(result) <= 1800

    def test_image_links_removed(self):
        raw = textwrap.dedent("""\
            # Title

            ![Screenshot](https://example.com/img.png)

            Some description here.

            ![Another image](./local/path.jpg)
        """)
        result = clean_readme(raw)
        assert "![Screenshot]" not in result
        assert "![Another image]" not in result
        assert "Some description here." in result

    def test_link_only_lines_removed(self):
        raw = textwrap.dedent("""\
            # Title

            Good content here.

            [Just a link](https://example.com)

            More good content.
        """)
        result = clean_readme(raw)
        assert "[Just a link]" not in result
        assert "Good content here." in result
        assert "More good content." in result

    def test_multiple_blank_lines_collapsed(self):
        raw = "Line 1\n\n\n\n\n\nLine 2"
        result = clean_readme(raw)
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_mixed_badges_and_content(self):
        raw = textwrap.dedent("""\
            # My Library

            [![Build](https://img.shields.io/travis/user/repo)](https://travis-ci.org/user/repo)

            A Python library for data processing.

            ![demo](https://example.com/demo.gif)

            ## Features

            - Fast processing
            - Easy to use
        """)
        result = clean_readme(raw)
        assert "# My Library" in result
        assert "shields.io" not in result
        assert "![demo]" not in result
        assert "Fast processing" in result


# ===================================================================
# extract_dependencies
# ===================================================================


class TestExtractDependencies:
    """Tests for dependency extraction from various manifest formats."""

    def test_requirements_txt(self):
        content = textwrap.dedent("""\
            # Core dependencies
            flask>=2.0
            requests==2.28.1
            numpy~=1.24
            pandas
            # Dev tools
            pytest>=7.0
            -r base.txt
            --index-url https://pypi.org/simple
            sqlalchemy[asyncio]>=2.0  # ORM
        """)
        deps = extract_dependencies(content, "requirements.txt")
        assert "flask" in deps
        assert "requests" in deps
        assert "numpy" in deps
        assert "pandas" in deps
        assert "pytest" in deps
        assert "sqlalchemy" in deps
        # Versions should be stripped
        assert not any(">=" in d for d in deps)
        assert not any("==" in d for d in deps)
        # -r and -- lines should be excluded
        assert not any("base.txt" in d for d in deps)
        assert not any("index-url" in d for d in deps)

    def test_pyproject_toml(self):
        content = textwrap.dedent("""\
            [project]
            name = "mypackage"
            dependencies = [
                "fastapi>=0.110",
                "httpx>=0.27",
                "pydantic-settings>=2.1",
            ]

            [tool.poetry.dependencies]
            python = "^3.11"
            uvicorn = "^0.27"
            rich = ">=13.0"
        """)
        deps = extract_dependencies(content, "pyproject.toml")
        assert "fastapi" in deps
        assert "httpx" in deps
        assert "pydantic-settings" in deps
        assert "uvicorn" in deps
        assert "rich" in deps
        # "python" should be excluded from poetry deps
        assert "python" not in deps

    def test_package_json(self):
        content = textwrap.dedent("""\
            {
                "name": "my-app",
                "dependencies": {
                    "react": "^18.2.0",
                    "next": "14.0.0",
                    "axios": "^1.6.0"
                },
                "devDependencies": {
                    "typescript": "^5.3.0",
                    "eslint": "^8.56.0"
                }
            }
        """)
        deps = extract_dependencies(content, "package.json")
        assert "react" in deps
        assert "next" in deps
        assert "axios" in deps
        assert "typescript" in deps
        assert "eslint" in deps

    def test_cargo_toml(self):
        content = textwrap.dedent("""\
            [package]
            name = "my-crate"
            version = "0.1.0"

            [dependencies]
            serde = { version = "1.0", features = ["derive"] }
            tokio = { version = "1", features = ["full"] }
            reqwest = "0.11"

            [dev-dependencies]
            criterion = "0.5"
        """)
        deps = extract_dependencies(content, "Cargo.toml")
        assert "serde" in deps
        assert "tokio" in deps
        assert "reqwest" in deps
        assert "criterion" in deps

    def test_pubspec_yaml(self):
        content = textwrap.dedent("""\
            name: my_app
            dependencies:
              flutter:
                sdk: flutter
              provider: ^6.0.0
              http: ^1.1.0
              shared_preferences: ^2.2.0

            dev_dependencies:
              flutter_test:
                sdk: flutter
              mockito: ^5.4.0
        """)
        deps = extract_dependencies(content, "pubspec.yaml")
        assert "provider" in deps
        assert "http" in deps
        assert "shared_preferences" in deps
        assert "mockito" in deps
        # flutter and flutter_test should be excluded
        assert "flutter" not in deps
        assert "flutter_test" not in deps

    def test_go_mod(self):
        content = textwrap.dedent("""\
            module github.com/user/myapp

            go 1.21

            require (
                github.com/gin-gonic/gin v1.9.1
                github.com/go-sql-driver/mysql v1.7.1
                golang.org/x/crypto v0.17.0
            )

            require github.com/stretchr/testify v1.8.4
        """)
        deps = extract_dependencies(content, "go.mod")
        assert "github.com/gin-gonic/gin" in deps
        assert "github.com/go-sql-driver/mysql" in deps
        assert "golang.org/x/crypto" in deps
        assert "github.com/stretchr/testify" in deps

    def test_gemfile(self):
        content = textwrap.dedent("""\
            source 'https://rubygems.org'

            gem 'rails', '~> 7.0'
            gem "puma", ">= 5.0"
            gem 'pg'
            gem "sidekiq"

            group :development, :test do
              gem 'rspec-rails'
            end
        """)
        deps = extract_dependencies(content, "Gemfile")
        assert "rails" in deps
        assert "puma" in deps
        assert "pg" in deps
        assert "sidekiq" in deps
        assert "rspec-rails" in deps

    def test_pom_xml(self):
        content = textwrap.dedent("""\
            <project>
                <dependencies>
                    <dependency>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-starter-web</artifactId>
                        <version>3.2.0</version>
                    </dependency>
                    <dependency>
                        <groupId>com.fasterxml.jackson.core</groupId>
                        <artifactId>jackson-databind</artifactId>
                    </dependency>
                    <dependency>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok</artifactId>
                        <scope>provided</scope>
                    </dependency>
                </dependencies>
            </project>
        """)
        deps = extract_dependencies(content, "pom.xml")
        assert "spring-boot-starter-web" in deps
        assert "jackson-databind" in deps
        assert "lombok" in deps

    def test_build_gradle(self):
        content = textwrap.dedent("""\
            plugins {
                id 'java'
            }

            dependencies {
                implementation 'org.springframework.boot:spring-boot-starter-web:3.2.0'
                implementation "com.google.guava:guava:32.1.3-jre"
                api 'io.projectreactor:reactor-core:3.6.0'
                testImplementation 'org.junit.jupiter:junit-jupiter:5.10.0'
                compile 'commons-io:commons-io:2.15.0'
            }
        """)
        deps = extract_dependencies(content, "build.gradle")
        assert "org.springframework.boot:spring-boot-starter-web" in deps
        assert "com.google.guava:guava" in deps
        assert "io.projectreactor:reactor-core" in deps
        assert "org.junit.jupiter:junit-jupiter" in deps
        assert "commons-io:commons-io" in deps

    def test_unknown_manifest_returns_empty(self):
        deps = extract_dependencies("anything here", "unknown.file")
        assert deps == []


# ===================================================================
# compose_purpose_text
# ===================================================================


class TestComposePurposeText:
    """Tests for purpose text composition."""

    def test_all_fields_populated(self):
        result = compose_purpose_text(
            description="A web framework for Python",
            topics=["web", "python", "async"],
            readme="This library provides an async web framework.",
        )
        assert "A web framework for Python" in result
        assert "Topics: web, python, async" in result
        assert "This library provides an async web framework." in result
        # README should come first (most important signal)
        readme_pos = result.index("This library provides")
        desc_pos = result.index("A web framework for Python")
        assert readme_pos < desc_pos
        assert result.endswith(".")

    def test_none_description(self):
        result = compose_purpose_text(
            description=None,
            topics=["cli", "tool"],
            readme="A command line tool.",
        )
        assert "Topics: cli, tool" in result
        assert "A command line tool." in result
        # Should not start with ". " since readme is first
        assert not result.startswith(".")

    def test_empty_topics(self):
        result = compose_purpose_text(
            description="A data processing library",
            topics=[],
            readme="Handles CSV and JSON data.",
        )
        assert "A data processing library" in result
        assert "Handles CSV and JSON data." in result

    def test_all_empty(self):
        result = compose_purpose_text(
            description=None,
            topics=[],
            readme="",
        )
        assert result == ""

    def test_readme_truncated_in_purpose(self):
        long_readme = "X" * 10_000
        result = compose_purpose_text(
            description="Test",
            topics=[],
            readme=long_readme,
        )
        # The readme portion should be truncated to 1800 chars
        assert len(result) < 2000


# ===================================================================
# compose_stack_text
# ===================================================================


class TestComposeStackText:
    """Tests for stack text composition."""

    def test_all_fields_populated(self):
        result = compose_stack_text(
            primary_language="Python",
            languages={"Python": 80.0, "JavaScript": 15.0, "Shell": 5.0},
            dependencies=["fastapi", "httpx", "pydantic"],
        )
        assert "Primary language: Python" in result
        assert "Languages: Python 80%, JavaScript 15%, Shell 5%" in result
        assert "Dependencies: fastapi, httpx, pydantic" in result
        assert result.endswith(".")

    def test_none_primary_language(self):
        result = compose_stack_text(
            primary_language=None,
            languages={"Rust": 95.0, "C": 5.0},
            dependencies=["serde", "tokio"],
        )
        assert "Primary language" not in result
        assert "Languages: Rust 95%, C 5%" in result
        assert "Dependencies: serde, tokio" in result

    def test_all_empty(self):
        result = compose_stack_text(
            primary_language=None,
            languages={},
            dependencies=[],
        )
        assert result == ""

    def test_only_primary_language(self):
        result = compose_stack_text(
            primary_language="Go",
            languages={},
            dependencies=[],
        )
        assert result == "Primary language: Go."
