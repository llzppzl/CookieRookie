"""agent/conftest.py - pytest configuration"""
import pytest


@pytest.fixture(autouse=True)
def allow_pytest_tmp_dirs(monkeypatch, tmp_path_factory):
    """Tests change files in pytest's temporary folders, which are outside the working directory
    that edit_file and write_file are limited to. Allow those folders too."""
    from agent import tools
    real_project_dirs = tools.project_dirs
    base = str(tmp_path_factory.getbasetemp())
    monkeypatch.setattr(tools, "project_dirs", lambda: real_project_dirs() + [base])


# Tell pytest not to collect test_run and test_generate from test_tools as tests
# These are utility functions, not test cases
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Remove test_run and test_generate from collection"""
    skip_names = {'test_run', 'test_generate'}
    for item in items:
        # Check if the item comes from test_tools.py and has these names
        if item.fspath and 'test_tools.py' in str(item.fspath):
            if item.name in skip_names:
                item.add_marker(pytest.mark.skip(reason="Not a test function"))
