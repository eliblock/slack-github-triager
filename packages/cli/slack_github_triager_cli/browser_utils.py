import time
from urllib.parse import urlparse

from selenium import webdriver


def fetch_d_cookie(subdomain: str) -> str:
    """
    Fetch the Slack 'd' cookie using browser automation.

    This function opens a Chrome browser, navigates to the Slack workspace,
    waits for authentication, and extracts the session cookie.
    """
    driver = webdriver.Chrome()
    driver.get(f"https://{subdomain}.slack.com")

    while urlparse(driver.current_url).netloc != "app.slack.com":
        time.sleep(0.1)

    cookies = driver.get_cookies()
    d_cookie = next(
        cookie["value"]
        for cookie in cookies
        if cookie["domain"] == ".slack.com" and cookie["name"] == "d"
    )
    driver.quit()

    return d_cookie
