"""Pick the attention source from the command line (`--attention off|keyboard|random|bci`)."""

from .base import AttentionSource
from .focus_index import FocusConfig
from .sim_sources import KeyboardAttention, NullAttention, RandomAttention

MODES = ("off", "keyboard", "random", "bci")


def _print_flush(text: str) -> None:
    print(text, flush=True)


def make_attention_source(
    mode: str = "off", config: FocusConfig | None = None, log: bool = True
) -> AttentionSource:
    if mode == "bci":
        from .bci_source import BciAttention

        source = BciAttention(config=config)
    elif mode == "random":
        source = RandomAttention()
    elif mode == "keyboard":
        import pygame

        def direction() -> int:
            keys = pygame.key.get_pressed()
            return int(keys[pygame.K_UP]) - int(keys[pygame.K_DOWN])

        source = KeyboardAttention(direction)
    else:
        return NullAttention()
    source.log = _print_flush if log else None
    return source
