import asyncio
import concurrent.futures as _cf
import functools
import gc
import gzip
import inspect
import json
import os
import random
import shutil
import signal
import socket
import statistics
import sys
import threading
import time
import traceback
import tracemalloc
import zlib

from collections import deque
from datetime import datetime

import aiohttp
import aiohttp.streams
import brotli
import orjson
import psutil

from aiohttp import resolver
from colorama import Fore, init as colorama_init
from fake_useragent import UserAgent

aiohttp.resolver.DefaultResolver = resolver.ThreadedResolver
aiohttp.streams.DEFAULT_LIMIT = 16 * 1024
aiohttp.streams.DEFAULT_BUFFER = 8 * 1024


class DummyJar(aiohttp.DummyCookieJar):
    def update_cookies(self, *a, **kw):
        return


aiohttp.DummyCookieJar = DummyJar


async def fast_json(self):
    body = await self.read()
    try:
        return orjson.loads(body)
    except:
        return json.loads(body.decode("utf-8", "replace"))


aiohttp.ClientResponse.json = fast_json
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
else:
    try:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    except:
        pass
DEFAULT_TIMEOUT = 10
NAME_BOT = "Solflare Kingdom"
_MAIN_LOOP: asyncio.AbstractEventLoop | None = None
_GLOBAL_LOOP: asyncio.AbstractEventLoop | None = None
_GLOBAL_LOOP_THREAD: threading.Thread | None = None
_LOOP_LOCK = threading.Lock()


def register_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def _start_background_loop() -> None:
    global _GLOBAL_LOOP, _GLOBAL_LOOP_THREAD

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with _LOOP_LOCK:
            nonlocal_loop_set = None
            _GLOBAL_LOOP = loop
        try:
            loop.run_forever()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    thr = threading.Thread(target=_run, daemon=True)
    _GLOBAL_LOOP_THREAD = thr
    thr.start()
    start = time.time()
    while _GLOBAL_LOOP is None and time.time() - start < 2.0:
        time.sleep(0.01)


def _get_target_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        if _MAIN_LOOP is not None:
            return _MAIN_LOOP
        with _LOOP_LOCK:
            if _GLOBAL_LOOP is None:
                _start_background_loop()
        start = time.time()
        while _GLOBAL_LOOP is None and time.time() - start < 2.0:
            time.sleep(0.01)
        if _GLOBAL_LOOP is None:
            raise RuntimeError("No event loop available")
        return _GLOBAL_LOOP


def run_coro_from_any_thread(coro):
    try:
        asyncio.get_running_loop()
        raise RuntimeError(
            "run_coro_from_any_thread called from within running loop; await the coroutine instead."
        )
    except RuntimeError:
        loop = _get_target_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result()


class BoundedSet:
    def __init__(self, maxlen: int = 10000):
        self._set = set()
        self._dq = deque()
        self.maxlen = maxlen

    def __contains__(self, item):
        return item in self._set

    def add(self, item):
        if item in self._set:
            return
        self._set.add(item)
        self._dq.append(item)
        if len(self._dq) > self.maxlen:
            old = self._dq.popleft()
            try:
                self._set.remove(old)
            except KeyError:
                pass

    def clear(self):
        self._set.clear()
        self._dq.clear()

    def __len__(self):
        return len(self._dq)


colorama_init(autoreset=True)
_global_ua = None


def now_ts():
    return datetime.now().strftime("[%Y:%m:%d ~ %H:%M:%S] |")


class ProxyManager:
    def __init__(
        self,
        proxies: list[str] | None = None,
        recovery_interval: int = 25,
        connect_timeout: int = 6,
        max_fail: int = 5,
    ):
        self.lock = asyncio.Lock()
        self.proxies: dict[str, dict] = {}
        proxies = proxies or []
        for p in proxies:
            self._init_proxy(p)
        self.recovery_interval = recovery_interval
        self.connect_timeout = connect_timeout
        self.max_fail = max_fail
        self.recovery_task = None

    def _init_proxy(self, p: str):
        self.proxies[p] = {
            "score": 1.0,
            "fail": 0,
            "success": 0,
            "latency": None,
            "last_ok": 0,
            "last_fail": 0,
            "alive": True,
        }

    def start_recovery_async(self, loop=None):
        if self.recovery_task:
            return
        if loop is None:
            loop = asyncio.get_running_loop()
        self.recovery_task = loop.create_task(self._recovery_loop_async())

    async def stop_recovery_async(self):
        if self.recovery_task:
            self.recovery_task.cancel()
            try:
                await self.recovery_task
            except:
                pass
            self.recovery_task = None

    async def _recovery_loop_async(self):
        while True:
            await asyncio.sleep(self.recovery_interval)
            try:
                await self._check_all_proxies_async()
            except Exception as e:
                print("Recovery loop error:", e)

    async def _check_all_proxies_async(self):
        async with self.lock:
            plist = list(self.proxies.keys())
        tasks = [self._test_proxy_async(p) for p in plist]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _test_proxy_async(self, proxy: str):
        test_url = "https://httpbin.org/get"
        timeout = aiohttp.ClientTimeout(total=self.connect_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            t0 = time.monotonic()
            try:
                async with s.get(test_url, proxy=proxy) as r:
                    await r.text()
                latency = time.monotonic() - t0
                async with self.lock:
                    px = self.proxies.get(proxy)
                    if not px:
                        return
                    px["success"] += 1
                    px["fail"] = 0
                    px["alive"] = True
                    px["latency"] = latency
                    px["last_ok"] = time.time()
                    px["score"] = max(px["score"] + 0.2, 0.1)
            except:
                async with self.lock:
                    px = self.proxies.get(proxy)
                    if not px:
                        return
                    px["fail"] += 1
                    px["last_fail"] = time.time()
                    px["score"] = max(px["score"] - 0.5, -5)
                    if px["fail"] >= self.max_fail:
                        px["alive"] = False

    async def get_proxy(self, block=False, timeout=0.3):
        """
        block=False → langsung ambil proxy terbaik
        block=True  → tunggu proxy hidup (optional)
        """
        if not block:
            return await self._pick_best_proxy()
        t0 = time.monotonic()
        while True:
            p = await self._pick_best_proxy()
            if p:
                return p
            if time.monotonic() - t0 >= timeout:
                return None
            await asyncio.sleep(0.05)

    async def _pick_best_proxy(self):
        async with self.lock:
            alive = [p for p, d in self.proxies.items() if d["alive"]]
            if not alive:
                return None
            weighted = []
            for p in alive:
                score = max(self.proxies[p]["score"], 0.1)
                weighted.append((p, score))
        total = sum((w for _, w in weighted))
        r = random.uniform(0, total)
        cum = 0
        for p, w in weighted:
            cum += w
            if r <= cum:
                return p
        return weighted[-1][0]

    async def mark_success(self, proxy: str, latency: float):
        async with self.lock:
            if proxy not in self.proxies:
                self._init_proxy(proxy)
            d = self.proxies[proxy]
            d["alive"] = True
            d["fail"] = 0
            d["success"] += 1
            d["latency"] = latency
            d["score"] += 0.3

    async def mark_failure(self, proxy: str):
        async with self.lock:
            if proxy not in self.proxies:
                self._init_proxy(proxy)
            d = self.proxies[proxy]
            d["fail"] += 1
            d["score"] -= 0.6
            d["alive"] = d["fail"] < self.max_fail

    async def add_proxy(self, p: str):
        async with self.lock:
            self._init_proxy(p)


async def decode_aio_resp(resp: aiohttp.ClientResponse):
    ct = (resp.headers.get("Content-Type") or "").lower()
    text = await resp.text()
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return (await resp.json(content_type=None), text)
        except Exception:
            try:
                return (json.loads(stripped), text)
            except Exception:
                return (text, text)
    return (text, text)


def wrapper_feature(func):
    is_login = func.__name__.lower() == "login"

    @functools.wraps(func)
    async def _async_wrapper(*args, **kwargs):
        self = args[0] if args else None
        if is_login and getattr(self, "prepare_session", None):
            try:
                maybe = self.prepare_session()
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:
                pass
        try:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            loop = asyncio.get_running_loop()
            executor = None
            try:
                executor = getattr(args[0], "executor", None)
            except Exception:
                executor = None
            return await loop.run_in_executor(
                executor, functools.partial(func, *args, **kwargs)
            )
        except Exception as e:
            try:
                if self:
                    self.log(f"Error in {func.__name__}: {e}", Fore.RED)
            except Exception:
                pass
            return None
        finally:
            try:
                if getattr(self, "clear_locals", None):
                    maybe = self.clear_locals()
                    if inspect.isawaitable(maybe):
                        await maybe
            except Exception:
                pass

    def wrapper(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            return _async_wrapper(*args, **kwargs)
        except RuntimeError:
            return run_coro_from_any_thread(_async_wrapper(*args, **kwargs))

    return wrapper


def auto_async(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            return func(*args, **kwargs)
        except RuntimeError:
            if inspect.iscoroutinefunction(func):
                return run_coro_from_any_thread(func(*args, **kwargs))
            else:
                loop = _get_target_loop()

                async def _run_sync():
                    exec_ = None
                    if args and hasattr(args[0], "executor"):
                        exec_ = args[0].executor
                    return await loop.run_in_executor(
                        exec_, functools.partial(func, *args, **kwargs)
                    )

                return run_coro_from_any_thread(_run_sync())

    return wrapper


class solflarekingdom:
    BASE_URL = "https://kingdom.solflare.com/api/v1/"
    HEADERS = {
        "Accept": "*/*",
        "Accept-Encoding": "br",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "Origin": "https://kingdom.solflare.com",
        "Pragma": "no-cache",
        "Priority": "u=1, i",
        "Referer": "https://kingdom.solflare.com/",
        "Sec-Ch-Ua": '"Microsoft Edge";v="142", "Microsoft Edge WebView2";v="142", "Chromium";v="142", "Not_A Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
    }

    def __init__(
        self,
        use_proxy: bool = False,
        proxy_list: list | None = None,
        load_on_init: bool = True,
    ):
        self._suppress_local_session_log = not load_on_init
        if load_on_init:
            self.config = self.load_config()
            if self.config.get("reff", False):
                try:
                    self.log("🔁 reff enabled via config.json", Fore.CYAN)
                    self.reff()
                except Exception:
                    pass
            self.query_list = self.load_query("query.txt")
        else:
            self.config = {}
            self.query_list = []
        self.token = None
        self._base_headers = dict(getattr(self, "HEADERS", {}) or {})
        self.session: aiohttp.ClientSession | None = None
        self._prepared = False
        self._preparing = False
        self.shared_executor = None
        self.executor = None
        self.proxy = None
        self.proxy_list = (
            proxy_list
            if proxy_list is not None
            else self.load_proxies()
            if load_on_init
            else []
        )
        self.proxy_manager = None

    def banner(self):
        self.log("")
        self.log("=======================================", Fore.CYAN)
        self.log(f"           🎉  {NAME_BOT} BOT 🎉             ", Fore.CYAN)
        self.log("=======================================", Fore.CYAN)
        self.log("🚀  by LIVEXORDS", Fore.CYAN)
        self.log("📢  t.me/livexordsscript", Fore.CYAN)
        self.log("=======================================", Fore.CYAN)
        self.log("")

    def log(self, message, color=Fore.RESET):
        safe_message = str(message).encode("utf-8", "backslashreplace").decode("utf-8")
        print(Fore.LIGHTBLACK_EX + now_ts() + " " + color + safe_message + Fore.RESET)

    def _merge_headers(self, extra: dict | None):
        if not extra:
            return self._base_headers
        if not extra.keys():
            return self._base_headers
        new_hdr = self._base_headers.copy()
        new_hdr.update(extra)
        return new_hdr

    class AioRespWrapper:
        __slots__ = ("status", "headers", "reason", "body", "_text_cache")

        def __init__(self, orig, body):
            self.status = orig.status
            self.headers = orig.headers
            self.reason = orig.reason
            self.body = body
            self._text_cache = None

        async def text(self):
            if self._text_cache is None:
                try:
                    charset = self.headers.get("Content-Type", "")
                    if "charset=" in charset:
                        charset = charset.split("charset=")[-1].split(";")[0].strip()
                    else:
                        charset = "utf-8"
                    self._text_cache = self.body.decode(charset, errors="replace")
                except:
                    self._text_cache = self.body.decode("utf-8", errors="replace")
            return self._text_cache

        async def json(self):
            return json.loads(await self.text())

    def set_header(self, key, value):
        if not hasattr(self, "HEADERS"):
            self.HEADERS = {}
        if not hasattr(self, "_base_headers"):
            self._base_headers = {}
        self.HEADERS[key] = value
        self._base_headers[key] = value

    async def _request(
        self,
        method: str,
        url_or_path: str,
        *,
        headers: dict | None = None,
        params: dict | None = None,
        data=None,
        json_data=None,
        timeout: float | None = None,
        use_session: bool = True,
        allow_redirects: bool = True,
        stream: bool = False,
        parse: bool = False,
        retries: int = 2,
        backoff: float = 0.5,
        allow_proxy: bool = True,
        debug: bool = False,
    ):
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        method = method.upper()
        headers = headers or {}
        timeout = timeout or 10.0
        if not url_or_path.lower().startswith("http"):
            url = self.BASE_URL.rstrip("/") + "/" + url_or_path.lstrip("/")
        else:
            url = url_or_path
        last_exc = None
        adaptive_retries = retries
        attempt = 1
        while attempt <= adaptive_retries + 1:
            chosen_proxy = None
            temp_session = False
            try:
                proxies = None
                if allow_proxy and getattr(self, "proxy_manager", None):
                    if getattr(self, "proxy", None):
                        chosen_proxy = self.proxy
                        proxies = {"http": chosen_proxy, "https": chosen_proxy}
                    else:
                        chosen_proxy = await self.proxy_manager.get_proxy(
                            block=True, timeout=0.5
                        )
                        if chosen_proxy:
                            chosen_proxy = self.normalize_proxy(chosen_proxy)
                            proxies = {"http": chosen_proxy, "https": chosen_proxy}
                if chosen_proxy:
                    params_adaptive = self.compute_adaptive_proxy_params(chosen_proxy)
                    timeout = float(params_adaptive.get("timeout", timeout))
                    adaptive_retries = int(params_adaptive.get("retries", 1))
                else:
                    adaptive_retries = retries
                if use_session:
                    if getattr(self, "session", None) is None or self.session.closed:
                        await self.prepare_session()
                    session = self.session
                else:
                    session = aiohttp.ClientSession()
                    temp_session = True
                req_kwargs = {
                    "allow_redirects": allow_redirects,
                    "timeout": aiohttp.ClientTimeout(total=timeout),
                    "headers": self._merge_headers(headers),
                }
                if params:
                    req_kwargs["params"] = params
                if json_data is not None:
                    req_kwargs["json"] = json_data
                elif data is not None:
                    req_kwargs["data"] = data
                if proxies:
                    req_kwargs["proxy"] = chosen_proxy
                if debug:
                    self.log(
                        f"[DEBUG aiohttp] {method} {url} proxy={chosen_proxy}",
                        Fore.MAGENTA,
                    )
                resp = await session.request(method, url, **req_kwargs)
                if resp.status == 429:
                    delay_sec = attempt * 10
                    self.log(
                        f"⏳ 429 rate-limited. Delaying {delay_sec}s (attempt {attempt})...",
                        Fore.YELLOW,
                    )
                    await asyncio.sleep(delay_sec)
                    if attempt >= 5:
                        self.log("❌ Too many 429 responses (5x). Stopping.", Fore.RED)
                        raise aiohttp.ClientError("Too many 429 responses")
                    attempt += 1
                    continue
                if chosen_proxy:
                    try:
                        self._record_proxy_result(chosen_proxy, True, 0.0)
                    except:
                        pass
                if parse or stream:
                    body_bytes = await resp.read()
                else:
                    body_bytes = b""
                await resp.release()
                if temp_session:
                    await session.close()
                text_cache = None

                async def _text():
                    nonlocal text_cache
                    if text_cache is None:
                        try:
                            text_cache = body_bytes.decode(
                                resp.charset or "utf-8", errors="replace"
                            )
                        except:
                            text_cache = body_bytes.decode("utf-8", errors="replace")
                    return text_cache

                async def _json():
                    return json.loads(await _text())

                decoded = None
                if parse:
                    try:
                        decoded = json.loads(body_bytes.decode("utf-8", "replace"))
                    except:
                        decoded = None
                return (self.AioRespWrapper(resp, body_bytes), decoded)
            except aiohttp.ClientError as e:
                last_exc = e
                if temp_session:
                    try:
                        await session.close()
                    except:
                        pass
                if (
                    allow_proxy
                    and getattr(self, "proxy", None)
                    and getattr(self, "proxy_manager", None)
                ):
                    try:
                        self._record_proxy_result(self.proxy, False, None)
                    except:
                        pass
                    try:
                        await self.rotate_proxy_and_ua(
                            force_new_proxy=True, quick_test=True
                        )
                    except:
                        pass
                    try:
                        if use_session and getattr(self.session, "closed", True):
                            await self.prepare_session()
                    except:
                        pass
                    if attempt == 1:
                        self.log(
                            f"🔁 Retrying {method} {url} after proxy rotate...",
                            Fore.YELLOW,
                        )
                        await asyncio.sleep(0.15)
                        continue
                if getattr(self, "proxy_manager", None) and chosen_proxy:
                    try:
                        await self.proxy_manager.mark_failure(chosen_proxy)
                    except:
                        pass
                    self.proxy = None
                self.log(
                    f"⚠️ Request error attempt {attempt} for {method} {url}: {e}",
                    Fore.YELLOW,
                )
                await asyncio.sleep(
                    backoff * 2 ** (attempt - 1) * random.uniform(0.9, 1.1)
                )
                attempt += 1
                continue
            except Exception as e:
                last_exc = e
                if temp_session:
                    try:
                        await session.close()
                    except:
                        pass
                self.log(f"❌ Unexpected error: {e}", Fore.RED)
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("request failed unexpectedly")

    def memory_monitor(self):
        try:
            p = psutil.Process()
            mem = p.memory_info().rss
            return f"RSS={mem / 1024 / 1024:.2f} MB"
        except Exception:
            try:
                tracemalloc.start()
                s = tracemalloc.take_snapshot()
                total = sum(stat.size for stat in s.statistics("filename"))
                return f"tracemalloc_total={total / 1024 / 1024:.2f} MB"
            except Exception:
                return "unknown"

    def clear_locals(self):
        try:
            self.log(f"🔎 Memory before clear: {self.memory_monitor()}", Fore.MAGENTA)
        except Exception:
            pass
        try:
            frame = inspect.currentframe()
            if not frame:
                return
            caller = frame.f_back
            if caller and caller.f_back:
                caller = caller.f_back
            if not caller:
                return
            names = list(caller.f_locals.keys())
            for name in names:
                if name not in ("self",) and (not name.startswith("__")):
                    try:
                        del caller.f_locals[name]
                    except Exception:
                        try:
                            caller.f_locals[name] = None
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            try:
                gc.collect()
            except:
                pass
            try:
                self.log(
                    f"✅ Memory after clear: {self.memory_monitor()}",
                    Fore.LIGHTBLACK_EX,
                )
            except:
                pass
            try:
                del frame
                del caller
            except:
                pass

    def get_ua(self):
        global _global_ua
        if _global_ua is None:
            try:
                _global_ua = UserAgent(use_cache=True)
            except Exception:
                _global_ua = None
        try:
            if _global_ua:
                ua = _global_ua.random
                if isinstance(ua, str):
                    return ua
        except:
            pass
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    def _record_proxy_result(self, proxy, success: bool, latency: float | None = None):
        try:
            pm = getattr(self, "proxy_manager", None)
            if not pm:
                return
            proxy = self.normalize_proxy(proxy)
            if not proxy:
                return
            if success:
                try:
                    if latency is None:
                        pm.mark_success(proxy)
                    else:
                        pm.mark_success(proxy, latency=latency)
                except Exception:
                    pass
            else:
                try:
                    pm.mark_failure(proxy, latency=latency)
                except Exception:
                    pass
        except Exception:
            pass

    def compute_adaptive_proxy_params(self, proxy) -> dict:
        pm = getattr(self, "proxy_manager", None)
        if pm is None or proxy is None:
            return {"timeout": 1.5, "retries": 1, "quarantine": 30}
        try:
            avg_lat, fail_rate, score = pm.get_stats(proxy)
            fail_rate = max(0.0, min(1.0, float(fail_rate or 0.0)))
            if avg_lat is None:
                timeout = 1.0
            else:
                timeout = max(0.35, min(3.0, float(avg_lat) * 1.6 + 0.15))
            if fail_rate < 0.25:
                retries = 1
            elif fail_rate < 0.6:
                retries = 2
            else:
                retries = 3
            return {
                "timeout": float(timeout),
                "retries": retries,
                "quarantine": int(getattr(pm, "_quarantine_seconds", 30)),
            }
        except Exception:
            return {"timeout": 1.2, "retries": 1, "quarantine": 30}

    async def rotate_proxy_and_ua(
        self, force_new_proxy: bool = True, quick_test: bool = True
    ):
        if not force_new_proxy and getattr(self, "proxy", None):
            return
        plist = list(getattr(self, "proxy_list", []) or [])
        if not plist:
            self.proxy = None
            return
        max_attempts = max(3, len(plist) + 1)
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            candidate = None
            try:
                if getattr(self, "proxy_manager", None):
                    candidate = await self.proxy_manager.get_proxy(
                        block=True, timeout=0.5, prefer_best=True
                    )
                    candidate = self.normalize_proxy(candidate)
                else:
                    candidate = random.choice(plist)
            except:
                candidate = None
            if not candidate:
                self.proxy = None
                return
            if quick_test:
                ok = False
                params = self.compute_adaptive_proxy_params(candidate)
                adaptive_timeout = float(params.get("timeout", 3.0))
                test_timeout = aiohttp.ClientTimeout(total=min(6, adaptive_timeout))
                test_url = "https://httpbin.org/ip"
                start = time.time()
                try:
                    async with aiohttp.ClientSession(timeout=test_timeout) as s:
                        async with s.get(test_url, proxy=candidate) as r:
                            ok = r.status < 400
                except:
                    ok = False
                latency = time.time() - start
                try:
                    self._record_proxy_result(candidate, ok, latency)
                except:
                    pass
                if ok:
                    try:
                        self.log(
                            f"🌐 Proxy OK ({latency:.2f}s): {candidate}", Fore.GREEN
                        )
                    except:
                        pass
                else:
                    try:
                        self.log(
                            f"⚠️ Proxy bad ({latency:.2f}s): {candidate}", Fore.YELLOW
                        )
                    except:
                        pass
                if not ok:
                    try:
                        if getattr(self, "proxy_manager", None):
                            await self.proxy_manager.mark_failure(candidate)
                    except:
                        pass
                    await asyncio.sleep(0.05)
                    continue
            await self.prepare_session()
            self.proxy = candidate
            try:
                if hasattr(self, "get_ua"):
                    ua = self.get_ua()
                    if inspect.isawaitable(ua):
                        ua = await ua
                    if isinstance(ua, str) and ua.strip():
                        hdr = {k.lower(): v for k, v in (self.HEADERS or {}).items()}
                        hdr["user-agent"] = ua
                        try:
                            self.session._default_headers.clear()
                            self.session._default_headers.update(hdr)
                        except:
                            pass
            except:
                pass
            return
        self.proxy = None

    @wrapper_feature
    def reff(self):
        try:
            self.log("🎯 Running reff placeholder...", Fore.CYAN)
            pass
        except Exception as e:
            self.log(f"❌ reff error: {e}", Fore.RED)

    def load_config(self, suppress_log: bool = False):
        try:
            with open("config.json", encoding="utf-8") as f:
                cfg = json.load(f)
            if not suppress_log:
                try:
                    self.log("✅ Config loaded", Fore.GREEN)
                except:
                    pass
            return cfg
        except FileNotFoundError:
            if not suppress_log:
                try:
                    self.log("⚠️ config.json not found (using minimal)", Fore.YELLOW)
                except:
                    pass
            return {}
        except Exception as e:
            if not suppress_log:
                try:
                    self.log(f"❌ Config parse error: {e}", Fore.RED)
                except:
                    pass
            return {}

    def load_query(self, path_file: str = "query.txt") -> list:
        try:
            if not os.path.exists(path_file):
                try:
                    self.log(f"❌ {path_file} not found", Fore.RED)
                except:
                    pass
                return []
            queries = []
            with open(path_file, encoding="utf-8") as file:
                for line in file:
                    v = line.strip()
                    if v:
                        queries.append(v)
            cfg = getattr(self, "config", None)
            if cfg and cfg.get("reff", False):
                reff_file = "reff_result.txt"
                if os.path.exists(reff_file):
                    try:
                        with open(reff_file, encoding="utf-8") as rf:
                            reff_lines = [ln.strip() for ln in rf if ln.strip()]
                    except Exception as e:
                        try:
                            self.log(f"❌ Error loading {reff_file}: {e}", Fore.RED)
                        except:
                            pass
                        reff_lines = []
                else:
                    try:
                        self.log(
                            f"⚪ {reff_file} not found (reff enabled but no results yet)",
                            Fore.YELLOW,
                        )
                    except:
                        pass
                    reff_lines = []
                if reff_lines:
                    seen = set(queries)
                    appended = 0
                    for item in reff_lines:
                        if item not in seen:
                            queries.append(item)
                            seen.add(item)
                            appended += 1
                    try:
                        self.log(
                            f"🔁 Loaded {len(reff_lines)} from {reff_file} (+{appended} new)",
                            Fore.CYAN,
                        )
                    except:
                        pass
            if not queries:
                try:
                    self.log(f"⚠️ {path_file} empty", Fore.YELLOW)
                except:
                    pass
            else:
                try:
                    self.log(
                        f"✅ {len(queries)} entries loaded from {path_file}", Fore.GREEN
                    )
                except:
                    pass
            return queries
        except Exception as e:
            try:
                self.log(f"❌ Query load error: {e}", Fore.RED)
            except:
                pass
            return []

    @wrapper_feature
    async def login(self, index: int) -> None:
        if index < 0 or index >= len(self.query_list):
            self.log("❌ Invalid login index.", Fore.RED)
            return
        query_raw = self.query_list[index].strip()
        if not query_raw:
            self.log("❌ Empty query_id in list.", Fore.RED)
            return
        payload = {"initData": query_raw}
        reff = self.config.get("reffcode")
        if reff:
            payload["referralCode"] = reff
        max_retry = 50
        attempt = 1
        access_token = None
        while attempt <= max_retry:
            try:
                self.log(f"🔁 Login attempt {attempt}/{max_retry} ...", Fore.YELLOW)
                resp, parsed = await self._request(
                    "POST", "auth/telegram/raw", json_data=payload, parse=True
                )
                if parsed and parsed.get("success") is True:
                    access_token = parsed["data"]["access_token"]
                    self.log("✅ Login successful.", Fore.GREEN)
                    break
                if parsed and parsed.get("statusCode") == 429:
                    self.log("⏳ 429 Too Many Requests. Retrying...", Fore.YELLOW)
                    await asyncio.sleep(0.3)
                else:
                    self.log(f"⚠️ Unexpected login response: {parsed}", Fore.RED)
                    await asyncio.sleep(0.3)
            except Exception as e:
                self.log(f"❌ Login error: {e}", Fore.RED)
                await asyncio.sleep(0.3)
            attempt += 1
        if not access_token:
            self.log(
                "❌ Failed to obtain access token after maximum retries.", Fore.RED
            )
            return
        self.set_header("Authorization", f"Bearer {access_token}")
        self.log("🔐 Authorization header applied.", Fore.CYAN)
        try:
            resp2, parsed2 = await self._request("GET", "users/me", parse=True)
        except Exception as e:
            self.log(f"❌ Request to /users/me failed: {e}", Fore.RED)
            return
        if not parsed2 or not parsed2.get("success"):
            self.log(f"❌ /users/me returned error: {parsed2}", Fore.RED)
            return
        user = parsed2["data"]
        stats = user.get("stats", {})
        self.log(f"👤 Username: @{user.get('username')}", Fore.CYAN)
        self.log(f"🆔 Telegram ID: {user.get('telegramId')}", Fore.CYAN)
        self.log(f"📌 UserID: {user.get('id')}", Fore.CYAN)
        self.log(f"💰 Total Points: {stats.get('totalPoints')}", Fore.GREEN)
        self.log(f"🎟️ Tickets: {stats.get('availableTickets')}", Fore.GREEN)
        self.log(f"⭐ Level: {stats.get('level')}", Fore.GREEN)
        self.log("🏁 Login flow completed.", Fore.GREEN)

    @wrapper_feature
    async def daily(self):
        self.log("🔍 Checking daily check-in status...", Fore.CYAN)
        try:
            resp_status, parsed_status = await self._request(
                "GET", "checkin/status", parse=True
            )
        except Exception as e:
            self.log(f"❌ Error requesting check-in status: {e}", Fore.RED)
            return
        if not parsed_status or parsed_status.get("success") is not True:
            self.log(f"❌ Invalid check-in status response: {parsed_status}", Fore.RED)
            return
        data = parsed_status.get("data", {})
        can_check = data.get("canCheckInToday", False)
        has_check = data.get("hasCheckedInToday", False)
        if has_check or not can_check:
            self.log("✨ Already checked in today.", Fore.GREEN)
            return True
        self.log("🟢 Performing daily check-in...", Fore.YELLOW)
        try:
            resp_check, parsed_check = await self._request(
                "POST", "checkin", parse=True, json_data={}
            )
        except Exception as e:
            self.log(f"❌ Check-in failed due to error: {e}", Fore.RED)
            return
        if not parsed_check or parsed_check.get("success") is not True:
            self.log(f"❌ Check-in API returned error: {parsed_check}", Fore.RED)
            return
        reward = parsed_check.get("data", {})
        self.log(
            f"🎉 Check-in successful! Day {reward.get('streakDay')} | +{reward.get('pointsEarned')} pts | +{reward.get('ticketsEarned')} tickets",
            Fore.GREEN,
        )
        return True

    @wrapper_feature
    async def game(self):
        self.log("🔍 Fetching user profile...", Fore.CYAN)
        try:
            resp_me, parsed_me = await self._request("GET", "users/me", parse=True)
        except Exception as e:
            self.log(f"❌ Failed to fetch /users/me: {e}", Fore.RED)
            return
        if not parsed_me or parsed_me.get("success") is not True:
            self.log(f"❌ Invalid /users/me response: {parsed_me}", Fore.RED)
            return
        stats = parsed_me["data"].get("stats", {})
        tickets = stats.get("availableTickets", 0)
        if tickets < 2:
            self.log("🎟️ Not enough tickets to play. Minimum 2 needed.", Fore.YELLOW)
            return
        self.log(f"🎟️ Tickets available: {tickets}", Fore.GREEN)
        self.log("🎮 Fetching available games...", Fore.CYAN)
        try:
            resp_g, parsed_g = await self._request("GET", "games/all", parse=True)
        except Exception as e:
            self.log(f"❌ Failed to fetch /games/all: {e}", Fore.RED)
            return
        if not parsed_g or parsed_g.get("success") is not True:
            self.log(f"❌ Invalid game list response: {parsed_g}", Fore.RED)
            return
        game_target = "cmfx6u2xn0000m0wd81dpmv1f"
        self.log(f"🎯 Selected game ID: {game_target}", Fore.CYAN)
        while tickets >= 2:
            self.log("🟢 Starting new game session...", Fore.YELLOW)
            try:
                resp_start, parsed_start = await self._request(
                    "POST", "games/start", parse=True, json_data={"gameId": game_target}
                )
            except Exception as e:
                self.log(f"❌ Error starting game: {e}", Fore.RED)
                return
            if not parsed_start or parsed_start.get("success") is not True:
                self.log(f"❌ Invalid start game response: {parsed_start}", Fore.RED)
                return
            session = parsed_start["data"]["id"]
            self.log(f"🎮 Game session started: {session}", Fore.GREEN)
            await asyncio.sleep(0.3)
            try:
                resp_ab, parsed_ab = await self._request(
                    "POST",
                    f"games/sessions/{session}/abandon",
                    parse=True,
                    json_data={},
                )
            except Exception as e:
                self.log(f"❌ Failed to abandon session: {e}", Fore.RED)
                return
            if not parsed_ab or parsed_ab.get("success") is not True:
                self.log(f"❌ Abandon API error: {parsed_ab}", Fore.RED)
                return
            self.log(f"🚪 Session abandoned: {session}", Fore.YELLOW)
            score = random.randint(500, 1000)
            assets_clicked = random.randint(500, 1000)
            difficulty = random.randint(580, 1000)
            duration = random.uniform(29.0, 31.0)
            calc_duration = random.randint(29, 31)
            payload_complete = {
                "score": score,
                "gameData": {
                    "duration": duration,
                    "assetsClicked": assets_clicked,
                    "difficulty": difficulty,
                    "timeRemaining": 0,
                    "calculatedDuration": calc_duration,
                },
            }
            await asyncio.sleep(0.3)
            try:
                resp_c, parsed_c = await self._request(
                    "POST",
                    f"games/complete/{session}",
                    parse=True,
                    json_data=payload_complete,
                )
            except Exception as e:
                self.log(f"❌ Failed completing game: {e}", Fore.RED)
                return
            if not parsed_c or parsed_c.get("success") is not True:
                self.log(f"❌ Complete API returned error: {parsed_c}", Fore.RED)
                return
            self.log(
                f"🏁 Game completed | Score: {score} | Clicks: {assets_clicked} | Difficulty: {difficulty}",
                Fore.GREEN,
            )
            tickets -= 2
            self.log(f"🎟️ Remaining tickets: {tickets}", Fore.CYAN)
            await asyncio.sleep(0.3)
        self.log("✅ All tickets used. Game session finished.", Fore.GREEN)

    @wrapper_feature
    async def task(self):
        self.log("🔍 Fetching quests list...", Fore.CYAN)
        try:
            _, parsed_quests = await self._request("GET", "quests", parse=True)
        except Exception as e:
            self.log(f"❌ Failed to fetch quests: {e}", Fore.RED)
            return
        if not parsed_quests or parsed_quests.get("success") is not True:
            self.log(f"❌ Invalid /quests response: {parsed_quests}", Fore.RED)
            return
        self.log("🔎 Fetching completed quests...", Fore.CYAN)
        try:
            _, parsed_completed = await self._request(
                "GET", "quests/my-completions", parse=True
            )
        except Exception as e:
            self.log(f"❌ Failed to fetch my-completions: {e}", Fore.RED)
            return
        if parsed_completed is None:
            parsed_completed = {"data": []}
        completed_ids = {
            c.get("questId")
            for c in parsed_completed.get("data", [])
            if c.get("questId")
        }
        self.log(f"🗂️ Completed quests: {len(completed_ids)} found", Fore.CYAN)
        quests = parsed_quests.get("data", {}).get("quests", [])
        to_start = []
        for q in quests:
            qid = q.get("id")
            title = q.get("title", "<no-title>")
            active = q.get("isActive", False)
            if not active:
                self.log(f"⏭ Skipping inactive quest: {title} ({qid})", Fore.YELLOW)
                continue
            if qid in completed_ids:
                self.log(f"✅ Already completed: {title} ({qid})", Fore.GREEN)
                continue
            self.log(f"📥 Queueing quest to start: {title} ({qid})", Fore.CYAN)
            to_start.append(qid)
        if not to_start:
            self.log("ℹ️ No quests to start.", Fore.YELLOW)
            return True
        claim_list = []
        self.log("🚀 Starting queued quests...", Fore.CYAN)
        for qid in to_start:
            try:
                _, parsed_start = await self._request(
                    "POST", f"quests/{qid}/start", parse=True, json_data={}
                )
            except Exception as e:
                self.log(f"❌ Error starting quest {qid}: {e}", Fore.RED)
                await asyncio.sleep(0.3)
                continue
            if parsed_start and parsed_start.get("success") is True:
                self.log(f"✅ Started quest {qid}", Fore.GREEN)
                claim_list.append(qid)
            else:
                sc = parsed_start.get("statusCode") if parsed_start else None
                msg = parsed_start.get("message") if parsed_start else str(parsed_start)
                if sc == 400:
                    self.log(
                        f"⚠️ Skipping quest {qid} (start returned 400): {msg}",
                        Fore.YELLOW,
                    )
                else:
                    self.log(f"❌ Start failed for {qid}: {parsed_start}", Fore.RED)
            await asyncio.sleep(0.3)
        if not claim_list:
            self.log("ℹ️ Nothing to claim after start phase.", Fore.YELLOW)
            return True
        self.log("🏁 Claiming started quests...", Fore.CYAN)
        for qid in claim_list:
            try:
                _, parsed_claim = await self._request(
                    "POST", "quests/complete", parse=True, data={"questId": qid}
                )
            except Exception as e:
                self.log(f"❌ Claim request failed for {qid}: {e}", Fore.RED)
                await asyncio.sleep(0.3)
                continue
            if parsed_claim and parsed_claim.get("success") is True:
                data = parsed_claim.get("data", {})
                pts = data.get("pointsEarned")
                tks = data.get("ticketsEarned")
                self.log(
                    f"🎉 Quest claimed {qid} | +{(pts if pts is not None else 0)} pts | +{(tks if tks is not None else 0)} tickets",
                    Fore.GREEN,
                )
            else:
                sc = parsed_claim.get("statusCode") if parsed_claim else None
                if sc == 400:
                    self.log(
                        f"⚠️ Claim skipped for {qid} (400): {parsed_claim.get('message')}",
                        Fore.YELLOW,
                    )
                else:
                    self.log(f"❌ Claim failed for {qid}: {parsed_claim}", Fore.RED)
            await asyncio.sleep(0.3)
        self.log("✅ Task phase completed.", Fore.GREEN)
        return True

    def load_proxies(self, filename="proxy.txt"):
        try:
            if not os.path.exists(filename):
                return []
            with open(filename, encoding="utf-8") as file:
                proxies = list(
                    dict.fromkeys([line.strip() for line in file if line.strip()])
                )
            if not proxies:
                raise ValueError("Proxy file is empty.")
            return proxies
        except Exception as e:
            self.log(f"❌ Proxy load error: {e}", Fore.RED)
            return []

    def decode_response(self, response: object) -> object:
        if isinstance(response, str):
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                return response
        headers_get = getattr(response.headers, "get", lambda k, d=None: d)
        content_encoding = (headers_get("Content-Encoding", "") or "").lower()
        data = getattr(response, "content", b"")
        try:
            if content_encoding == "gzip":
                try:
                    data = gzip.decompress(data)
                except Exception:
                    pass
            elif content_encoding in ("br", "brotli"):
                try:
                    data = brotli.decompress(data)
                except Exception:
                    pass
            elif content_encoding in ("deflate", "zlib"):
                try:
                    data = zlib.decompress(data)
                except Exception:
                    pass
        except Exception:
            pass
        content_type = (headers_get("Content-Type", "") or "").lower()
        charset = None
        if "charset=" in content_type:
            try:
                charset = (
                    content_type.split("charset=")[-1]
                    .split(";")[0]
                    .strip()
                    .strip('"')
                    .strip("'")
                )
            except Exception:
                charset = None
        text = None
        if charset:
            try:
                text = data.decode(charset, errors="replace")
            except Exception:
                text = None
        if text is None:
            try:
                text = data.decode("utf-8", errors="strict")
            except Exception:
                try:
                    text = data.decode("utf-8", errors="replace")
                except Exception:
                    text = data.decode("latin-1", errors="replace")
        stripped = text.strip() if isinstance(text, str) else ""
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except Exception:
                return text
        return text

    async def decode_response_async(self, response: object) -> object:
        loop = asyncio.get_running_loop()
        executor = getattr(self, "executor", None)
        if executor:
            return await loop.run_in_executor(
                executor, functools.partial(self.decode_response, response)
            )
        return await asyncio.to_thread(self.decode_response, response)

    def normalize_proxy(self, proxy):
        if isinstance(proxy, dict):
            return proxy.get("http") or proxy.get("https")
        return proxy

    def _format_aiohttp_proxy(self, proxy):
        try:
            if not proxy:
                return None
            if isinstance(proxy, dict):
                p = proxy.get("http") or proxy.get("https")
            else:
                p = proxy
            if not p:
                return None
            if "://" not in p:
                p = "http://" + p
            return p
        except Exception:
            return None

    async def prepare_session(self) -> None:
        if getattr(self, "_prepared", False):
            sess = getattr(self, "session", None)
            if sess is not None and (not sess.closed):
                return
        if getattr(self, "_preparing", False):
            while getattr(self, "_preparing", False):
                await asyncio.sleep(0.02)
            return
        self._preparing = True
        try:
            old_sess = getattr(self, "session", None)
            if old_sess is not None and (not old_sess.closed):
                self._prepared = True
                return
            headers = {k.lower(): v for k, v in (self.HEADERS or {}).items()}
            try:
                ua = getattr(self, "get_ua", None)
                if ua:
                    maybe = ua()
                    if inspect.isawaitable(maybe):
                        maybe = await maybe
                    if isinstance(maybe, str):
                        headers["user-agent"] = maybe
            except:
                pass
            timeout = aiohttp.ClientTimeout(total=12)
            connector = aiohttp.TCPConnector(
                force_close=True, enable_cleanup_closed=True, use_dns_cache=False
            )
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout,
                connector=connector,
                cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False,
            )
            use_proxy = bool(self.config.get("proxy", False))
            if use_proxy:
                if getattr(self, "proxy_manager", None) is None:
                    try:
                        if self.proxy_list:
                            self.proxy_manager = ProxyManager(
                                proxies=list(self.proxy_list),
                                maxsize=max(1, len(self.proxy_list)),
                            )
                    except:
                        self.proxy_manager = None
            if use_proxy and self.proxy_manager:
                chosen = None
                for p in self.proxy_list:
                    purl = self.normalize_proxy(p)
                    if await self._async_test_proxy(purl):
                        chosen = purl
                        break
                if chosen:
                    self.proxy = chosen
                    self.log(f"✅ Proxy OK: {chosen}", Fore.GREEN)
                else:
                    self.proxy = None
                    self.log("⚠️ No working proxy. Using local.", Fore.YELLOW)
            else:
                self.proxy = None
                if not getattr(self, "_suppress_local_session_log", False):
                    self.log("🌐 Using local IP (no proxy)", Fore.YELLOW)
            self._prepared = True
        except Exception as e:
            self.log(
                f"❌ prepare_session error: {e}\n{traceback.format_exc()}", Fore.RED
            )
            self._prepared = False
        finally:
            self._preparing = False

    async def _async_test_proxy(self, proxy_url: str) -> bool:
        if not proxy_url:
            return False
        test_timeout = aiohttp.ClientTimeout(total=3)
        test_url = "https://httpbin.org/ip"
        start = time.time()
        ok = False
        try:
            async with aiohttp.ClientSession(timeout=test_timeout) as s:
                async with s.get(test_url, proxy=proxy_url) as resp:
                    ok = resp.status < 400
            latency = time.time() - start
            try:
                self._record_proxy_result(proxy_url, ok, latency)
            except:
                pass
            return ok
        except Exception:
            try:
                self._record_proxy_result(proxy_url, False, None)
            except:
                pass
            return False

    class _WSHandle:
        def __init__(self, parent, ws, proxy_taken=None, prev_session_proxies=None):
            self._parent = parent
            self.ws = ws
            self.proxy_taken = proxy_taken
            self._prev_session_proxies = prev_session_proxies
            self._closed = False

        @property
        def is_open(self):
            try:
                return not self._closed and (not getattr(self.ws, "closed", False))
            except Exception:
                return False

        async def send(self, data):
            try:
                if isinstance(data, str):
                    await self.ws.send_str(data)
                else:
                    await self.ws.send_bytes(data)
                return True
            except Exception as e:
                try:
                    self._parent._record_proxy_result(
                        self.proxy_taken or self._parent.proxy, False
                    )
                except:
                    pass
                self._parent.log(f"❌ ws.send error: {e}", Fore.RED)
                return False

        async def recv(self, timeout=None):
            try:
                if timeout:
                    msg = await asyncio.wait_for(self.ws.receive(), timeout=timeout)
                else:
                    msg = await self.ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    return msg.data
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    return msg.data
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    return None
                return None
            except TimeoutError:
                return None
            except Exception as e:
                try:
                    self._parent._record_proxy_result(
                        self.proxy_taken or self._parent.proxy, False
                    )
                except:
                    pass
                self._parent.log(f"⚠️ ws.recv error: {e}", Fore.YELLOW)
                return None

        async def close(self, reason=None):
            if self._closed:
                return
            try:
                await self.ws.close()
            except:
                pass
            try:
                if self.proxy_taken and getattr(self._parent, "proxy_manager", None):
                    try:
                        self._parent.proxy_manager.release_proxy(self.proxy_taken)
                        self._parent.log(
                            f"🔁 Proxy released for ws ({self.proxy_taken})", Fore.GREEN
                        )
                    except:
                        pass
            except:
                pass
            sess = getattr(self, "session", None)
            if sess is not None:
                try:
                    close_aiohttp_session_sync(sess)
                except:
                    try:
                        sess.close()
                    except:
                        pass
                finally:
                    self.session = None
            self._closed = True

    def _derive_ws_proxy(self):
        try:
            sess = getattr(self, "session", None)
            if sess is not None:
                proxies = getattr(sess, "proxies", None)
                if isinstance(proxies, dict):
                    p = proxies.get("http") or proxies.get("https")
                    if p:
                        return p
            px = getattr(self, "proxy", None)
            if px:
                if isinstance(px, dict):
                    p = px.get("http") or px.get("https")
                    if p:
                        return p
                elif isinstance(px, str):
                    return px
            pm = getattr(self, "proxy_manager", None)
            if pm:
                candidate = pm.get_proxy(block=False, timeout=0.01)
                if candidate:
                    pm.release_proxy(candidate)
                    if isinstance(candidate, dict):
                        p = candidate.get("http") or candidate.get("https")
                        if p:
                            return p
                    elif isinstance(candidate, str):
                        return candidate
        except Exception:
            pass
        return None

    async def ws_connect(
        self,
        url: str,
        *,
        proxy: str | None = None,
        timeout: float = 30.0,
        use_proxy_from_pool: bool = False,
        debug: bool = False,
    ):
        if self._aiohttp_session is None:
            timeout_obj = aiohttp.ClientTimeout(total=None)
            self._aiohttp_session = aiohttp.ClientSession(timeout=timeout_obj)
        chosen_proxy = proxy or self._derive_ws_proxy()
        chosen_proxy = self.normalize_proxy(chosen_proxy)
        proxy_taken = None
        if use_proxy_from_pool and getattr(self, "proxy_manager", None):
            try:
                candidate = await self.proxy_manager.get_proxy(block=True, timeout=2.0)
                if candidate:
                    proxy_taken = self.normalize_proxy(candidate)
                    chosen_proxy = proxy_taken
                    self.log(
                        f"🧵 Using proxy {chosen_proxy} from pool for WS", Fore.CYAN
                    )
            except Exception:
                proxy_taken = None
        aio_proxy = self._format_aiohttp_proxy(chosen_proxy)
        if debug:
            self.log(
                f"[DEBUG] ws_connect url={url} proxy={aio_proxy} use_pool={use_proxy_from_pool}",
                Fore.MAGENTA,
            )
        errors = []
        for attempt in (1, 2):
            try:
                conn_timeout = aiohttp.ClientTimeout(total=timeout)
                ws = await self._aiohttp_session.ws_connect(
                    url, proxy=aio_proxy, timeout=conn_timeout
                )
                try:
                    self._record_proxy_result(chosen_proxy, True, 0.0)
                except:
                    pass
                handle = self._WSHandle(
                    self, ws, proxy_taken=proxy_taken, prev_session_proxies=None
                )
                try:
                    ok = await handle.send("ping")
                    if ok:
                        pong = await handle.recv(timeout=5)
                        if pong is None:
                            raise Exception("no pong")
                except Exception:
                    try:
                        await handle.close()
                    except:
                        pass
                    raise
                self.log(f"🐾 WebSocket connected -> {url}", Fore.CYAN)
                return handle
            except Exception as e:
                errors.append(e)
                try:
                    self._record_proxy_result(chosen_proxy, False, None)
                except:
                    pass
                if proxy_taken and getattr(self, "proxy_manager", None):
                    try:
                        await self.proxy_manager.release_proxy(proxy_taken)
                    except:
                        pass
                if attempt == 1:
                    await asyncio.sleep(0.12)
                    continue
                else:
                    break
        self.log(
            f"❌ ws_connect failed: {(errors[-1] if errors else 'unknown')}", Fore.RED
        )
        raise Exception("ws_connect failed")

    async def ws_send(
        self,
        handle,
        message,
        *,
        close_after: bool = False,
        close_delay: float = 0.0,
        wait_ack: bool = False,
        ack_timeout: float | None = None,
    ):
        try:
            ok = await handle.send(message)
            if not ok:
                raise Exception("send failed")
            self.log("📤 message sent", Fore.GREEN)
            resp = None
            if wait_ack:
                resp = await handle.recv(timeout=ack_timeout)
            if close_after:
                if close_delay and close_delay > 0:
                    await asyncio.sleep(close_delay)
                await handle.close()
            return resp
        except Exception as e:
            self.log(f"❌ ws_send error: {e}", Fore.RED)
            raise

    async def ws_recv(self, handle, *, timeout: float | None = None):
        try:
            msg = await handle.recv(timeout=timeout)
            if msg is None:
                self.log("⌛ ws.recv timeout/no-data", Fore.YELLOW)
            else:
                self.log("📥 ws.recv got data", Fore.CYAN)
            return msg
        except Exception as e:
            self.log(f"⚠️ ws_recv error: {e}", Fore.YELLOW)
            return None

    async def ws_close(self, handle, *, reason: str | None = None):
        try:
            await handle.close(reason=reason)
            self.log("🔐 WebSocket closed", Fore.MAGENTA)
        except Exception as e:
            self.log(f"⚠️ ws_close error: {e}", Fore.YELLOW)
            raise

    async def close_async(self):
        try:
            pm = getattr(self, "proxy_manager", None)
            if pm:
                try:
                    pm.stop_recovery_async()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if getattr(self, "_aiohttp_session", None):
                try:
                    await self._aiohttp_session.close()
                except Exception:
                    pass
                self._aiohttp_session = None
        except Exception:
            pass
        try:
            execu = getattr(self, "executor", None)
            if execu:
                try:
                    execu.shutdown(wait=False)
                except Exception:
                    pass
                self.executor = None
        except Exception:
            pass
        try:
            if getattr(self, "session", None):
                try:
                    await self.session.close()
                except:
                    pass
                self.session = None
        except Exception:
            pass

    def close(self):
        try:
            loop = asyncio.get_running_loop()
            try:
                task = loop.create_task(self.close_async())
                return
            except Exception:
                asyncio.run_coroutine_threadsafe(self.close_async(), loop)
                return
        except RuntimeError:
            try:
                asyncio.run(self.close_async())
            except Exception:
                pass


tasks_config = {
    "daily": "Auto claim daily",
    "task": "Auto solve task",
    "game": "Auto playing game",
}


async def call_maybe_async(func, *args, executor=None, **kwargs):
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    maybe = func(*args, **kwargs)
    if inspect.isawaitable(maybe):
        return await maybe
    loop = asyncio.get_running_loop()
    if executor is not None:
        return await loop.run_in_executor(
            executor, functools.partial(lambda v: v, maybe)
        )
    return await asyncio.to_thread(lambda: maybe)


async def process_account(
    account,
    original_index,
    account_label,
    blu: solflarekingdom,
    sema: asyncio.Semaphore | None = None,
):
    display_account = account[:12] + "..." if len(account) > 12 else account
    blu.log(f"👤 {account_label}: {display_account}", Fore.YELLOW)
    try:
        blu.config = blu.load_config(suppress_log=True)
    except Exception:
        blu.config = blu.config or {}
    loop = asyncio.get_running_loop()
    if sema is None:
        sema = asyncio.Semaphore(1)
    try:
        async with sema:
            login_fn = blu.login
            await call_maybe_async(
                login_fn, original_index, executor=getattr(blu, "executor", None)
            )
    except Exception as e:
        blu.log(f"❌ login error: {e}", Fore.RED)
        return
    cfg = blu.config or {}
    enabled = [name for key, name in tasks_config.items() if cfg.get(key, False)]
    if enabled:
        blu.log("🛠️ Tasks enabled: " + ", ".join(enabled), Fore.CYAN)
    else:
        blu.log("🛠️ Tasks enabled: (none)", Fore.RED)
    for task_key, task_name in tasks_config.items():
        if not cfg.get(task_key, False):
            continue
        if not hasattr(blu, task_key):
            blu.log(f"⚠️ {task_key} missing", Fore.YELLOW)
            continue
        func = getattr(blu, task_key)
        try:
            if inspect.iscoroutinefunction(func):
                await func()
            else:
                async with sema:
                    await call_maybe_async(
                        func, executor=getattr(blu, "executor", None)
                    )
        except Exception as e:
            blu.log(f"❌ {task_key} error: {e}", Fore.RED)
    delay_switch = cfg.get("delay_account_switch", 10)
    blu.log(f"➡️ Done {account_label}. wait {delay_switch}s", Fore.CYAN)
    await asyncio.sleep(delay_switch)
    if blu.config.get("proxy") and getattr(blu, "proxy_manager", None) and blu.proxy:
        try:
            blu.proxy_manager.release_proxy(blu.proxy)
            blu.log(
                f"🔁 Proxy released ({blu.proxy}) | avail={blu.proxy_manager.available_count()} in_use={blu.proxy_manager.in_use_count()}",
                Fore.GREEN,
            )
        except Exception:
            blu.log("⚠️ release proxy failed", Fore.YELLOW)
        finally:
            blu.proxy = None
    await ultra_slim_self(blu)


async def ultra_slim_self(obj):
    keep = {
        "config",
        "query_list",
        "proxy_list",
        "proxy_manager",
        "executor",
        "shared_executor",
        "blocking_sema",
        "session",
        "_base_headers",
    }
    sess = getattr(obj, "session", None)
    if sess is not None:
        try:
            try:
                sess.cookies.clear()
            except Exception:
                pass
            try:
                for ad in getattr(sess, "adapters", {}).values():
                    try:
                        ad.close()
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
    for name in list(vars(obj).keys()):
        if name in keep:
            continue
        try:
            setattr(obj, name, None)
        except Exception:
            pass
    try:
        snapshot = {k: getattr(obj, k, None) for k in keep}
        obj.__dict__.clear()
        for k, v in snapshot.items():
            try:
                setattr(obj, k, v)
            except Exception:
                pass
    except Exception:
        pass
    try:
        gc.collect()
        gc.collect()
    except Exception:
        pass


async def stream_producer(
    file_path: str,
    queue: asyncio.Queue,
    stop_event: asyncio.Event,
    base_blu: solflarekingdom,
    poll_interval=0.8,
    dedupe=True,
):
    idx = 0
    seen = BoundedSet(maxlen=10000) if dedupe else None
    f = None
    inode = None
    first_open = True
    while not stop_event.is_set():
        if f is None:
            try:
                f = open(file_path, encoding="utf-8")
                try:
                    inode = os.fstat(f.fileno()).st_ino
                except Exception:
                    inode = None
                if first_open:
                    first_open = False
                    f.seek(0)
                    for line in f:
                        line = line.strip()
                        if not line:
                            idx += 1
                            continue
                        if seen is not None:
                            if line in seen:
                                idx += 1
                                continue
                            seen.add(line)
                        await queue.put((idx, line))
                        idx += 1
                    f.seek(0, os.SEEK_END)
                else:
                    f.seek(0, os.SEEK_END)
            except FileNotFoundError:
                await asyncio.sleep(poll_interval)
                continue
        line = f.readline()
        if not line:
            await asyncio.sleep(poll_interval)
            try:
                st = os.stat(file_path)
                if inode is not None and st.st_ino != inode:
                    try:
                        f.close()
                    except:
                        pass
                    f = open(file_path, encoding="utf-8")
                    inode = os.fstat(f.fileno()).st_ino
                    f.seek(0, os.SEEK_END)
                elif f.tell() > st.st_size:
                    f.seek(0, os.SEEK_END)
            except FileNotFoundError:
                try:
                    if f:
                        f.close()
                except:
                    pass
                f = None
                inode = None
            continue
        line = line.strip()
        if not line:
            continue
        if seen is not None:
            if line in seen:
                continue
            seen.add(line)
        await queue.put((idx, line))
        idx += 1
    try:
        if f:
            f.close()
    except:
        pass


async def once_producer(file_path: str, queue: asyncio.Queue):
    idx = 0
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    idx += 1
                    continue
                await queue.put((idx, line))
                idx += 1
    except FileNotFoundError:
        return


_BG_THREAD_TASKS: set = set()


async def run_in_thread(fn, *args, **kwargs):
    coro = asyncio.to_thread(fn, *args, **kwargs)
    task = asyncio.create_task(coro)
    _BG_THREAD_TASKS.add(task)
    try:
        return await task
    finally:
        _BG_THREAD_TASKS.discard(task)


def close_aiohttp_session_sync(sess):
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(sess.close(), loop)
            try:
                fut.result(timeout=5)
            except:
                pass
        else:
            newloop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(newloop)
                newloop.run_until_complete(sess.close())
            finally:
                try:
                    newloop.close()
                except:
                    pass
    except:
        try:
            sess.close()
        except:
            pass


async def worker(worker_id: int, base_blu: solflarekingdom, queue: asyncio.Queue):
    blu = solflarekingdom(
        use_proxy=base_blu.config.get("proxy", False),
        proxy_list=base_blu.proxy_list,
        load_on_init=False,
    )
    real_thread = int(base_blu.config.get("__real_thread_workers", 1))
    blu.executor = base_blu.shared_executor
    blu.log("🔁 Worker using shared executor", Fore.CYAN)
    try:
        blu.query_list = list(base_blu.query_list)
    except Exception:
        blu.query_list = []
    blu.log(f"👷 Worker-{worker_id} started | threads={real_thread}", Fore.CYAN)
    account_io_sema = getattr(
        base_blu, "blocking_sema", asyncio.Semaphore(max(1, real_thread))
    )
    while True:
        try:
            original_index, account = await queue.get()
        except asyncio.CancelledError:
            break
        account_label = f"W{worker_id}-A{original_index + 1}"
        try:
            await process_account(
                account, original_index, account_label, blu, account_io_sema
            )
        except Exception as e:
            blu.log(f"❌ {account_label} error: {e}", Fore.RED)
        finally:
            try:
                queue.task_done()
            except Exception:
                pass
    base_blu.log(f"🧾 Worker-{worker_id} stopped", Fore.CYAN)
    try:
        await run_in_thread(blu.close)
    except Exception:
        pass


def estimate_network_latency(host="1.1.1.1", port=53, attempts=2, timeout=0.6):
    latencies = []
    for _ in range(attempts):
        try:
            t0 = time.time()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            latencies.append(time.time() - t0)
        except Exception:
            latencies.append(timeout)
    try:
        return statistics.median(latencies)
    except:
        return timeout


def auto_tune_config_respecting_thread(
    existing_cfg: dict | None = None, prefer_network_check: bool = True
) -> dict:
    cfg = dict(existing_cfg or {})
    try:
        phys = psutil.cpu_count(logical=False) or 1
        logical = psutil.cpu_count(logical=True) or phys
    except:
        phys = logical = 1
    try:
        total_mem_gb = psutil.virtual_memory().total / 1024**3
    except:
        total_mem_gb = 1.0
    try:
        disk_free_gb = shutil.disk_usage(os.getcwd()).free / 1024**3
    except:
        disk_free_gb = 1.0
    net_lat = estimate_network_latency() if prefer_network_check else 1.0
    user_thread = cfg.get("thread", None)
    if user_thread is None:
        if logical >= 8:
            rec_thread = min(32, logical * 2)
        else:
            rec_thread = max(1, logical)
    else:
        rec_thread = int(user_thread)
    if total_mem_gb < 1.0:
        per_t = 20
    elif total_mem_gb < 2.5:
        per_t = 75
    elif total_mem_gb < 8:
        per_t = 200
    else:
        per_t = 1000
    q_recommend = int(min(max(50, rec_thread * per_t), 1000))
    if total_mem_gb < 1 or phys <= 1:
        poll = 1.0
    elif net_lat < 0.05:
        poll = 0.2
    elif net_lat < 0.2:
        poll = 0.5
    else:
        poll = 0.8
    dedupe = bool(total_mem_gb < 2.0)
    run_mode = cfg.get("run_mode", "continuous")
    merged = dict(cfg)
    if "queue_maxsize" not in merged:
        merged["queue_maxsize"] = q_recommend
    if "poll_interval" not in merged:
        merged["poll_interval"] = poll
    if "dedupe" not in merged:
        merged["dedupe"] = dedupe
    if "run_mode" not in merged:
        merged["run_mode"] = run_mode
    merged["_autotune_meta"] = {
        "phys_cores": int(phys),
        "logical_cores": int(logical),
        "total_mem_gb": round(total_mem_gb, 2),
        "disk_free_gb": round(disk_free_gb, 2),
        "net_latency_s": round(net_lat, 3),
        "queue_recommendation": int(q_recommend),
        "poll_recommendation": float(poll),
    }
    return merged


async def dynamic_tuner_nonthread(
    base_blu, queue: asyncio.Queue, stop_event: asyncio.Event, interval=6.0
):
    base_blu.log("🤖 Tuner started (non-thread)", Fore.CYAN)
    while not stop_event.is_set():
        try:
            cpu = psutil.cpu_percent(interval=None)
            qsize = queue.qsize() if queue is not None else 0
            cur_q = int(base_blu.config.get("queue_maxsize", 200))
            cur_poll = float(base_blu.config.get("poll_interval", 0.8))
            cur_dedupe = bool(base_blu.config.get("dedupe", True))
            cap = max(50, cur_q)
            if qsize > 0.8 * cap and cpu < 85:
                new_q = min(cur_q * 2, 10000)
            elif qsize < 0.2 * cap and cur_q > 100:
                new_q = max(int(cur_q / 2), 50)
            else:
                new_q = cur_q
            if cpu > 80:
                new_poll = min(cur_poll + 0.2, 2.0)
            elif cpu < 30 and qsize > 0.2 * cap:
                new_poll = max(cur_poll - 0.1, 0.1)
            else:
                new_poll = cur_poll
            vm = psutil.virtual_memory()
            if vm.available / 1024**2 < 200 and cur_dedupe:
                new_dedupe = False
            else:
                new_dedupe = cur_dedupe
            changed = []
            if new_q != cur_q:
                base_blu.config["queue_maxsize"] = int(new_q)
                changed.append(f"q:{cur_q}->{new_q}")
            if abs(new_poll - cur_poll) > 0.01:
                base_blu.config["poll_interval"] = float(round(new_poll, 3))
                changed.append(f"p:{cur_poll}->{round(new_poll, 3)}")
            if new_dedupe != cur_dedupe:
                base_blu.config["dedupe"] = bool(new_dedupe)
                changed.append(f"d:{cur_dedupe}->{new_dedupe}")
            if changed:
                base_blu.log("🔧 Tuner: " + ", ".join(changed), Fore.MAGENTA)
        except Exception:
            base_blu.log("⚠️ tuner error", Fore.YELLOW)
        await asyncio.sleep(interval)
    base_blu.log("🤖 Tuner stopped", Fore.MAGENTA)


async def producer_once(queue: asyncio.Queue, base_blu: solflarekingdom):
    idx = 0
    try:
        queries = base_blu.query_list
        if not queries:
            base_blu.log("⚠️ No queries to enqueue.", Fore.YELLOW)
            return
        for line in queries:
            if not line:
                idx += 1
                continue
            await queue.put((idx, line))
            idx += 1
        base_blu.log(f"📦 Enqueued {idx} queries total.", Fore.CYAN)
    except Exception as e:
        base_blu.log(f"❌ Producer error: {e}", Fore.RED)


def cleanup_after_batch(base_blu, keep_refs: dict | None = None, deep=False):
    try:
        try:
            for t in list(_BG_THREAD_TASKS):
                if getattr(t, "done", lambda: False)():
                    _BG_THREAD_TASKS.discard(t)
        except Exception:
            pass
        sess = getattr(base_blu, "session", None)
        if sess is not None:
            try:
                sess.cookies.clear()
            except Exception:
                pass
        if keep_refs is None:
            keep_refs = {}
        for k in ("last_items", "promo_data", "last_shop", "items_data"):
            if k not in keep_refs:
                try:
                    setattr(base_blu, k, None)
                except Exception:
                    pass
        if deep:
            for name in list(vars(base_blu).keys()):
                if name.startswith("_") or name in (
                    "logger",
                    "log",
                    "session",
                    "config",
                ):
                    continue
                try:
                    setattr(base_blu, name, None)
                except Exception:
                    pass
        try:
            gc.collect()
        except Exception:
            pass
        try:
            pm = getattr(base_blu, "proxy_manager", None)
            if pm:
                snap = pm.snapshot()
                if snap.get("in_use", 0) > 0:
                    base_blu.log(
                        f"⚠️ cleanup: {snap['in_use']} proxies still in-use; snapshot={snap}",
                        Fore.YELLOW,
                    )
        except Exception:
            pass
        try:
            CLEAN_ALLOW = (
                "requests",
                "urllib3",
                "aiohttp",
                "websocket",
                "brotli",
                "gzip",
                "zlib",
                "chardet",
                "fake_useragent",
                "psutil",
            )
            CORE_BLOCKLIST = (
                "asyncio",
                "concurrent",
                "threading",
                "socket",
                "os",
                "sys",
                "time",
                "gc",
                "json",
                "queue",
                "statistics",
                "inspect",
                "traceback",
                "datetime",
                "random",
                "signal",
                "shutil",
                "tracemalloc",
                "collections",
            )
            for name, module in list(sys.modules.items()):
                if name.startswith(CORE_BLOCKLIST):
                    continue
                if any(p in name for p in CLEAN_ALLOW):
                    try:
                        del sys.modules[name]
                    except Exception:
                        pass
                else:
                    try:
                        attrs = dir(module)
                        if (
                            "HTTPConnection" in attrs
                            or "HTTPSConnection" in attrs
                            or "PoolManager" in attrs
                            or ("ClientSession" in attrs)
                            or ("WebSocketClientProtocol" in attrs)
                        ):
                            try:
                                del sys.modules[name]
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            gc.collect()
            gc.collect()
        except Exception:
            pass
        try:
            emoji = random.choice(["🧹", "♻️", "🧽", "🌀", "🚿"])
            base_blu.log(
                f"{emoji} cleanup done | {base_blu.memory_monitor()}",
                Fore.LIGHTBLACK_EX,
            )
        except Exception:
            pass
    except Exception as e:
        try:
            base_blu.log(f"⚠️ cleanup error: {e}", Fore.YELLOW)
        except Exception:
            pass


async def main():
    base_blu = solflarekingdom()
    cfg_file = base_blu.config
    effective = auto_tune_config_respecting_thread(cfg_file)
    run_mode = "repeat"
    base_blu.config = effective
    base_blu.log(
        f"🎉 [LIVEXORDS] === Welcome to {NAME_BOT} Automation === [LIVEXORDS]",
        Fore.YELLOW,
    )
    cfg_summary = {
        "thread": int(effective.get("thread", 1)),
        "queue_maxsize": int(effective.get("queue_maxsize", 200)),
        "poll_interval": float(effective.get("poll_interval", 0.8)),
        "dedupe": bool(effective.get("dedupe", True)),
        "delay_loop": int(effective.get("delay_loop", 30)),
        "delay_account_switch": int(effective.get("delay_account_switch", 10)),
        "proxy": bool(effective.get("proxy", False)),
    }
    base_blu.log("")
    base_blu.log("🔧 Effective config:", Fore.CYAN)
    for k, v in cfg_summary.items():
        base_blu.log(f"    • {k:<20}: {v}", Fore.CYAN)
    base_blu.log("📊 Autotune metadata:", Fore.MAGENTA)
    meta = effective.get("_autotune_meta", {})
    for k, v in meta.items():
        base_blu.log(f"    • {k:<20}: {v}", Fore.MAGENTA)
    query_file = effective.get("query_file", "query.txt")
    queue_maxsize = int(effective.get("queue_maxsize", 200))
    poll_interval = float(effective.get("poll_interval", 0.8))
    dedupe = bool(effective.get("dedupe", True))
    max_async = int(effective.get("maxasync", 5))
    max_thread = int(effective.get("maxthread", 1))
    try:
        logical = max(1, int(psutil.cpu_count(logical=True) or 1))
    except Exception:
        logical = 1
    real_async_workers = min(max_async, max(1, logical * 2))
    thread_budget = max(1, int(max_thread))
    base_per_worker = thread_budget // real_async_workers
    remainder = thread_budget - base_per_worker * real_async_workers
    if base_per_worker < 1:
        base_per_worker = 1
        remainder = 0
    threads_per_worker = base_per_worker + (1 if remainder > 0 else 0)
    base_blu.config["__real_thread_workers"] = int(threads_per_worker)
    base_blu.log(
        f"🔢 workers={real_async_workers} | threads_total_budget={thread_budget} | threads_per_worker≈{threads_per_worker} | logical={logical}",
        Fore.MAGENTA,
    )
    shared_executor = _cf.ThreadPoolExecutor(max_workers=max(1, thread_budget))
    base_blu.shared_executor = shared_executor
    base_blu.blocking_sema = asyncio.Semaphore(max(1, thread_budget))
    base_blu.log(
        f"🔒 Shared executor created | max_workers={thread_budget} | blocking_sema={thread_budget}",
        Fore.MAGENTA,
    )
    base_blu.banner()
    base_blu.log(f"📂 {query_file} | q={queue_maxsize} | mode={run_mode}", Fore.YELLOW)
    stop_event = asyncio.Event()
    try:
        loop = asyncio.get_running_loop()
        global _MAIN_LOOP
        try:
            _MAIN_LOOP = loop
        except Exception:
            pass
        try:
            loop.add_signal_handler(signal.SIGINT, lambda: stop_event.set())
            loop.add_signal_handler(signal.SIGTERM, lambda: stop_event.set())
        except Exception:
            pass
    except Exception:
        pass
    while True:
        try:
            base_blu.query_list = base_blu.load_query(
                base_blu.config.get("query_file", query_file)
            )
        except Exception:
            base_blu.query_list = base_blu.load_query(query_file)
        queue = asyncio.Queue(maxsize=queue_maxsize)
        tuner_task = asyncio.create_task(
            dynamic_tuner_nonthread(base_blu, queue, stop_event)
        )
        prod_task = asyncio.create_task(producer_once(queue, base_blu))
        workers = [
            asyncio.create_task(worker(i + 1, base_blu, queue))
            for i in range(real_async_workers)
        ]
        try:
            await prod_task
            await queue.join()
        except asyncio.CancelledError:
            pass
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        tuner_task.cancel()
        try:
            await tuner_task
        except:
            pass
        await asyncio.sleep(0.05)
        known_tasks = set()
        known_tasks.add(tuner_task)
        known_tasks.add(prod_task)
        for w in workers:
            known_tasks.add(w)
        for t in _BG_THREAD_TASKS:
            known_tasks.add(t)
        pending = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task()
            and t not in known_tasks
            and (not t.done())
        ]
        if pending:
            for t in pending:
                try:
                    t.cancel()
                except Exception:
                    pass
            await asyncio.gather(*pending, return_exceptions=True)
        if _BG_THREAD_TASKS:
            base_blu.log(
                f"⏳ waiting for {len(_BG_THREAD_TASKS)} background thread(s) to finish...",
                Fore.CYAN,
            )
            await asyncio.gather(*list(_BG_THREAD_TASKS), return_exceptions=True)
        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            cleanup_after_batch(base_blu)
        except Exception:
            pass
        try:
            prod_task = None
            workers = None
            queue = None
        except Exception:
            pass
        base_blu.log("🔁 batch done", Fore.CYAN)
        base_blu.log(f"🧾 {base_blu.memory_monitor()}", Fore.MAGENTA)
        delay_loop = int(effective.get("delay_loop", 30))
        base_blu.log(f"⏳ sleep {delay_loop}s before next batch", Fore.CYAN)
        for _ in range(delay_loop):
            if stop_event.is_set():
                break
            await asyncio.sleep(1)
        if stop_event.is_set():
            break
    stop_event.set()
    shared = getattr(base_blu, "shared_executor", None)
    if shared is not None:
        base_blu.log("⏹ Shutting down shared executor...", Fore.MAGENTA)
        try:
            shared.shutdown(wait=True)
        except Exception:
            pass
    session = getattr(base_blu, "session", None)
    if session is not None:
        try:
            if not session.closed:
                await session.close()
        except Exception:
            pass
    base_blu.log("✅ shutdown", Fore.MAGENTA)


async def launcher():
    try:
        await main()
    except Exception as e:
        print("Error:", e)
    finally:
        print("🔥 ensuring clean shutdown...")


if __name__ == "__main__":
    try:
        asyncio.run(launcher())
    except KeyboardInterrupt:
        print("Interrupted by user. Bye!")
