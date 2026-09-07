"""Broker access tokens, fetched from the private token API.

    from tokens import get_token
    token = get_token("dhan")     # or "groww"

Stdlib only. No third-party HTTP client, no dependency on the rest of
this project, so the lowest-level scripts can import it without pulling
in econ/ or universe/.

WHAT THIS CHANGES, AND WHAT IT DELIBERATELY DOES NOT
----------------------------------------------------
Tokens expire daily and have repeatedly killed capture sessions and
probes mid-run. Sourcing them dynamically fixes that for DATA READS.

It does NOT extend to execution. SPEC.md 7.5 keeps the pre-trade auth
step a mandatory human touchpoint, and that is not an inconvenience to
engineer around -- it is the last manual gate between a bug and a real
order. Automating credentials for a read-only recorder does not violate
it; automating them for the order path does. That boundary is enforced
in code below (see EXECUTION_PATH_NAMESPACES) rather than left to
discipline, because "nobody would call it from there" is precisely the
kind of assumption that stops being true at 3am in Phase 7.

CACHE EXPIRY IS READ FROM THE API, NOT ASSUMED
----------------------------------------------
A flat TTL is wrong here and dangerously so. Groww's token dies around
06:00; a token cached at 05:50 under a 6-hour TTL would be served as
valid until 11:50 -- nearly six hours after it stopped working, with the
failure surfacing as a confusing 401 in the middle of a capture. So the
API's own `expiry` is honoured, with a safety margin, and an expiry that
cannot be parsed causes a REFETCH rather than a fallback TTL. Being
wrong about freshness is the whole failure mode; guessing is not an
option.

THIS IS A NEW SINGLE POINT OF FAILURE
-------------------------------------
Every data script now depends on tokens.example.invalid being
reachable. When it is not, the failure is raised as TokenAPIUnreachable
with an explicit message, never as a downstream 401 that reads like an
expired credential and sends someone to refresh a token that was fine.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://tokens.example.invalid"
CACHE_PATH = Path.home() / ".broker_tokens.json"
BROKERS = ("dhan", "groww")

#: Refetch when the token expires within this window. A token that dies
#: mid-capture is worse than one extra HTTP call.
EXPIRY_MARGIN_SECONDS = 30 * 60

REQUEST_TIMEOUT = 15

#: Module namespaces that may NEVER obtain a token from here. Order
#: placement authenticates through the human touchpoint in SPEC.md 7.5.
#: Checked against the whole call stack, so an indirect call through a
#: helper does not launder the origin.
EXECUTION_PATH_NAMESPACES = ("oms", "execution", "riskd", "broker.orders", "live")


class TokenError(RuntimeError):
    """Base for every token-sourcing failure."""


class TokenAPIUnreachable(TokenError):
    """The token API could not be reached at all.

    Distinct from an auth failure ON PURPOSE. If this surfaced as a
    generic error someone would go looking for an expired broker token,
    which is the one thing that is definitely not the problem.
    """


class TokenIssuerStale(TokenError):
    """The issuer served a token whose own expiry is already in the past.

    Observed live on 2026-09-01: the issuer's 08:20 server-side refresh
    did not run, so it kept serving the previous day's token, stamped
    expiry=2026-09-01T08:20 and updated=2026-08-31T08:20. Every caller
    got a 24-hour-old token, and Dhan answered DH-901.

    Without this check the dead token is handed to the broker and the
    symptom is an ordinary 401 -- which reads as "our credential
    expired" and sends someone to look at the brokerage account. The
    actual fault is upstream, and naming it is the difference between a
    five-minute fix and a lost session.
    """


class TokenAPIRejected(TokenError):
    """The token API rejected our API key (401/403 from the token API
    itself, not from the broker)."""


class ExecutionPathForbidden(TokenError):
    """An order-placing module tried to obtain a token.

    SPEC.md 7.5: the pre-trade auth step is a mandatory human touchpoint.
    """


def _caller_namespaces() -> list[str]:
    """Module names on the current call stack, excluding this module."""
    out: list[str] = []
    depth = 1
    while True:
        try:
            frame = sys._getframe(depth)  # noqa: SLF001
        except ValueError:
            break
        name = frame.f_globals.get("__name__", "")
        if name and name != __name__:
            out.append(name)
        depth += 1
        if depth > 60:
            break
    return out


def _assert_not_execution_path() -> None:
    for name in _caller_namespaces():
        for forbidden in EXECUTION_PATH_NAMESPACES:
            # Match the FULL dotted name, not its first segment. Comparing
            # only the head silently exempted every dotted entry in the
            # list: `broker.orders` never equals `broker`, and
            # `"broker.orders".startswith("broker.orders.")` is False, so
            # the one namespace named after order placement was the one
            # namespace not fenced. Caught by
            # tests/test_token_execution_fence.py, not by reading.
            if name == forbidden or name.startswith(forbidden + "."):
                raise ExecutionPathForbidden(
                    f"{name} attempted to obtain a broker token automatically. The order path "
                    f"may not do this: SPEC.md 7.5 keeps pre-trade authentication a mandatory "
                    f"human touchpoint, which is the last manual gate between a bug and a real "
                    f"order. Dynamic tokens exist for READ-ONLY data collection. If you are "
                    f"building execution, authenticate explicitly and interactively instead."
                )


#: The .env beside this module. Loaded on demand -- see _api_key().
ENV_PATH = Path(__file__).resolve().parent / ".env"
PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"
NEMESIS_ENV = Path("/Users/USER/Documents/Nemesis/.env")


def _load_dotenv_if_needed() -> None:
    """Populate TOKEN_API_KEY from .env when it is not already set.

    This module used to require the CALLER to have loaded .env first.
    Under an interactive shell that is invisible, because the operator's
    environment usually has it. Under launchd it is not: a scheduled job
    is handed 11 environment variables and a PATH of
    /usr/bin:/bin:/usr/sbin:/sbin, with nothing from any shell profile.
    Measured, not assumed -- a launchd probe confirmed TOKEN_API_KEY is
    not inherited.

    So the daily jobs worked only because each entry point happened to
    call its own .env loader before its first get_token(). That is
    discipline, and it holds until someone adds a script that forgets --
    at which point it fails at 09:00, unattended, and the session is
    gone. Loading it here makes the ordering impossible to get wrong.

    setdefault, never overwrite: a real environment variable must always
    beat a file, or overriding the key for a one-off run stops working.
    """
    if os.environ.get("TOKEN_API_KEY", "").strip():
        return
    for p in (ENV_PATH, PROJECT_ENV, NEMESIS_ENV):
        try:
            text = p.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        if os.environ.get("TOKEN_API_KEY", "").strip():
            return


def _api_key() -> str:
    _load_dotenv_if_needed()
    key = os.environ.get("TOKEN_API_KEY", "").strip()
    if not key:
        raise TokenError(
            f"TOKEN_API_KEY is not set, and {ENV_PATH} does not supply it. It lives in .env "
            f"(gitignored). Export it, or put it in that file. NOTE: scheduled (launchd) jobs "
            f"inherit almost no environment, so an export in a shell profile will NOT reach them."
        )
    return key


def _parse_expiry(raw: object) -> float | None:
    """Epoch seconds, or None if absent/unparseable.

    None means REFETCH -- never 'assume some TTL'. An unparseable expiry
    is exactly the case where a guess would be most likely to be wrong.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        # Naive timestamps are read as IST -- the token API and both
        # brokers are Indian, and assuming UTC would place expiry 5h30m
        # LATE, i.e. would serve a dead token. Wrong in the unsafe
        # direction, so it is not the default.
        parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    return parsed.timestamp()


def _read_cache() -> dict:
    try:
        with CACHE_PATH.open() as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(cache: dict) -> None:
    """Write 0600, creating it 0600 rather than fixing it afterwards.

    os.open with mode 0600 avoids the window in which the file exists
    world-readable between creation and chmod.
    """
    tmp = CACHE_PATH.with_suffix(".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(cache, fh, indent=2)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, CACHE_PATH)
    os.chmod(CACHE_PATH, stat.S_IRUSR | stat.S_IWUSR)


def _is_fresh(entry: dict) -> bool:
    """Fresh only if a PARSED expiry is more than the margin away."""
    if not isinstance(entry, dict) or not entry.get("token"):
        return False
    expiry_epoch = _parse_expiry(entry.get("expiry"))
    if expiry_epoch is None:
        return False  # missing/unparseable -> refetch, never a TTL fallback
    return (expiry_epoch - time.time()) > EXPIRY_MARGIN_SECONDS


def _fetch(broker: str) -> dict:
    url = f"{BASE_URL}/token/{broker}"
    req = urllib.request.Request(url, headers={"X-API-Key": _api_key(), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise TokenAPIRejected(
                f"The token API rejected our API key (HTTP {e.code}). This is TOKEN_API_KEY being "
                f"wrong or revoked -- NOT an expired broker token. Check .env."
            ) from e
        raise TokenAPIUnreachable(
            f"Token API returned HTTP {e.code} for {url}. The broker token itself is not the "
            f"problem; the service that issues it is failing."
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TokenAPIUnreachable(
            f"Cannot reach the token API at {BASE_URL} ({type(e).__name__}: {e}).\n"
            f"  Every data script now depends on this service — it is a single point of failure "
            f"introduced deliberately, and this is what its outage looks like.\n"
            f"  This is NOT an expired broker token. Refreshing credentials will not help."
        ) from e
    except json.JSONDecodeError as e:
        raise TokenAPIUnreachable(
            f"Token API at {url} returned a non-JSON body. Treating as an outage rather than "
            f"guessing at the response shape."
        ) from e

    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise TokenAPIUnreachable(
            f"Token API response for {broker!r} contained no usable 'token' field "
            f"(keys: {sorted(payload) if isinstance(payload, dict) else type(payload).__name__})."
        )
    return {
        "token": token,
        "expiry": payload.get("expiry"),
        "updated": payload.get("updated"),
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def refresh(broker: str | None = None) -> dict:
    """Ask the issuer to mint new broker tokens (POST /refresh).

    The documented remediation for a broker 401: refresh once, wait, refetch,
    retry once. Deliberately NOT called from get_token() -- an automatic
    refresh on every failure would hammer the issuer and mask a real outage.
    Callers invoke it explicitly, at most once per process.
    """
    req = urllib.request.Request(
        f"{BASE_URL}/refresh", data=b"", method="POST",
        headers={"X-API-Key": _api_key(), "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT * 4) as resp:
            body = resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        raise TokenAPIRejected(f"POST /refresh returned HTTP {e.code}") from e
    except Exception as e:  # noqa: BLE001
        raise TokenAPIUnreachable(f"POST /refresh could not reach {BASE_URL}: {e}") from e
    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {"raw": body[:200]}


def get_token(broker: str, *, force: bool = False) -> str:
    """Current access token for `broker` ("dhan" or "groww").

    Served from ~/.broker_tokens.json when the cached entry's own expiry
    is more than 30 minutes away; refetched otherwise, including when the
    expiry is missing or unparseable.

    Raises TokenAPIUnreachable when the token service is down, which is
    deliberately distinct from any broker auth failure.
    """
    _assert_not_execution_path()
    return _get_token_unfenced(broker, force=force)


def _get_token_unfenced(broker: str, *, force: bool = False) -> str:
    """Everything get_token does EXCEPT the fence.

    Split out so the fence and the fetch can be tested independently: a
    test that the fence lets a legitimate caller through should not need
    a network, a token cache, or an API key on the machine running it.
    Nothing in the codebase calls this directly -- get_token is the
    interface, and the fence is not optional on it.
    """
    broker = broker.strip().lower()
    if broker not in BROKERS:
        raise ValueError(f"unknown broker {broker!r}; expected one of {BROKERS}")

    cache = _read_cache()
    entry = cache.get(broker)
    if not force and _is_fresh(entry):
        return entry["token"]

    fresh = _fetch(broker)
    # A REFETCH IS NOT A GUARANTEE OF FRESHNESS. The issuer can serve a
    # token that is already expired -- it did, on 2026-09-01, when its own
    # 08:20 refresh failed to run. Returning it anyway turns an upstream
    # fault into a broker 401 at the call site, which is the wrong
    # diagnosis pointing at the wrong system.
    if not _is_fresh(fresh):
        raise TokenIssuerStale(
            f"The token issuer served a {broker} token that is ALREADY EXPIRED. "
            f"expiry={fresh.get('expiry')!r} issuer_updated={fresh.get('updated')!r}. "
            f"This is not a problem with your broker account and refreshing broker "
            f"credentials will not help -- the issuer's own scheduled refresh did not "
            f"produce a live token. Remediation: POST {BASE_URL}/refresh, wait, refetch."
        )
    cache[broker] = fresh
    try:
        _write_cache(cache)
    except OSError:
        # A cache we cannot persist is a performance problem, not a
        # correctness one. The token in hand is still good.
        pass
    return fresh["token"]


def token_status(broker: str) -> dict:
    """Non-secret cache metadata, for status surfaces.

    NEVER returns the token. Safe to render in a dashboard.
    """
    entry = _read_cache().get(broker.strip().lower())
    if not isinstance(entry, dict) or not entry.get("token"):
        return {"broker": broker, "cached": False, "fresh": False, "expiry": None}
    expiry_epoch = _parse_expiry(entry.get("expiry"))
    return {
        "broker": broker,
        "cached": True,
        "fresh": _is_fresh(entry),
        "expiry": entry.get("expiry"),
        "expiry_parseable": expiry_epoch is not None,
        "seconds_remaining": int(expiry_epoch - time.time()) if expiry_epoch else None,
        "fetched_at": entry.get("fetched_at"),
    }


def probe() -> dict:
    """Is the token API reachable? For health checks and the dashboard.

    Never raises and never exposes a token.
    """
    try:
        _api_key()
    except TokenError as e:
        return {"reachable": False, "reason": str(e), "kind": "CONFIG"}
    try:
        _fetch("dhan")
        return {"reachable": True, "reason": "", "kind": "OK"}
    except TokenAPIRejected as e:
        return {"reachable": False, "reason": str(e), "kind": "REJECTED"}
    except TokenError as e:
        return {"reachable": False, "reason": str(e), "kind": "UNREACHABLE"}
