import time
from workers.common.logging import get_logger

log = get_logger('aggregate')

if __name__ == '__main__':
    log.info('aggregate worker started')
    while True:
        log.info('aggregate recompute: stability, score, quarantine, rollups')
        time.sleep(30)
