"""Search API validation and bounded retries for explicit proxy pools."""
import asyncio
import logging

import pytest

from ominis_src import tools_handler


@pytest.mark.asyncio
@pytest.mark.parametrize("pool", [[], [""], ["ftp://localhost:8080"],
                                  ["127.0.0.1:8080", "invalid"], "127.0.0.1:8080"])
@pytest.mark.parametrize("api", ["duckduckgo", "bing", "dual"])
async def test_search_apis_propagate_invalid_proxy_pools(pool, api, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        if api == "dual":
            await tools_handler.fetch_dual_engine_results("proxy-test", proxies=pool)
        else:
            await tools_handler.fetch_engine_results(api, "proxy-test", proxies=pool)
    assert not (tmp_path / "Results").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit,expected_attempts", [(True, 3), (False, 4)])
async def test_retry_limit_depends_on_explicit_pool(servers, monkeypatch, explicit, expected_attempts):
    origin = await servers.origin()
    proxy = await servers.http_proxy(reject_reason="unavailable")
    monkeypatch.setattr(tools_handler, "MAX_RETRY_COUNT", 4)
    monkeypatch.setenv("HTTP_PROXY", proxy.url)
    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr(tools_handler.asyncio, "sleep", fast_sleep)
    with pytest.raises(RuntimeError, match="Request failed"):
        await tools_handler.make_request_async(origin.url, [proxy.url] if explicit else None)
    assert len(proxy.requests) == expected_attempts
    assert origin.connections == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["stalled", "backoff"])
async def test_explicit_proxy_budget_includes_requests_and_backoff(servers, monkeypatch, failure):
    origin = await servers.origin()

    async def stall(reader, writer, endpoint):
        endpoint.requests.append(await reader.readuntil(b"\r\n\r\n"))
        # Accept the request but send no response; stop when the client disconnects.
        await reader.read()

    proxy = (await servers.start(stall) if failure == "stalled"
             else await servers.http_proxy(reject_reason="unavailable"))
    monkeypatch.setattr(tools_handler, "MAX_RETRY_COUNT", 20)
    monkeypatch.setattr(tools_handler, "PROXY_REQUEST_TIMEOUT", 0.2, raising=False)
    started = asyncio.get_running_loop().time()
    with pytest.raises(RuntimeError, match="Request failed"):
        await asyncio.wait_for(tools_handler.make_request_async(origin.url, [proxy.url]), timeout=2)
    assert asyncio.get_running_loop().time() - started < 1.5
    assert len(proxy.requests) == 1
    assert origin.connections == 0


@pytest.mark.asyncio
async def test_proxy_display_prompt_does_not_consume_retry_budget(servers, monkeypatch):
    origin = await servers.origin()
    proxy = await servers.http_proxy()
    monkeypatch.setattr(tools_handler, "show_message", None)
    monkeypatch.setattr(tools_handler, "PROXY_REQUEST_TIMEOUT", 0.5)

    async def delayed_answer():
        await asyncio.sleep(0.6)
        return False

    monkeypatch.setattr(tools_handler, "ask_to_show_message", delayed_answer)
    assert await tools_handler.make_request_async(origin.url, [proxy.url]) == "local response"
    assert len(proxy.requests) == 1


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_through_proxy_budget(servers):
    origin = await servers.origin()
    connected = asyncio.Event()

    async def stall(reader, writer, endpoint):
        endpoint.requests.append(await reader.readuntil(b"\r\n\r\n"))
        connected.set()
        await reader.read()

    proxy = await servers.start(stall)
    request = asyncio.create_task(tools_handler.make_request_async(origin.url, [proxy.url]))
    try:
        await asyncio.wait_for(connected.wait(), timeout=2)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(request, timeout=2)
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
    assert origin.connections == 0


@pytest.mark.asyncio
async def test_recoverable_search_failures_still_return_empty_results(monkeypatch, caplog):
    async def invalid_response(url, proxies):
        raise RuntimeError("temporary search failure")

    monkeypatch.setattr(tools_handler, "make_request_async", invalid_response)
    with caplog.at_level(logging.ERROR, logger=tools_handler.__name__):
        assert await tools_handler.fetch_engine_results("bing", "proxy-test") == []
    assert "temporary search failure" in caplog.text
