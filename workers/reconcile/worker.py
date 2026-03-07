import time
from workers.common.logging import get_logger

log = get_logger('reconcile')

if __name__ == '__main__':
    log.info('reconcile worker started')
    while True:
        log.info('country accounts reconcile pass')
        time.sleep(120)
