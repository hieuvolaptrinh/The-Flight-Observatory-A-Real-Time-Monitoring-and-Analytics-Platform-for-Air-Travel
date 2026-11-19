"""AirLabs schedules + cached OpenWeather. No CSV or simulator fallback."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
import math
import re
from zoneinfo import ZoneInfo

import httpx

from app.live_store import LiveStore, quota_period

# HTTPX's INFO request log includes query strings containing provider keys.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class ProviderError(RuntimeError):
    """Only sanitized provider identifiers/codes may appear in this exception."""


@dataclass
class Account:
    name: str
    key: str = field(repr=False)
    airports: tuple[str, ...] = ()
    quota_group: str = "default"
    budget: int = 800
    reset_day: int = 1


def accounts_from_settings(settings):
    airports = tuple(code.strip().upper() for code in settings.airlabs_airports.split(",") if code.strip())
    secret = settings.airlabs_accounts.get_secret_value().strip()
    try:
        entries = json.loads(secret) if secret else [{
            "name": "default", "key": settings.airlabs_api_key.get_secret_value(),
            "airports": airports, "budget": settings.airlabs_monthly_budget,
            "reset_day": settings.airlabs_reset_day,
        }]
        result, assigned, groups, names = [], set(), {}, set()
        for entry in entries:
            name = entry["name"]
            group = entry.get("quota_group", name)
            codes = tuple(str(c).strip().upper() for c in entry.get("airports", airports))
            budget, day = int(entry.get("budget", 800)), int(entry.get("reset_day", 1))
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) or name in names:
                raise ValueError()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", group) or not 1 <= day <= 28 or budget < 1:
                raise ValueError()
            if len(codes) != len(set(codes)) or any(not re.fullmatch(r"[A-Z]{3}", c) or c in assigned for c in codes):
                raise ValueError()
            if group in groups and groups[group] != (budget, day):
                raise ValueError()
            groups[group] = (budget, day)
            names.add(name)
            assigned.update(codes)
            result.append(Account(name, str(entry["key"]).strip(), codes, group, budget, day))
        return result
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Invalid AIRLABS_ACCOUNTS: use unique account names/airports and consistent quota-group budgets/reset days") from None


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def timestamp(raw, prefix, airport):
    epoch = number(raw.get(prefix + "_ts"))
    if epoch is not None:
        return datetime.fromtimestamp(epoch, timezone.utc)
    if raw.get(prefix + "_utc"):
        return datetime.fromisoformat(raw[prefix + "_utc"]).replace(tzinfo=timezone.utc)
    if raw.get(prefix) and airport.get("timezone"):
        return datetime.fromisoformat(raw[prefix]).replace(tzinfo=ZoneInfo(airport["timezone"])).astimezone(timezone.utc)
    return None


def distance_miles(origin, dest):
    coords = [number(a.get(k)) for a in (origin, dest) for k in ("lat", "lng")]
    if any(v is None for v in coords):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, coords)
    term = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return round(3958.7613 * 2 * math.asin(min(1, math.sqrt(term))), 1)


def normalize_schedule(raw, origin, destination, fetched_at):
    """Map schedules without inventing observed outcomes or weather."""
    dep, arr = raw.get("dep_iata"), raw.get("arr_iata")
    carrier, flight = raw.get("airline_iata"), str(raw.get("flight_number") or "")
    if not all((dep, arr, carrier, flight, raw.get("dep_time"))) or not flight.isdigit():
        return None
    # Prefer the operating flight identity on a codeshare, when supplied.
    carrier = raw.get("cs_airline_iata") or carrier
    flight = str(raw.get("cs_flight_number") or flight)
    if not flight.isdigit():
        return None
    local_dep = datetime.fromisoformat(raw["dep_time"])
    local_arr = datetime.fromisoformat(raw["arr_time"]) if raw.get("arr_time") else None
    dep_utc, arr_utc = timestamp(raw, "dep_time", origin), timestamp(raw, "arr_time", destination)
    elapsed = (arr_utc-dep_utc).total_seconds()/60 if dep_utc and arr_utc else None
    if elapsed is not None and elapsed < 0:
        elapsed = None
    actual_delays = {}
    for side, airport, scheduled in (("dep", origin, dep_utc), ("arr", destination, arr_utc)):
        actual = timestamp(raw, side + "_actual", airport)
        actual_delays[side] = round((actual-scheduled).total_seconds()/60, 1) if actual and scheduled else None
    status = str(raw.get("status") or "unknown")
    if status in ("cancelled", "diverted"):
        delay, kind = None, "unknown"
    elif actual_delays["arr"] is not None or actual_delays["dep"] is not None:
        delay = actual_delays["arr"] if actual_delays["arr"] is not None else actual_delays["dep"]
        kind = "observed_arrival" if actual_delays["arr"] is not None else "observed_departure"
    else:
        estimates = [number(raw.get(k)) for k in ("arr_delayed", "dep_delayed")]
        delay = next((v for v in estimates if v is not None), None)
        kind = "estimated" if delay is not None else "unknown"
    key = f"airlabs:{local_dep.date()}:{carrier}:{flight}:{dep}:{arr}:{local_dep:%H%M}"
    return {
        "FLIGHT_KEY": key, "FL_DATE": local_dep.date().isoformat(), "DAY_OF_WEEK": local_dep.isoweekday(),
        "OP_UNIQUE_CARRIER": carrier, "OP_CARRIER_FL_NUM": flight, "ORIGIN": dep, "DEST": arr,
        "CRS_DEP_TIME": local_dep.strftime("%H:%M"), "CRS_ARR_TIME": local_arr.strftime("%H:%M") if local_arr else None,
        "DISTANCE": distance_miles(origin, destination), "CRS_ELAPSED_TIME": elapsed,
        "TAIL_NUM": raw.get("reg_number"), "DELAY_MINUTES": delay, "_live": True,
        "_details": {
            "source": "airlabs", "flight_status": status, "delay_kind": kind,
            "dep_delay_min": actual_delays["dep"], "arr_delay_min": actual_delays["arr"],
            "scheduled_dep_utc": dep_utc.isoformat() if dep_utc else None,
            "scheduled_arr_utc": arr_utc.isoformat() if arr_utc else None,
            "distance_source": "great_circle_estimate", "fetched_at": fetched_at, "raw": raw,
        },
    }


def normalize_weather(raw, fetched_at):
    main, wind = raw.get("main", {}), raw.get("wind", {})
    speed, gust, visibility = number(wind.get("speed")), number(wind.get("gust")), number(raw.get("visibility"))
    observed = number(raw.get("dt"))
    if observed is None:
        raise ProviderError("openweather: missing observation time")
    return {
        "observed_at": datetime.fromtimestamp(observed, timezone.utc).isoformat(), "fetched_at": fetched_at,
        "temperature_c": number(main.get("temp")), "pressure_hpa": number(main.get("pressure")),
        "wind_speed_kmh": round(speed*3.6, 2) if speed is not None else None,
        "wind_gust_kmh": round(gust*3.6, 2) if gust is not None else None,
        "visibility_km": visibility/1000 if visibility is not None else None,
        "precipitation_mm": (number(raw.get("rain", {}).get("1h")) or 0) + (number(raw.get("snow", {}).get("1h")) or 0),
        "precipitation_period_hours": 1, "source": "openweather", "raw": raw,
    }


class LiveProviders:
    def __init__(self, settings, repository, transport=None):
        self.settings, self.store = settings, LiveStore(repository)
        self.accounts = accounts_from_settings(settings)
        self.transport = transport
        self.last_status = {"state": "waiting", "warnings": []}

    async def request(self, client, provider, endpoint, params, group, budget, reset_day, credential):
        now = datetime.now(timezone.utc)
        credential_id = hashlib.sha256(credential.encode()).hexdigest()[:16]
        block_key = f"block:{provider}:{group}"
        blocked, _ = await asyncio.to_thread(self.store.cached, block_key)
        if blocked and blocked["until"] > now.timestamp() and (blocked.get("credential") in (None, credential_id)):
            raise ProviderError(f"{provider}: quota group temporarily paused")
        allowed = await asyncio.to_thread(self.store.reserve, f"{provider}:{group}", budget, reset_day)
        if not allowed:
            raise ProviderError(f"{provider}: configured request budget exhausted")
        code, payload = None, None
        try:
            response = await client.get(endpoint, params=params)
            if response.status_code >= 400:
                code = str(response.status_code)
            else:
                payload = response.json()
                if not isinstance(payload, dict):
                    code = "invalid_response"
                elif payload.get("error"):
                    code = str(payload["error"].get("code", "provider_error")) if isinstance(payload["error"], dict) else "provider_error"
        except (httpx.HTTPError, ValueError):
            code = "network_or_response_error"
        if code:
            # Never retain provider error messages or request URLs: they may echo credentials.
            known = {"401", "403", "429", "unknown_api_key", "expired_api_key", "minute_limit_exceeded", "hour_limit_exceeded", "month_limit_exceeded"}
            safe = code if code in known else "request_failed"
            seconds = 60 if code == "minute_limit_exceeded" else 3600
            credential_block = code in {"401", "403", "unknown_api_key", "expired_api_key"}
            if credential_block:
                seconds = 86400
            until = now + timedelta(seconds=seconds)
            if code == "month_limit_exceeded":
                period = datetime.fromisoformat(quota_period(now, reset_day)).replace(tzinfo=timezone.utc)
                until = (period.replace(day=28) + timedelta(days=4)).replace(day=reset_day)
            await asyncio.to_thread(self.store.cache, block_key, {"until": until.timestamp(), "credential": credential_id if credential_block else None})
            raise ProviderError(f"{provider}: {safe}")
        return payload

    async def airlabs(self, client, account, endpoint, params):
        payload = await self.request(client, "airlabs", f"https://airlabs.co/api/v9/{endpoint}",
            {**params, "api_key": account.key}, account.quota_group, account.budget, account.reset_day, account.key)
        if not isinstance(payload.get("response"), list):
            raise ProviderError("airlabs: response is not a list")
        return payload

    async def airport(self, client, account, code):
        key = f"airport:{code}"
        cached, epoch = await asyncio.to_thread(self.store.cached, key)
        if cached is not None and datetime.now(timezone.utc).timestamp()-epoch < 30*86400:
            return cached
        payload = await self.airlabs(client, account, "airports", {"iata_code": code})
        row = next((r for r in payload["response"] if r.get("iata_code") == code), {})
        await asyncio.to_thread(self.store.cache, key, row)
        return row

    async def weather(self, client, code, airport):
        if not self.settings.openweather_api_key.get_secret_value() or number(airport.get("lat")) is None or number(airport.get("lng")) is None:
            return
        key = f"weather:{code}"
        cached, epoch = await asyncio.to_thread(self.store.cached, key)
        if cached and datetime.now(timezone.utc).timestamp()-epoch < self.settings.weather_cache_seconds:
            return
        secret = self.settings.openweather_api_key.get_secret_value()
        raw = await self.request(client, "openweather", "https://api.openweathermap.org/data/2.5/weather",
            {"lat": airport["lat"], "lon": airport["lng"], "units": "metric", "appid": secret},
            "default", self.settings.openweather_monthly_budget, self.settings.openweather_reset_day, secret)
        normalized = normalize_weather(raw, datetime.now(timezone.utc).isoformat())
        await asyncio.to_thread(self.store.weather, code, normalized)
        await asyncio.to_thread(self.store.cache, key, normalized)

    async def fetch(self):
        fetched = datetime.now(timezone.utc).isoformat()
        rows, warnings, seen = [], [], set()
        pages = 0
        async with httpx.AsyncClient(timeout=20, transport=self.transport) as client:
            for account in self.accounts:
                if not account.key:
                    warnings.append(f"{account.name}: missing AirLabs key")
                    continue
                for code in account.airports:
                    # A failed airport must not prevent processing another account/airport.
                    try:
                        for page in range(self.settings.airlabs_max_pages):
                            payload = await self.airlabs(client, account, "schedules", {"dep_iata": code, "limit": 50, "offset": page*50})
                            pages += 1
                            for raw in payload["response"]:
                                if not isinstance(raw, dict) or raw.get("dep_iata") != code:
                                    continue
                                origin, destination = {}, {}
                                for airport_code in (code, raw.get("arr_iata")):
                                    if not airport_code:
                                        continue
                                    try:
                                        info = await self.airport(client, account, airport_code)
                                        if airport_code == code:
                                            origin = info
                                        else:
                                            destination = info
                                    except ProviderError as exc:
                                        warnings.append(str(exc))
                                try:
                                    record = normalize_schedule(raw, origin, destination, fetched)
                                except (ValueError, TypeError, KeyError, OverflowError):
                                    warnings.append("Skipped a flight with invalid schedule/timezone")
                                    continue
                                if record and record["FLIGHT_KEY"] not in seen:
                                    seen.add(record["FLIGHT_KEY"])
                                    rows.append(record)
                            more = payload.get("request", {}).get("has_more")
                            if more is None:
                                more = len(payload["response"]) == 50
                            if not more:
                                break
                            if page + 1 == self.settings.airlabs_max_pages:
                                warnings.append(f"{code}: page cap reached; coverage is partial")
                    except ProviderError as exc:
                        warnings.append(f"{account.name}/{code}: {exc}")
                    try:
                        airport, _ = await asyncio.to_thread(self.store.cached, f"airport:{code}")
                        await self.weather(client, code, airport or {})
                    except ProviderError as exc:
                        warnings.append(str(exc))
        if not self.settings.openweather_api_key.get_secret_value():
            warnings.append("OpenWeather key missing; real weather is unavailable")
        self.last_status = {"state": "fetched" if rows else "no_new_data", "checked_at": fetched,
            "received": len(rows), "schedule_requests_succeeded": pages, "warnings": sorted(set(warnings))}
        await asyncio.to_thread(self.store.cache, "ingestion_status", self.last_status)
        return {"source": "airlabs", "fetched_at": fetched, "data": rows}
