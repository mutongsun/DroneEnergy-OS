"""DeepSeekClient 熔断器行为测试（不发起真实网络请求）"""

from app.ai.client import DeepSeekClient


async def test_circuit_opens_after_consecutive_failures() -> None:
    client = DeepSeekClient(api_key="test-key", failure_threshold=3, cooldown_seconds=60.0)
    calls = {"count": 0}

    async def _failing_create(messages: list[dict[str, str]]) -> str:
        calls["count"] += 1
        raise RuntimeError("network down")

    client._create_completion = _failing_create  # type: ignore[method-assign]

    for _ in range(3):
        result = await client.chat({"soc": 80}, "策略?")
        assert result["action"] == "fallback"
    assert calls["count"] == 3

    # 第 4 次：熔断已开启，直接降级，不再外呼
    result = await client.chat({"soc": 80}, "策略?")
    assert result["action"] == "fallback"
    assert calls["count"] == 3


async def test_success_resets_failure_counter() -> None:
    client = DeepSeekClient(api_key="test-key", failure_threshold=3, cooldown_seconds=60.0)
    state = {"calls": 0}

    async def _flaky_create(messages: list[dict[str, str]]) -> str:
        state["calls"] += 1
        if state["calls"] <= 2:
            raise RuntimeError("network down")
        return '{"action": "normal", "params": {}, "reason": "ok"}'

    client._create_completion = _flaky_create  # type: ignore[method-assign]

    assert (await client.chat({}, "q"))["action"] == "fallback"
    assert (await client.chat({}, "q"))["action"] == "fallback"
    assert (await client.chat({}, "q"))["action"] == "normal"

    # 成功后失败计数清零，不会因历史失败累积触发熔断
    assert client._consecutive_failures == 0
    assert client._circuit_opened_at is None
