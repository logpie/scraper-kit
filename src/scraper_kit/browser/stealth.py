"""Fingerprint-evasion shims for headless Chromium/Chrome.

All parameters (hardware specs, screen dimensions, platform strings) are
configurable so the same toolkit works across different scraping projects.
"""
import json
import logging
import os

log = logging.getLogger(__name__)

# Cache keyed by absolute path — supports multiple stealth JS files.
_stealth_js_cache: dict[str, str] = {}


def _load_stealth_js(path: str) -> str:
    """Load a stealth JS file from disk, with caching.

    Returns ``""`` if *path* is empty/falsy or does not point to a file.
    """
    if not path:
        return ""
    abs_path = os.path.abspath(path)
    if abs_path in _stealth_js_cache:
        return _stealth_js_cache[abs_path]
    if not os.path.isfile(abs_path):
        _stealth_js_cache[abs_path] = ""
        return ""
    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()
    _stealth_js_cache[abs_path] = content
    return content


def build_stealth_shim(
    chrome_version: str,
    *,
    hardware_concurrency: int = 10,
    device_memory: int = 16,
    platform: str = "macOS",
    platform_version: str = "15.3.0",
    architecture: str = "arm",
    screen_width: int = 1728,
    screen_height: int = 1117,
    screen_avail_height: int = 1079,
    color_depth: int = 30,
    webgl_vendor: str = "Google Inc. (Apple)",
    webgl_renderer: str = "ANGLE (Apple, ANGLE Metal Renderer: Apple M4, Unspecified Version)",
) -> str:
    """Build a JS shim that fixes fingerprint leaks stealth.min.js misses.

    All hardware/display values are parameterized so the shim can be tuned
    for different machines and platforms.
    """
    major = chrome_version.split(".")[0]
    grease_brand = "Not/A)Brand"
    major_js = json.dumps(major)
    chrome_version_js = json.dumps(chrome_version)
    grease_brand_js = json.dumps(grease_brand)
    platform_js = json.dumps(platform)
    platform_version_js = json.dumps(platform_version)
    architecture_js = json.dumps(architecture)
    webgl_vendor_js = json.dumps(webgl_vendor)
    webgl_renderer_js = json.dumps(webgl_renderer)
    return f"""
    (() => {{
        // -- navigator.userAgentData --
        const brands = [
            {{ brand: "Chromium", version: {major_js} }},
            {{ brand: "Google Chrome", version: {major_js} }},
            {{ brand: {grease_brand_js}, version: "99" }},
        ];
        const fullBrands = [
            {{ brand: "Chromium", version: {chrome_version_js} }},
            {{ brand: "Google Chrome", version: {chrome_version_js} }},
            {{ brand: {grease_brand_js}, version: "99.0.0.0" }},
        ];
        const uaData = {{
            brands: brands,
            mobile: false,
            platform: {platform_js},
            getHighEntropyValues: function(hints) {{
                return Promise.resolve({{
                    brands: fullBrands,
                    mobile: false,
                    platform: {platform_js},
                    platformVersion: {platform_version_js},
                    architecture: {architecture_js},
                    model: "",
                    uaFullVersion: {chrome_version_js},
                    fullVersionList: fullBrands,
                }});
            }},
            toJSON: function() {{
                return {{ brands: brands, mobile: false, platform: {platform_js} }};
            }},
        }};
        Object.defineProperty(navigator, 'userAgentData', {{
            get: () => uaData, configurable: true,
        }});

        // -- navigator.languages (Chinese user on Chinese platform) --
        Object.defineProperty(navigator, 'languages', {{
            get: () => ["zh-CN", "zh", "en-US", "en"], configurable: true,
        }});
        Object.defineProperty(navigator, 'language', {{
            get: () => "zh-CN", configurable: true,
        }});

        // -- navigator.hardwareConcurrency --
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {hardware_concurrency}, configurable: true,
        }});

        // -- navigator.vendor (should be "Google Inc." for Chrome) --
        Object.defineProperty(navigator, 'vendor', {{
            get: () => "Google Inc.", configurable: true,
        }});

        // -- navigator.maxTouchPoints (0 for desktop, no touch screen) --
        Object.defineProperty(navigator, 'maxTouchPoints', {{
            get: () => 0, configurable: true,
        }});

        // -- window outer dimensions (outer === inner is headless tell) --
        Object.defineProperty(window, 'outerHeight', {{
            get: () => window.innerHeight + 38, configurable: true,
        }});
        Object.defineProperty(window, 'outerWidth', {{
            get: () => window.innerWidth, configurable: true,
        }});

        // -- WebGL renderer --
        const _origGetParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            if (param === 0x9245) return {webgl_vendor_js};
            if (param === 0x9246) return {webgl_renderer_js};
            return _origGetParam.call(this, param);
        }};
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const _origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {{
                if (param === 0x9245) return {webgl_vendor_js};
                if (param === 0x9246) return {webgl_renderer_js};
                return _origGetParam2.call(this, param);
            }};
        }}

        // -- navigator.permissions (headless inconsistency fix) --
        if (navigator.permissions) {{
            const _origQuery = navigator.permissions.query.bind(navigator.permissions);
            navigator.permissions.query = function(desc) {{
                if (desc.name === 'notifications') {{
                    return Promise.resolve({{
                        state: Notification.permission === 'default'
                            ? 'prompt' : Notification.permission,
                        onchange: null,
                    }});
                }}
                return _origQuery(desc);
            }};
        }}

        // -- navigator.deviceMemory --
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {device_memory}, configurable: true,
        }});

        // -- navigator.connection (missing/empty in headless) --
        if (!navigator.connection) {{
            Object.defineProperty(navigator, 'connection', {{
                get: () => ({{
                    effectiveType: "4g",
                    rtt: 50,
                    downlink: 10,
                    saveData: false,
                }}),
                configurable: true,
            }});
        }}

        // -- window.screenX / screenY --
        Object.defineProperty(window, 'screenX', {{
            get: () => 120, configurable: true,
        }});
        Object.defineProperty(window, 'screenY', {{
            get: () => 38, configurable: true,
        }});

        // -- screen.* properties --
        Object.defineProperty(screen, 'width', {{
            get: () => {screen_width}, configurable: true,
        }});
        Object.defineProperty(screen, 'height', {{
            get: () => {screen_height}, configurable: true,
        }});
        Object.defineProperty(screen, 'availWidth', {{
            get: () => {screen_width}, configurable: true,
        }});
        Object.defineProperty(screen, 'availHeight', {{
            get: () => {screen_avail_height}, configurable: true,
        }});
        Object.defineProperty(screen, 'colorDepth', {{
            get: () => {color_depth}, configurable: true,
        }});
        Object.defineProperty(screen, 'pixelDepth', {{
            get: () => {color_depth}, configurable: true,
        }});

        // -- Error.stack cleanup (remove UtilityScript artifacts from Playwright) --
        const _origPrepareStackTrace = Error.prepareStackTrace;
        Error.prepareStackTrace = function(error, stack) {{
            if (_origPrepareStackTrace) {{
                return _origPrepareStackTrace(error, stack);
            }}
            return error.toString() + "\\n" + stack.map(function(f) {{
                return "    at " + f.toString();
            }}).filter(function(line) {{
                return line.indexOf("UtilityScript") === -1;
            }}).join("\\n");
        }};
    }})();
    """


def inject_stealth(
    page,
    chrome_version: str,
    stealth_js_path: str = "",
    **shim_kwargs,
) -> None:
    """Inject stealth scripts into the current page via ``evaluate()``.

    *stealth_js_path* is an optional path to a ``stealth.min.js`` file.
    Extra keyword arguments are forwarded to :func:`build_stealth_shim`.
    """
    stealth_js = _load_stealth_js(stealth_js_path)
    try:
        if stealth_js:
            page.evaluate(stealth_js)
        page.evaluate(build_stealth_shim(chrome_version, **shim_kwargs))
    except Exception:
        pass  # page may have navigated away


def setup_cdp_stealth(
    page,
    context,
    chrome_version: str,
    stealth_js_path: str = "",
    **shim_kwargs,
):
    """Install stealth scripts via CDP to run BEFORE any page JS.

    Uses ``Page.addScriptToEvaluateOnNewDocument`` directly.  Returns the
    CDP session (must stay alive — detaching removes registered scripts),
    or ``None`` on failure.
    """
    stealth_js = _load_stealth_js(stealth_js_path)

    parts: list[str] = []
    if stealth_js:
        parts.append(stealth_js)
    parts.append(build_stealth_shim(chrome_version, **shim_kwargs))
    source = "\n".join(parts)

    try:
        cdp = context.new_cdp_session(page)
        cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": source})
        log.info("CDP stealth injection installed (pre-navigation)")
        return cdp
    except Exception as e:
        log.warning("CDP stealth injection failed (%s); caller should fall back to evaluate()", e)
        return None
