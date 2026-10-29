"""Run separately: python -m backend.worker"""
import logging
from .config import Settings
from .service import Service


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    service = Service(Settings())
    print('Ribbon worker ready (durable SQLite queue; Ctrl+C to stop)', flush=True)
    try:
        service.worker_loop()
    except KeyboardInterrupt:
        service.stop()


if __name__ == '__main__':
    main()
