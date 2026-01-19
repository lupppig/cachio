from datetime import datetime, timezone
from typing import Dict, Any, Optional
from requests.structures import CaseInsensitiveDict
from .utils import check_date, to_date
from .error import DateDirectiveMissing

FRESH = 1
STALE = 0

def parse_cache_control(headers: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Parse Cache-Control header into a dictionary."""
    val = headers.get("cache-control") or headers.get("Cache-Control")
    cc: Dict[str, Optional[str]] = {}
    if not val:
        return cc
    
    split_cc = val.split(",")
    for part in split_cc:
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            cc[key.lower()] = value
        else:
            cc[part.lower()] = None
    return cc

def check_freshness(req_headers: Dict[str, Any], resp_headers: Dict[str, Any]) -> int:
    """Check if the cache response is fresh based on headers."""
    class HeaderWrapper:
        def __init__(self, h): self.headers = h
    
    req_cc = parse_cache_control(req_headers)
    resp_cc = parse_cache_control(resp_headers)

    if "no-cache" in req_cc:
        return 2
    if "no-cache" in resp_cc:
        return STALE
    if "only-if-cached" in req_cc:
        return FRESH

    try:
        date = check_date(HeaderWrapper(resp_headers)) # type: ignore
    except (DateDirectiveMissing, AttributeError):
        date = datetime.now(timezone.utc)
        
    now = datetime.now(timezone.utc)
    current_age = (now - date).total_seconds()

    resp_max_age = resp_cc.get("max-age")
    if resp_max_age is not None:
        try:
            if current_age <= int(resp_max_age):
                fresh = True
            else:
                fresh = False
        except ValueError:
            fresh = False
    elif resp_headers.get("expires") or resp_headers.get("Expires"):
        exp = resp_headers.get("expires") or resp_headers.get("Expires")
        expires_dt = to_date(exp)
        fresh = now <= expires_dt
    else:
        fresh = False

    max_stale = req_cc.get("max-stale")
    if not fresh and max_stale is not None:
        if max_stale is None or max_stale == "":
            fresh = True
        else:
            try:
                max_stale_sec = int(max_stale)
                if resp_max_age is not None:
                        if current_age - int(resp_max_age) <= max_stale_sec:
                            fresh = True
            except ValueError:
                pass

    min_fresh = req_cc.get("min-fresh")
    if fresh and min_fresh is not None:
        try:
            min_fresh_sec = int(min_fresh)
            if resp_max_age is not None:
                if int(resp_max_age) - current_age < min_fresh_sec:
                    fresh = False
        except ValueError:
            pass

    return FRESH if fresh else STALE

def check_stale_if_error(resp_headers: Dict[str, Any]) -> bool:
    """Check stale-if-error directive."""
    cc = parse_cache_control(resp_headers)
    stale_if_error = cc.get("stale-if-error")
    if not stale_if_error:
        return False
        
    try:
        stale_window = int(stale_if_error)
    except ValueError:
        return False

    class HeaderWrapper:
        def __init__(self, h): self.headers = h
        
    try:
        date = check_date(HeaderWrapper(resp_headers)) # type: ignore
    except (DateDirectiveMissing, AttributeError):
        date = datetime.now(timezone.utc)
        
    now = datetime.now(timezone.utc)
    age = (now - date).total_seconds()
    
    return age <= stale_window
