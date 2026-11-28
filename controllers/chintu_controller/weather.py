"""Live & simulated weather integration for Chintu by Sarworks.

Uses Open-Meteo (no API key required) for live weather lookups and provides
deterministic simulated weather presets for offline Playground demos & tests.
"""

from dataclasses import dataclass
import json
import threading
import time
from typing import Callable, Dict, Optional, Tuple
import urllib.parse
import urllib.request


WEATHER_CONDITIONS: Tuple[str, ...] = (
    "sunny",
    "cloudy",
    "rainy",
    "storm",
    "snowy",
    "windy",
    "starry",
)

WEATHER_CONDITION_SET = frozenset(WEATHER_CONDITIONS)

_DEFAULT_PRESETS: Dict[str, Tuple[float, float, int, bool, str]] = {
    # condition: (temp_c, wind_kmh, wmo_code, is_day, description)
    "sunny": (27.0, 9.0, 0, True, "Clear golden sunshine"),
    "cloudy": (20.0, 14.0, 3, True, "Soft drifting overcast"),
    "rainy": (17.0, 18.0, 63, True, "Cozy steady rain"),
    "storm": (16.0, 38.0, 95, True, "Thunder & lightning"),
    "snowy": (-3.0, 12.0, 73, True, "Drifting snowflakes"),
    "windy": (14.0, 44.0, 2, True, "Gusty swirling breeze"),
    "starry": (12.0, 6.0, 0, False, "Clear starry night"),
}


@dataclass
class WeatherSnapshot:
    """Normalized weather snapshot rendered by Chintu's face & Playground UI."""

    condition: str
    temp_c: float
    apparent_temp_c: float
    wind_kmh: float
    weather_code: int
    is_day: bool
    city: str
    description: str
    source: str = "simulated"  # "live" | "simulated"
    fetched_at_s: float = 0.0
    error: Optional[str] = None

    def format_temp(self, unit: str = "C") -> str:
        u = str(unit).upper().strip()
        if u == "F":
            val = round(self.temp_c * 9.0 / 5.0 + 32.0)
            return f"{val}F"
        val = round(self.temp_c)
        return f"{val}C"

    def to_dict(self, unit: str = "C") -> Dict[str, object]:
        return {
            "condition": self.condition,
            "temp_c": round(self.temp_c, 1),
            "temp_f": round(self.temp_c * 9.0 / 5.0 + 32.0, 1),
            "apparent_temp_c": round(self.apparent_temp_c, 1),
            "wind_kmh": round(self.wind_kmh, 1),
            "weather_code": self.weather_code,
            "is_day": self.is_day,
            "city": self.city,
            "description": self.description,
            "source": self.source,
            "temp_label": self.format_temp(unit),
            "error": self.error,
        }


def normalize_condition(condition: str) -> str:
    c = str(condition or "").lower().strip()
    aliases = {
        "clear": "sunny",
        "sun": "sunny",
        "hot": "sunny",
        "clouds": "cloudy",
        "overcast": "cloudy",
        "fog": "cloudy",
        "mist": "cloudy",
        "rain": "rainy",
        "drizzle": "rainy",
        "shower": "rainy",
        "showers": "rainy",
        "thunderstorm": "storm",
        "thunder": "storm",
        "lightning": "storm",
        "stormy": "storm",
        "snow": "snowy",
        "blizzard": "snowy",
        "sleet": "snowy",
        "wind": "windy",
        "breezy": "windy",
        "gusty": "windy",
        "night": "starry",
        "stars": "starry",
        "moon": "starry",
        "clear_night": "starry",
    }
    c = aliases.get(c, c)
    if c not in WEATHER_CONDITION_SET:
        raise ValueError(f"Unknown weather condition {condition!r}; expected one of {WEATHER_CONDITIONS}")
    return c


def wmo_code_to_condition(weather_code: int, is_day: bool = True, wind_kmh: float = 0.0) -> Tuple[str, str]:
    """Maps WMO weather interpretation code + day/wind to Chintu's 7 creative conditions."""
    code = int(weather_code)
    if code >= 95:
        return "storm", "Thunderstorm"
    if (71 <= code <= 77) or code in (85, 86):
        return "snowy", "Snowfall"
    if (51 <= code <= 67) or (80 <= code <= 82):
        return "rainy", "Rain & showers"
    if float(wind_kmh) >= 30.0 and code in (0, 1, 2, 3):
        return "windy", "Gusty winds"
    if code in (2, 3, 45, 48):
        return "cloudy", "Cloudy skies"
    if code in (0, 1):
        return ("sunny", "Clear sunshine") if is_day else ("starry", "Clear starry night")
    return "cloudy", "Partly cloudy"


def default_simulated_weather(
    condition: str,
    city: str = "Playground",
    temp_c: Optional[float] = None,
    wind_kmh: Optional[float] = None,
) -> WeatherSnapshot:
    """Builds a deterministic simulated WeatherSnapshot for offline playground & tests."""
    cond = normalize_condition(condition)
    t_c, w_kmh, code, is_day, desc = _DEFAULT_PRESETS[cond]
    eff_temp = t_c if temp_c is None else float(temp_c)
    eff_wind = w_kmh if wind_kmh is None else float(wind_kmh)
    return WeatherSnapshot(
        condition=cond,
        temp_c=eff_temp,
        apparent_temp_c=eff_temp - (2.0 if eff_wind > 25.0 else 0.0),
        wind_kmh=eff_wind,
        weather_code=code,
        is_day=is_day,
        city=str(city or "Playground"),
        description=desc,
        source="simulated",
        fetched_at_s=time.time(),
    )


def _default_json_get(url: str, timeout_s: float) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ChintuBySarworks/1.0 (+local-playground)"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_live_weather(
    city: str = "New York",
    json_getter: Optional[Callable[[str, float], dict]] = None,
    timeout_s: float = 4.0,
) -> WeatherSnapshot:
    """Fetches real-time weather from Open-Meteo (geocoding + current forecast, zero API key)."""
    getter = json_getter or _default_json_get
    query = str(city or "New York").strip() or "New York"
    geo_url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode({"name": query, "count": 1, "language": "en", "format": "json"})
    )
    geo_data = getter(geo_url, timeout_s)
    results = geo_data.get("results") or []
    if not results:
        raise ValueError(f"Could not find location {query!r}")
    place = results[0]
    lat = float(place["latitude"])
    lon = float(place["longitude"])
    place_name = str(place.get("name") or query)
    admin = place.get("country_code") or place.get("country") or ""
    display_city = f"{place_name}, {admin}" if admin else place_name

    wx_url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,is_day,weather_code,wind_speed_10m",
            "timezone": "auto",
        })
    )
    wx_data = getter(wx_url, timeout_s)
    cur = wx_data.get("current") or {}
    temp_c = float(cur.get("temperature_2m", 20.0))
    app_c = float(cur.get("apparent_temperature", temp_c))
    is_day = bool(int(cur.get("is_day", 1)))
    code = int(cur.get("weather_code", 0))
    wind_kmh = float(cur.get("wind_speed_10m", 0.0))
    cond, desc = wmo_code_to_condition(code, is_day=is_day, wind_kmh=wind_kmh)

    return WeatherSnapshot(
        condition=cond,
        temp_c=temp_c,
        apparent_temp_c=app_c,
        wind_kmh=wind_kmh,
        weather_code=code,
        is_day=is_day,
        city=display_city,
        description=desc,
        source="live",
        fetched_at_s=time.time(),
    )


class WeatherService:
    """Thread-safe non-blocking weather fetcher for Chintu's 50 Hz control loop."""

    def __init__(
        self,
        json_getter: Optional[Callable[[str, float], dict]] = None,
        timeout_s: float = 4.0,
    ) -> None:
        self._json_getter = json_getter
        self._timeout_s = float(timeout_s)
        self._lock = threading.Lock()
        self._pending_result: Optional[WeatherSnapshot] = None
        self._pending_error: Optional[str] = None
        self._in_flight: bool = False
        self.last_city: str = "New York"

    @property
    def is_fetching(self) -> bool:
        with self._lock:
            return self._in_flight

    def request_live_weather(self, city: Optional[str] = None) -> None:
        target_city = str(city or self.last_city or "New York").strip() or "New York"
        with self._lock:
            self.last_city = target_city
            self._in_flight = True
            self._pending_error = None

        def _worker() -> None:
            try:
                snap = fetch_live_weather(
                    city=target_city,
                    json_getter=self._json_getter,
                    timeout_s=self._timeout_s,
                )
                with self._lock:
                    self._pending_result = snap
                    self._pending_error = None
                    self._in_flight = False
            except Exception as exc:
                with self._lock:
                    self._pending_error = str(exc)
                    self._in_flight = False

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def poll_result(self) -> Tuple[Optional[WeatherSnapshot], Optional[str]]:
        """Returns (snapshot, error) if a background fetch finished since last poll."""
        with self._lock:
            snap = self._pending_result
            err = self._pending_error
            self._pending_result = None
            self._pending_error = None
            return snap, err
