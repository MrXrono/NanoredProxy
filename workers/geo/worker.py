import time
from workers.common.logging import get_logger

log = get_logger('geo')

if __name__ == '__main__':
    log.info('geo worker started')
    while True:
        log.info('geo resolution pass for country_unknown proxies')
        time.sleep(60)
