import time
from workers.common.logging import get_logger

log = get_logger('availability')

if __name__ == '__main__':
    log.info('availability worker started')
    while True:
        log.info('availability batch: size=10 window=5 pause=2s')
        time.sleep(2)
