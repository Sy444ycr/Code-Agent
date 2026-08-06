def test_package_exports_version() -> None:
    import code_agent

    assert isinstance(code_agent.__version__, str)
    assert code_agent.__version__
