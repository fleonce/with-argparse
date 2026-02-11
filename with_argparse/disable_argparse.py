from .impl import is_enabled, set_config, set_enabled


class no_argparse:  # noqa
    def __init__(self):
        self.previous_state = None

    def __enter__(self):
        self.previous_state = is_enabled()
        set_enabled(False)

    def __exit__(self, exc_type, exc_val, exc_tb):
        set_enabled(self.previous_state)
