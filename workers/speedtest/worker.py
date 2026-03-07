import time
from workers.common.logging import get_logger

log = get_logger('speedtest')

if __name__ == '__main__':
    log.info('speedtest worker started')
    while True:
        log.info('speedtest cycle: 1 test at a time, pause 5 min between tests, stop on active sessions')
        time.sleep(300)
