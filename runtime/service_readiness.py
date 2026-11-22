"""Bounded startup retries for dependencies that may start after Docker resumes."""
import time
from urllib.error import HTTPError, URLError

from config import spark_conf


def spark_conf_when_catalog_ready(timeout=300, interval=2, loader=spark_conf):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return loader()
        except HTTPError as error:
            if error.code < 500 and error.code != 429:
                raise
            last_error = error
        except (URLError, TimeoutError, ConnectionError) as error:
            last_error = error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Unity Catalog did not become available during Spark SQL startup') from last_error
        print('Waiting for Unity Catalog before starting Spark SQL...', flush=True)
        time.sleep(min(interval, remaining))
