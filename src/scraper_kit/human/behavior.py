"""Human-like behavioral patterns for browser automation.

Replaces mechanical bot patterns (uniform timing, fixed scrolls, no mouse
movement) with statistically natural human behavior to defeat anti-bot
fingerprinting.
"""

import logging
import math
import random
import time

log = logging.getLogger(__name__)

# Track last known mouse position for Bezier curve start points.
# Initialized to viewport center; updated by bezier_move / human_click.
_last_mouse: dict[str, float] = {"x": 640.0, "y": 360.0}


def _safe_float(val, default: float) -> float:
    try:
        f = float(val)
        if math.isfinite(f):
            return f
    except (TypeError, ValueError):
        pass
    return default


def human_sleep(low: float, high: float, sigma: float = 0.3) -> None:
    """Sleep for a log-normal distributed duration between low and high.

    Log-normal matches human reaction times: mostly quick responses with
    occasional longer pauses. 8% chance of a "distraction" adding 2-6s.

    sigma controls variance — higher = more spread:
      0.2 = tight (page load waits)
      0.3 = moderate (default, UI interactions)
      0.5 = wide (reading/browsing pauses)
    """
    low = _safe_float(low, 0.05)
    high = _safe_float(high, low)
    sigma = max(0.01, _safe_float(sigma, 0.3))
    if high < low:
        low, high = high, low
    low = max(low, 0.001)
    high = max(high, low)
    # Log-normal centered at midpoint of [low, high]
    mid = max((low + high) / 2, 0.001)
    mu = math.log(mid)
    delay = random.lognormvariate(mu, sigma)
    # Clamp to reasonable range (0.5x low to 2x high)
    delay = max(low * 0.5, min(delay, high * 2))
    # Occasional distraction pause
    if random.random() < 0.08:
        delay += random.uniform(2, 6)
    time.sleep(delay)
    log.debug(f"    sleep {delay:.1f}s")


# ---------------------------------------------------------------------------
# Bezier curve mouse movement
# ---------------------------------------------------------------------------

def _cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Evaluate cubic Bezier at parameter t in [0, 1]."""
    u = 1 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def bezier_move(page, to_x: float, to_y: float) -> None:
    """Move mouse along a cubic Bezier curve from current position to target.

    Generates realistic trajectories with:
    - Two random control points creating a natural arc
    - Gaussian micro-jitter per point (simulates hand tremor)
    - Non-uniform timing: slow at start/end, fast in middle (Fitts' Law)
    """
    global _last_mouse
    if not page or not hasattr(page, "mouse"):
        return
    to_x = _safe_float(to_x, _last_mouse.get("x", 640.0))
    to_y = _safe_float(to_y, _last_mouse.get("y", 360.0))
    from_x, from_y = _last_mouse["x"], _last_mouse["y"]
    dx = to_x - from_x
    dy = to_y - from_y
    dist = math.hypot(dx, dy)

    # For very short moves, just go direct
    if dist < 10:
        page.mouse.move(to_x, to_y)
        _last_mouse["x"], _last_mouse["y"] = to_x, to_y
        return

    # Random control points — offset perpendicular to the direct path
    # to create a natural arc (humans don't move in straight lines)
    cp1_x = from_x + dx * random.uniform(0.2, 0.4) + random.uniform(-50, 50)
    cp1_y = from_y + dy * random.uniform(0.1, 0.3) + random.uniform(-30, 30)
    cp2_x = from_x + dx * random.uniform(0.6, 0.8) + random.uniform(-50, 50)
    cp2_y = from_y + dy * random.uniform(0.7, 0.9) + random.uniform(-30, 30)

    # More steps for longer distances (20-40 range)
    steps = max(20, min(40, int(dist / 15)))
    for i in range(steps + 1):
        t = i / steps
        x = _cubic_bezier(t, from_x, cp1_x, cp2_x, to_x)
        y = _cubic_bezier(t, from_y, cp1_y, cp2_y, to_y)
        # Gaussian micro-jitter (hand tremor) — decreases near target for
        # precision, matching human fine motor control
        tremor = max(0.3, 1.5 * (1 - t))
        x += random.gauss(0, tremor)
        y += random.gauss(0, tremor)
        page.mouse.move(x, y)
        # Non-uniform timing: slow-fast-slow (parabolic speed profile)
        # Matches Fitts' Law — decelerate approaching target
        speed = 4 * t * (1 - t)  # peaks at t=0.5, zero at endpoints
        delay = random.uniform(0.005, 0.018) / max(speed, 0.15)
        time.sleep(delay)

    _last_mouse["x"], _last_mouse["y"] = to_x, to_y


# ---------------------------------------------------------------------------
# Inertial scroll simulation
# ---------------------------------------------------------------------------

def inertial_wheel(page, total_distance: int) -> int:
    """Scroll via decelerating burst of small wheel events (trackpad inertia).

    Returns the actual total distance scrolled (may differ slightly from
    requested due to jitter).
    """
    if not page or not hasattr(page, "mouse"):
        return 0
    total_distance = int(_safe_float(total_distance, 0))
    if total_distance == 0:
        return 0
    sign = 1 if total_distance > 0 else -1
    remaining = abs(total_distance)
    scrolled = 0
    n_steps = random.randint(8, 15)

    for i in range(n_steps):
        if remaining <= 0:
            break
        # Exponential decay — most distance covered in early steps
        progress = i / n_steps
        fraction = random.uniform(0.08, 0.25) * (1 - progress)
        delta = int(remaining * fraction) + random.randint(-3, 3)
        delta = max(1, min(delta, remaining))
        if remaining > 8:
            delta = min(remaining, max(8, delta))
        page.mouse.wheel(0, sign * delta)
        remaining -= delta
        scrolled += delta
        # Inter-event gap — short and variable like real scroll events
        time.sleep(random.uniform(0.008, 0.035))

    # Final correction — dump remaining distance
    if remaining > 0:
        page.mouse.wheel(0, sign * remaining)
        scrolled += remaining
        time.sleep(random.uniform(0.01, 0.03))

    return sign * scrolled


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def human_scroll(page, distance: int) -> None:
    """Scroll with inertial simulation and Bezier mouse repositioning.

    - Moves mouse to random viewport position via Bezier curve
    - Scrolls via decelerating burst of wheel events (inertial simulation)
    - 15% chance of a small corrective scroll-up afterward
    """
    if not page or not hasattr(page, "mouse"):
        return
    distance = int(_safe_float(distance, 0))
    if distance == 0:
        return
    t0 = time.monotonic()
    # Move mouse to random viewport position via Bezier curve
    vs = page.viewport_size or {"width": 1920, "height": 1080}
    vw = max(100, int(_safe_float((vs or {}).get("width"), 1920)))
    vh = max(100, int(_safe_float((vs or {}).get("height"), 1080)))
    min_x, max_x = int(vw * 0.2), int(vw * 0.8)
    min_y, max_y = int(vh * 0.3), int(vh * 0.7)
    target_x = random.randint(min_x, max_x) if min_x <= max_x else vw // 2
    target_y = random.randint(min_y, max_y) if min_y <= max_y else vh // 2
    bezier_move(page, target_x, target_y)

    # Inertial scroll
    jittered = int(distance * random.uniform(0.8, 1.2))
    if jittered == 0:
        jittered = 1 if distance > 0 else -1
    actual = inertial_wheel(page, jittered)

    # Occasional corrective scroll-up
    corrected = False
    if random.random() < 0.15:
        time.sleep(random.uniform(0.2, 0.5))
        inertial_wheel(page, -random.randint(50, 150))
        corrected = True

    elapsed = time.monotonic() - t0
    log.debug(f"    scroll {actual}px ({elapsed:.1f}s){' +correction' if corrected else ''}")


def human_click(page, element) -> None:
    """Click an element via Bezier curve mouse movement with random offset.

    Moves the mouse along a natural arc to the element, applies a random
    offset from center, then clicks with a brief pre-click pause.
    """
    if not page or element is None:
        return
    t0 = time.monotonic()
    box = element.bounding_box()
    if not box:
        element.click()
        elapsed = time.monotonic() - t0
        log.debug(f"    click (no box, fallback) [{elapsed:.1f}s]")
        return
    # Random offset from center (within 30% of dimensions)
    bw = _safe_float(box.get("width"), 0.0)
    bh = _safe_float(box.get("height"), 0.0)
    if bw <= 0 or bh <= 0:
        element.click()
        elapsed = time.monotonic() - t0
        log.debug(f"    click (invalid box, fallback) [{elapsed:.1f}s]")
        return
    bx = _safe_float(box.get("x"), 0.0)
    by = _safe_float(box.get("y"), 0.0)
    offset_x = random.uniform(-0.3, 0.3) * bw
    offset_y = random.uniform(-0.3, 0.3) * bh
    target_x = bx + bw / 2 + offset_x
    target_y = by + bh / 2 + offset_y
    # Bezier curve movement to target
    bezier_move(page, target_x, target_y)
    # Brief pre-click pause (human reaction before committing to click)
    time.sleep(random.uniform(0.05, 0.15))
    page.mouse.click(target_x, target_y)
    elapsed = time.monotonic() - t0
    log.debug(f"    click ({target_x:.0f},{target_y:.0f}) bezier [{elapsed:.1f}s]")


def human_dismiss_modal(page) -> None:
    """Dismiss a modal overlay using a randomly chosen method.

    50% Escape key, 30% close button click, 20% backdrop click.
    Falls back to Escape if the chosen method fails.
    """
    t0 = time.monotonic()
    roll = random.random()
    method = "escape"
    if roll < 0.50:
        # Escape key
        page.keyboard.press("Escape")
        human_sleep(0.3, 0.8)
    elif roll < 0.80:
        # Try close button
        close_btn = page.query_selector(
            ".close-circle, .note-detail .close, [class*='close'] svg"
        )
        if close_btn:
            method = "close-btn"
            human_click(page, close_btn)
            human_sleep(0.3, 0.8)
        else:
            page.keyboard.press("Escape")
            human_sleep(0.3, 0.8)
    else:
        # Try clicking backdrop
        backdrop = page.query_selector(".mask-container, .note-detail-mask")
        if backdrop:
            method = "backdrop"
            human_click(page, backdrop)
            human_sleep(0.3, 0.8)
        else:
            page.keyboard.press("Escape")
            human_sleep(0.3, 0.8)
    elapsed = time.monotonic() - t0
    log.debug(f"    dismiss modal via {method} [{elapsed:.1f}s]")


def scroll_count() -> int:
    """Return a random scroll count (2-5) instead of fixed 3."""
    return random.randint(2, 5)
