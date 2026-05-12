from cdmsparkevents.selftest import startup

def test_noop():
    assert startup.run_iceberg_startup_test
