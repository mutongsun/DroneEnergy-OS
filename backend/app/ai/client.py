"""DeepSeek 客户端（v2 修正版）

v1 缺陷：在 async 路由里使用同步 OpenAI SDK——阻塞整个事件循环，
30 秒超时期间所有并发请求（包括 /metrics 抓取）一起卡死。
（该类问题可被 ruff 的 ASYNC 规则在 CI 阶段直接拦截。）

v2 修正：
1. AsyncOpenAI + await：请求挂起期间事件循环保持可服务
2. 连续失败熔断：达到阈值后开路，冷却期内直接走 fallback，
   不再把超时预算浪费在大概率失败的外呼上
3. 结构化契约：模型输出必须可解析为 JSON 才算成功
"""

import json
import logging
import os
import time
from typing import Any

from openai import AsyncOpenAI

from app.monitoring.metrics import AI_CALL_LATENCY, AI_CALLS_TOTAL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是无人机能源管理智能体“小电同学”。根据当前飞行状态给出能源分配策略、"
    "故障预警或航线优化建议。输出必须为 JSON："
    '{"action": "...", "params": {...}, "reason": "..."}'
)

FALLBACK_ACTION: dict[str, Any] = {
    "action": "fallback",
    "params": {},
    "reason": "AI 服务不可用，采用保守能源策略（热电优先、限速巡航）",
}


class DeepSeekClient:
    """异步客户端 + 简单熔断器（连续失败计数 + 冷却半开）"""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            timeout=timeout,
            max_retries=2,
        )
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

    # ---------- 熔断状态机 ----------

    def _circuit_open(self) -> bool:
        if self._circuit_opened_at is None:
            return False
        if time.monotonic() - self._circuit_opened_at >= self._cooldown_seconds:
            # 冷却结束 → 半开：放行一次真实调用重新探活
            self._circuit_opened_at = None
            self._consecutive_failures = 0
            return False
        return True

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_opened_at = None

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._circuit_opened_at = time.monotonic()
            logger.error(
                "ai_circuit_opened failures=%s cooldown=%ss",
                self._consecutive_failures,
                self._cooldown_seconds,
            )

    # ---------- 对外接口 ----------

    async def chat(self, flight_context: dict[str, Any], user_query: str) -> dict[str, Any]:
        """返回结构化决策；任何失败路径都降级为 fallback，绝不向上抛异常"""
        if self._circuit_open():
            AI_CALLS_TOTAL.labels("circuit_open").inc()
            return FALLBACK_ACTION

        with AI_CALL_LATENCY.time():
            try:
                raw = await self._create_completion(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": self._build_prompt(flight_context, user_query),
                        },
                    ]
                )
                parsed = json.loads(raw)  # 解析失败视为调用失败，走降级
                self._record_success()
                AI_CALLS_TOTAL.labels("ok").inc()
                return parsed
            except Exception as exc:  # 外部边界：超时/网络/解析错误统一降级
                self._record_failure()
                AI_CALLS_TOTAL.labels("error").inc()
                logger.warning("ai_call_failed: %s", exc)
                return FALLBACK_ACTION

    async def _create_completion(self, messages: list[dict[str, str]]) -> str:
        """真实模型调用（独立方法，便于单元测试替换为测试替身）"""
        # DeepSeek 兼容 OpenAI 协议；SDK 类型定义为 OpenAI 模型 Literal，忽略校验
        resp = await self._client.chat.completions.create(  # type: ignore[call-overload]
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return str(resp.choices[0].message.content)

    @staticmethod
    def _build_prompt(ctx: dict[str, Any], query: str) -> str:
        return (
            f"当前飞行状态：型号={ctx.get('model')}，SOC={ctx.get('soc')}%，"
            f"电池温度={ctx.get('battery_temp')}℃，电机温度={ctx.get('motor_temp')}℃，"
            f"自旋热电输出={ctx.get('thermal_power')}W，风速={ctx.get('wind_speed')}m/s，"
            f"飞行阶段={ctx.get('phase')}。\n用户问题：{query}\n请给出最优能源策略。"
        )
