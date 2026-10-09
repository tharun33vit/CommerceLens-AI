"""
Smoke test suite for repository scaffolding and structural integrity.
These tests verify that the project structure, configuration files,
core modules, and environment are valid without requiring external services
or large datasets.
"""

import sys
from pathlib import Path
import pytest


@pytest.mark.smoke
def test_python_version_supported():
    """Verify that Python runtime is >= 3.11 and < 3.13 (or compatible)."""
    assert sys.version_info >= (3, 11), f"Python 3.11+ is required, found {sys.version}"


@pytest.mark.smoke
def test_package_import_and_metadata():
    """Verify that the commercelens package can be imported and has version metadata."""
    # Ensure src is on sys.path if not installed in editable mode yet
    src_dir = Path(__file__).resolve().parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    import commercelens
    assert hasattr(commercelens, "__version__")
    assert commercelens.__version__ == "0.1.0"


@pytest.mark.smoke
def test_submodules_exist():
    """Verify that all core architectural submodules can be imported."""
    src_dir = Path(__file__).resolve().parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    import commercelens.data
    import commercelens.analytics
    import commercelens.ml
    import commercelens.llm
    import commercelens.app

    assert commercelens.data is not None
    assert commercelens.analytics is not None
    assert commercelens.ml is not None
    assert commercelens.llm is not None
    assert commercelens.app is not None


@pytest.mark.smoke
def test_directory_structure_exists():
    """Verify that essential workspace directories exist."""
    repo_root = Path(__file__).resolve().parent.parent

    expected_dirs = [
        repo_root / "data" / "raw",
        repo_root / "data" / "processed",
        repo_root / "notebooks",
        repo_root / "src" / "commercelens",
        repo_root / "sql" / "schema",
        repo_root / "sql" / "analysis",
        repo_root / "sql" / "views",
        repo_root / "dashboards" / "powerbi",
        repo_root / "docs",
        repo_root / "scripts",
        repo_root / "tests",
        repo_root / "reports",
    ]

    for d in expected_dirs:
        assert d.exists(), f"Expected directory does not exist: {d}"
        assert d.is_dir(), f"Expected path to be a directory: {d}"


@pytest.mark.smoke
def test_core_configuration_files_exist():
    """Verify that essential root configuration and governance files exist."""
    repo_root = Path(__file__).resolve().parent.parent

    expected_files = [
        repo_root / "AGENTS.md",
        repo_root / "README.md",
        repo_root / ".gitignore",
        repo_root / ".env.example",
        repo_root / "pyproject.toml",
    ]

    for f in expected_files:
        assert f.exists(), f"Expected file does not exist: {f}"
        assert f.stat().st_size > 0, f"Expected non-empty file: {f}"


@pytest.mark.smoke
def test_docs_exist():
    """Verify that the required Phase 0 documentation artifacts exist."""
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"

    expected_docs = [
        docs_dir / "PROJECT_PLAN.md",
        docs_dir / "DATA_DICTIONARY.md",
        docs_dir / "METRICS.md",
        docs_dir / "ARCHITECTURE.md",
        docs_dir / "POWERBI_DASHBOARD_SPEC.md",
    ]

    for doc in expected_docs:
        assert doc.exists(), f"Expected documentation file does not exist: {doc}"
        assert doc.stat().st_size > 0, f"Expected non-empty doc file: {doc}"
