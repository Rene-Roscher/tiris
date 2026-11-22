import os

import pytest

from tiris.live import try_lock

URL = os.environ.get("TIRIS_TEST_DATABASE_URL")


@pytest.mark.skipif(not URL, reason="needs TIRIS_TEST_DATABASE_URL")
def test_second_poller_does_not_get_the_lock():
    first = try_lock(URL)
    assert first is not None
    try:
        assert try_lock(URL) is None
    finally:
        first.close()
    again = try_lock(URL)       # released with the connection
    assert again is not None
    again.close()
