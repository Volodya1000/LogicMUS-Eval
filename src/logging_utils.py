import logging

import litellm  # type: ignore


def configure_logging() -> None:
    """Configure global logging and suppress third-party noise."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    for logger_name in ("litellm", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    litellm.suppress_debug_info = True
    litellm.set_verbose = False
