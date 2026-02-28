"""engine — core scraping orchestration, strategies, and health monitoring."""
from .health import HealthMonitor  # noqa: F401
from .errors import ScraperSignal, ScraperError  # noqa: F401
from .passive_tap import PassiveTap, WaitResult  # noqa: F401
from .failure_bundle import FailureBundle, BundleVerbosity, capture_failure_bundle, save_failure_bundle  # noqa: F401
from .orchestrator import fetch_posts  # noqa: F401
