from __future__ import annotations

import logging
import sys
from typing import Sequence

from .models import NotificationEvent

log = logging.getLogger(__name__)

DEFAULT_BACKENDS: list[str] = ["pygame", "simpleaudio", "bell"]


class AudioNotifier:
    def __init__(
        self,
        enabled: bool = True,
        volume: float = 0.7,
        backend_preference: Sequence[str] | None = None,
        sounds: dict[str, str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.volume = max(0.0, min(1.0, volume))
        self.backend_preference = list(backend_preference or DEFAULT_BACKENDS)
        self.sounds: dict[str, str] = sounds or {}

    def notify(self, event: NotificationEvent) -> None:
        if not self.enabled:
            return

        sound_path = self.sounds.get(event.event_type.value, "")
        if not sound_path:
            sound_path = self.sounds.get("default", "")

        if not sound_path:
            self._try_bell()
            return

        for backend in self.backend_preference:
            if backend == "pygame" and self._try_pygame(sound_path):
                return
            if backend == "simpleaudio" and self._try_simpleaudio(sound_path):
                return
            if backend == "bell":
                self._try_bell()
                return

    def _try_pygame(self, path: str) -> bool:
        try:
            import pygame.mixer  # type: ignore[import-untyped]

            if not pygame.mixer.get_init():
                pygame.mixer.init()

            sound = pygame.mixer.Sound(path)
            sound.set_volume(self.volume)
            sound.play()
            return True
        except (ImportError, FileNotFoundError, pygame.error):  # type: ignore[attr-defined]
            log.debug("pygame backend unavailable or failed for %s", path)
            return False
        except Exception:
            log.debug("Unexpected error in pygame backend", exc_info=True)
            return False

    def _try_simpleaudio(self, path: str) -> bool:
        try:
            import simpleaudio  # type: ignore[import-untyped]

            wave_obj = simpleaudio.WaveObject.from_wave_file(path)
            wave_obj.play()
            return True
        except (ImportError, FileNotFoundError):
            log.debug("simpleaudio backend unavailable or failed for %s", path)
            return False
        except Exception:
            log.debug("Unexpected error in simpleaudio backend", exc_info=True)
            return False

    def _try_bell(self) -> None:
        print("\a", end="", flush=True, file=sys.stdout)
