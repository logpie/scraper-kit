"""User-Agent detection and construction."""


def get_chromium_version(playwright) -> str:
    """Launch a throwaway browser to detect the Chromium version string.

    No internal caching — caller is responsible for caching the result.
    """
    browser = playwright.chromium.launch(headless=True)
    version = browser.version
    browser.close()
    return version


def build_user_agent(chrome_version: str, template: str = "") -> str:
    """Build a User-Agent string for the given Chrome version.

    If *template* is empty, uses a standard macOS Chrome UA template.
    """
    if not template:
        template = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
        )
    return template.format(version=chrome_version)
