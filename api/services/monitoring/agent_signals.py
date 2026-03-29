"""Agent-to-agent signal passing — the 4-agent closed-loop coordinator.

Manages the flow of structured signals between the 4 agents:
  Agent 1 (情报员/Intel) → Agent 2 (策略师/Strategist)
  Agent 2 (策略师) → Agent 3 (设计师/Designer)
  Agent 3 (设计师) → Agent 4 (数据科学家/Data Scientist)
  Agent 4 (数据科学家) → Agent 1 (情报员) [feedback loop]

Each signal is a structured JSON payload that one agent produces
and the next agent consumes to inform its decisions.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    intel = "intel"           # Agent 1: 情报员
    strategist = "strategist"  # Agent 2: 策略师
    designer = "designer"      # Agent 3: 设计师
    data_sci = "data_sci"      # Agent 4: 数据科学家


class SignalType(str, Enum):
    # Intel → Strategist
    competitor_intel = "competitor_intel"
    review_pain_points = "review_pain_points"
    keyword_opportunities = "keyword_opportunities"
    listing_changes = "listing_changes"
    seasonal_triggers = "seasonal_triggers"

    # Strategist → Designer
    visual_brief = "visual_brief"
    story_arc = "story_arc"
    ab_test_plan = "ab_test_plan"

    # Designer → Data Scientist
    assets_generated = "assets_generated"
    variant_batch = "variant_batch"

    # Data Scientist → Intel (feedback loop)
    performance_feedback = "performance_feedback"
    conversion_attribution = "conversion_attribution"
    roi_update = "roi_update"


@dataclass
class Signal:
    """A structured message passed between agents."""

    signal_id: str = ""
    signal_type: SignalType = SignalType.competitor_intel
    source_agent: AgentRole = AgentRole.intel
    target_agent: AgentRole = AgentRole.strategist
    payload: dict = field(default_factory=dict)
    created_at: str = ""
    consumed: bool = False
    consumed_at: str = ""
    asin: str = ""  # optional ASIN context
    job_id: str = ""  # optional job context


class SignalBus:
    """Central bus for agent-to-agent signal passing.

    The signal bus maintains a queue of signals between agents.
    Each agent can:
    1. Emit signals to the bus
    2. Consume pending signals addressed to it
    3. Query signal history for context

    Current status: In-memory implementation. Production needs:
    1. Persistent queue (Redis/Supabase)
    2. Webhook triggers for real-time agent activation
    3. Signal schema validation
    4. Dead letter queue for failed processing
    """

    # Valid signal routes (source → target)
    ROUTES: dict[AgentRole, AgentRole] = {
        AgentRole.intel: AgentRole.strategist,
        AgentRole.strategist: AgentRole.designer,
        AgentRole.designer: AgentRole.data_sci,
        AgentRole.data_sci: AgentRole.intel,
    }

    def __init__(self) -> None:
        self._signals: list[Signal] = []

    def emit(
        self,
        signal_type: SignalType,
        source: AgentRole,
        payload: dict,
        asin: str = "",
        job_id: str = "",
    ) -> Signal:
        """Emit a signal from one agent to the next in the loop."""
        target = self.ROUTES.get(source)
        if target is None:
            raise ValueError(f"Unknown source agent: {source}")

        signal = Signal(
            signal_id=str(uuid.uuid4())[:8],
            signal_type=signal_type,
            source_agent=source,
            target_agent=target,
            payload=payload,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            asin=asin,
            job_id=job_id,
        )
        self._signals.append(signal)
        logger.info(
            "Signal emitted: %s → %s [%s] (id=%s)",
            source.value, target.value, signal_type.value, signal.signal_id,
        )
        return signal

    def consume(
        self,
        agent: AgentRole,
        signal_type: SignalType | None = None,
        asin: str = "",
    ) -> list[Signal]:
        """Consume pending signals for an agent.

        Returns unconsumed signals addressed to this agent,
        optionally filtered by type and ASIN.
        Marks consumed signals so they won't be returned again.
        """
        pending = [
            s for s in self._signals
            if s.target_agent == agent
            and not s.consumed
            and (signal_type is None or s.signal_type == signal_type)
            and (not asin or s.asin == asin)
        ]

        now = datetime.now(tz=timezone.utc).isoformat()
        for signal in pending:
            signal.consumed = True
            signal.consumed_at = now

        if pending:
            logger.info(
                "Agent %s consumed %d signals",
                agent.value, len(pending),
            )
        return pending

    def peek(
        self,
        agent: AgentRole,
        signal_type: SignalType | None = None,
    ) -> list[Signal]:
        """Peek at pending signals without consuming them."""
        return [
            s for s in self._signals
            if s.target_agent == agent
            and not s.consumed
            and (signal_type is None or s.signal_type == signal_type)
        ]

    def get_history(
        self,
        agent: AgentRole | None = None,
        limit: int = 50,
    ) -> list[Signal]:
        """Return signal history, optionally filtered by agent."""
        signals = self._signals
        if agent:
            signals = [
                s for s in signals
                if s.source_agent == agent or s.target_agent == agent
            ]
        return signals[-limit:]

    def get_loop_status(self) -> dict:
        """Return the current state of the 4-agent loop."""
        pending_per_agent = {}
        for agent in AgentRole:
            pending = len([
                s for s in self._signals
                if s.target_agent == agent and not s.consumed
            ])
            pending_per_agent[agent.value] = pending

        return {
            "total_signals": len(self._signals),
            "pending_per_agent": pending_per_agent,
            "consumed": sum(1 for s in self._signals if s.consumed),
            "routes": {
                src.value: dst.value
                for src, dst in self.ROUTES.items()
            },
        }


# Module-level singleton
signal_bus = SignalBus()
