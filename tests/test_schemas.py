"""Tests for schema models and parse_repo_url utility."""

import pytest
from pydantic import ValidationError

from app.models.schemas import SearchRequest, parse_repo_url


class TestParseRepoUrl:
    def test_full_https_url(self):
        assert parse_repo_url("https://github.com/owner/repo") == ("owner", "repo")

    def test_full_url_with_www(self):
        assert parse_repo_url("https://www.github.com/owner/repo") == ("owner", "repo")

    def test_url_with_git_suffix(self):
        assert parse_repo_url("https://github.com/owner/repo.git") == ("owner", "repo")

    def test_owner_repo_shorthand(self):
        assert parse_repo_url("owner/repo") == ("owner", "repo")

    def test_url_with_trailing_slash(self):
        assert parse_repo_url("https://github.com/owner/repo/") == ("owner", "repo")

    def test_url_with_whitespace(self):
        assert parse_repo_url("  https://github.com/owner/repo  ") == ("owner", "repo")

    def test_http_url(self):
        assert parse_repo_url("http://github.com/owner/repo") == ("owner", "repo")

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid repo URL"):
            parse_repo_url("not-valid")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Invalid repo URL"):
            parse_repo_url("")

    def test_url_with_extra_path_raises(self):
        with pytest.raises(ValueError, match="Invalid repo URL"):
            parse_repo_url("https://github.com/owner/repo/tree/main")


class TestSearchRequestWeights:
    def test_weight_purpose_above_range(self):
        with pytest.raises(ValidationError, match="weight_purpose"):
            SearchRequest(repo_url="owner/repo", weight_purpose=1.5)

    def test_weight_purpose_below_range(self):
        with pytest.raises(ValidationError, match="weight_purpose"):
            SearchRequest(repo_url="owner/repo", weight_purpose=-0.1)

    def test_weight_stack_above_range(self):
        with pytest.raises(ValidationError, match="weight_stack"):
            SearchRequest(repo_url="owner/repo", weight_stack=1.5)

    def test_weight_stack_below_range(self):
        with pytest.raises(ValidationError, match="weight_stack"):
            SearchRequest(repo_url="owner/repo", weight_stack=-0.1)

    def test_edge_values_accepted(self):
        req = SearchRequest(repo_url="owner/repo", weight_purpose=0.0, weight_stack=1.0)
        assert req.weight_purpose == 0.0
        assert req.weight_stack == 1.0

    def test_defaults(self):
        req = SearchRequest(repo_url="owner/repo")
        assert req.weight_purpose == 0.7
        assert req.weight_stack == 0.3
        assert req.limit == 20
        assert req.min_stars == 0


class TestSearchRequestLimit:
    def test_limit_zero_rejected(self):
        with pytest.raises(ValidationError, match="limit"):
            SearchRequest(repo_url="owner/repo", limit=0)

    def test_limit_above_max_rejected(self):
        with pytest.raises(ValidationError, match="limit"):
            SearchRequest(repo_url="owner/repo", limit=101)

    def test_limit_boundary_values_accepted(self):
        req1 = SearchRequest(repo_url="owner/repo", limit=1)
        assert req1.limit == 1
        req100 = SearchRequest(repo_url="owner/repo", limit=100)
        assert req100.limit == 100


class TestSearchRequestWeightSum:
    def test_weights_summing_too_high_rejected(self):
        with pytest.raises(ValidationError, match="must equal 1.0"):
            SearchRequest(repo_url="owner/repo", weight_purpose=0.9, weight_stack=0.9)

    def test_weights_summing_too_low_rejected(self):
        with pytest.raises(ValidationError, match="must equal 1.0"):
            SearchRequest(repo_url="owner/repo", weight_purpose=0.3, weight_stack=0.3)
