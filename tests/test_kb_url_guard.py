"""Tests for KB URL guard — SSRF prevention and javascript: XSS mitigation."""
from __future__ import annotations

import pytest

from sentinel.kb.url_guard import safe_href, validate_crawl_url


# --------------------------------------------------------------------------- #
# validate_crawl_url — SSRF guard
# --------------------------------------------------------------------------- #

def test_valid_public_url_passes():
    url = "https://biltiq.ai"
    assert validate_crawl_url(url) == url


def test_http_scheme_passes():
    url = "http://example.com"
    assert validate_crawl_url(url) == url


def test_javascript_scheme_blocked():
    with pytest.raises(ValueError, match="http or https"):
        validate_crawl_url("javascript:alert(1)")


def test_file_scheme_blocked():
    with pytest.raises(ValueError, match="http or https"):
        validate_crawl_url("file:///etc/passwd")


def test_ftp_scheme_blocked():
    with pytest.raises(ValueError, match="http or https"):
        validate_crawl_url("ftp://example.com/file")


def test_loopback_ipv4_blocked():
    with pytest.raises(ValueError, match="blocked address"):
        validate_crawl_url("http://127.0.0.1/admin")


def test_loopback_localhost_blocked():
    with pytest.raises(ValueError, match="blocked address"):
        validate_crawl_url("http://localhost/internal")


def test_rfc1918_10_blocked():
    with pytest.raises(ValueError, match="blocked address"):
        validate_crawl_url("http://10.0.0.1/secret")


def test_rfc1918_192168_blocked():
    with pytest.raises(ValueError, match="blocked address"):
        validate_crawl_url("http://192.168.1.1/router")


def test_rfc1918_172_blocked():
    with pytest.raises(ValueError, match="blocked address"):
        validate_crawl_url("http://172.16.0.1/service")


def test_cloud_metadata_endpoint_blocked():
    """169.254.169.254 is the AWS/GCP/Azure instance metadata endpoint."""
    with pytest.raises(ValueError, match="blocked address"):
        validate_crawl_url("http://169.254.169.254/latest/meta-data/")


def test_no_hostname_blocked():
    with pytest.raises(ValueError, match="no hostname"):
        validate_crawl_url("https:///path")


# --------------------------------------------------------------------------- #
# safe_href — javascript: URI XSS guard
# --------------------------------------------------------------------------- #

def test_safe_href_http():
    assert safe_href("http://example.com") == "http://example.com"


def test_safe_href_https():
    assert safe_href("https://biltiq.ai") == "https://biltiq.ai"


def test_safe_href_javascript_returns_none():
    assert safe_href("javascript:alert(document.cookie)") is None


def test_safe_href_data_uri_returns_none():
    assert safe_href("data:text/html,<script>alert(1)</script>") is None


def test_safe_href_empty_returns_none():
    assert safe_href("") is None


def test_safe_href_vbscript_returns_none():
    assert safe_href("vbscript:msgbox(1)") is None
