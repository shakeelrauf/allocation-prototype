import pytest

import llm_explain


@pytest.fixture(autouse=True)
def _reset_llm_auto_probe_between_tests():
    llm_explain._reset_llm_auto_probe()
    yield
    llm_explain._reset_llm_auto_probe()
