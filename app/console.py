from __future__ import annotations

import logging
import signal
import threading

from app.config import get_settings
from app.main import configure_logging
from app.models import TranscriptEvent
from app.services.pipeline import Pipeline


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    pipeline = Pipeline(settings)
    stopped = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    pipeline.start()
    logging.getLogger(__name__).info("console transcription started (Ctrl+C to stop)")
    try:
        while not stopped.is_set():
            event = pipeline.next_broadcast(timeout=0.5)
            if isinstance(event, TranscriptEvent):
                print(
                    f"[{event.started_at:%H:%M:%S}] {event.text}",
                    flush=True,
                )
    finally:
        pipeline.stop()


if __name__ == "__main__":
    main()
