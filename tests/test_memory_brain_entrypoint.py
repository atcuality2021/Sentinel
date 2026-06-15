# tests/test_memory_brain_entrypoint.py
def test_worker_module_is_importable():
    import sentinel.worker as w
    assert hasattr(w, "main")
