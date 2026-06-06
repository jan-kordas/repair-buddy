import time

from selenium import webdriver

#Load delay
DEFAULT_DELAY = 2.5


class Fetcher:
    def __init__(self, delay: float = DEFAULT_DELAY) -> None:
        self.delay = delay
        self.driver = webdriver.Chrome()

    def get(self, url: str) -> webdriver.Chrome:
        self.driver.get(url)
        time.sleep(self.delay)
        return self.driver

    def close(self) -> None:
        self.driver.quit()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
