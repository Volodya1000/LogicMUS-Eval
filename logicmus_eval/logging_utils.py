import logging


def configure_logging() -> None:
    """Configure global logging and suppress third-party noise."""
    import litellm  # pylint: disable=import-outside-toplevel

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    for logger_name in ("litellm", "LiteLLM", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    litellm.suppress_debug_info = True
