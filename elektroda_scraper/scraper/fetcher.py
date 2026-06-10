from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

PAGE_READY_SELECTOR = "article.table-row"
SUMMARY_SELECTOR = "#topic-summary"
TIMEOUT = 15
SUMMARY_EXTRA_WAIT = 15


class Fetcher:
    def __init__(self, timeout: float = TIMEOUT) -> None:
        self.timeout = timeout
        self.driver = webdriver.Chrome()

    def get(self, url: str, ready_selector: str = PAGE_READY_SELECTOR) -> webdriver.Chrome:
        self.driver.get(url)
        try:
            button = self.driver.find_element(By.CLASS_NAME, "fc-button-label")
            button.click()
        except Exception:
            pass
        WebDriverWait(self.driver, self.timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ready_selector))
        )
        if ready_selector == PAGE_READY_SELECTOR:
            try:
                WebDriverWait(self.driver, SUMMARY_EXTRA_WAIT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, SUMMARY_SELECTOR))
                )
            except TimeoutException:
                pass
        return self.driver

    def close(self) -> None:
        self.driver.quit()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
