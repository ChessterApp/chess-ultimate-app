"""
LLM Session Manager - Handles multi-tenant LLM request execution

This service manages concurrent LLM requests from multiple users with:
- Connection pooling (shared LLM client)
- Request queuing (per-user fairness)
- Concurrency control (global and per-user limits)
- Error handling and retries
- Usage tracking
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime
import os

# Import LLM clients
from llm.openrouter_llm import OpenRouterLLM
from llm.anthropic_llm import AnthropicLLM

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """Represents a single LLM request"""
    user_id: str
    fen: str
    query: str
    conversation_id: str
    context: list  # Previous messages for context
    priority: int = 0  # Higher = more important (for future use)
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


@dataclass
class LLMResponse:
    """Represents an LLM response with metadata"""
    content: str
    tokens_used: int
    response_time_ms: float
    model: str
    success: bool
    error: Optional[str] = None


class LLMSessionManager:
    """
    Manages LLM client connections and request execution for multiple users.

    Features:
    - Shared LLM client (connection pooling)
    - Global concurrency limit (prevents server overload)
    - Per-user concurrency limit (fairness)
    - Async execution with semaphores
    - Request timeout handling
    - Retry logic with exponential backoff
    """

    # Configuration
    MAX_GLOBAL_CONCURRENT = 50  # Max concurrent requests across all users
    MAX_USER_CONCURRENT = 3     # Max concurrent requests per user
    REQUEST_TIMEOUT = 30        # Seconds
    MAX_RETRIES = 3

    def __init__(self):
        """Initialize the LLM session manager"""
        # Shared LLM client (via OpenRouter or direct Anthropic fallback)
        self.llm_client = None
        # Use OpenRouter model naming convention - read from env or default to Gemini 3 Flash
        self.model_name = os.getenv("PRIMARY_MODEL", "google/gemini-3-flash-preview")

        # Concurrency controls
        self.global_semaphore = asyncio.Semaphore(self.MAX_GLOBAL_CONCURRENT)
        self.user_semaphores: Dict[str, asyncio.Semaphore] = {}

        # Tracking
        self.active_requests = 0
        self.user_request_counts: Dict[str, int] = {}
        self.total_requests_processed = 0
        self.total_errors = 0

        # Initialize LLM client
        self._initialize_llm_client()

        logger.info(
            f"LLM Session Manager initialized: "
            f"global_limit={self.MAX_GLOBAL_CONCURRENT}, "
            f"user_limit={self.MAX_USER_CONCURRENT}"
        )

    def _initialize_llm_client(self):
        """Initialize the shared LLM client"""
        try:
            # Try OpenRouter first (preferred), fallback to direct Anthropic
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")

            if openrouter_key:
                # Use OpenRouter (OpenAI-compatible format)
                self.llm_client = OpenRouterLLM(
                    api_key=openrouter_key,
                    model_name=self.model_name,
                    max_tokens=2000,
                    temperature=0.7
                )
                logger.info(f"LLM client initialized (OpenRouter): model={self.model_name}")
            elif anthropic_key:
                # Fallback to direct Anthropic API
                fallback_model = os.getenv("FALLBACK_MODEL", "claude-3-5-sonnet-20241022")
                self.llm_client = AnthropicLLM(
                    api_key=anthropic_key,
                    model_name=fallback_model,
                    max_tokens=2000,
                    temperature=0.7
                )
                logger.info(f"LLM client initialized (direct Anthropic): model={fallback_model}")
            else:
                raise ValueError("No LLM API key found (neither OPENROUTER_API_KEY nor ANTHROPIC_API_KEY)")

        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}", exc_info=True)
            raise

    def _get_user_semaphore(self, user_id: str) -> asyncio.Semaphore:
        """Get or create semaphore for user (max concurrent per user)"""
        if user_id not in self.user_semaphores:
            self.user_semaphores[user_id] = asyncio.Semaphore(self.MAX_USER_CONCURRENT)
        return self.user_semaphores[user_id]

    def _build_system_prompt(self, fen: str, context_type: str = "analysis") -> str:
        """Build system prompt for chess analysis"""
        if context_type == "position":
            return f"""You are an expert chess coach analyzing a position.

Current position (FEN): {fen}

Provide clear, insightful analysis focusing on:
- Key features of the position
- Piece activity and coordination
- Pawn structure strengths/weaknesses
- Tactical opportunities
- Strategic plans for both sides

Be encouraging and educational. Explain concepts clearly for intermediate players."""

        elif context_type == "game":
            return f"""You are an expert chess coach reviewing a game.

Current position (FEN): {fen}

Provide constructive feedback focusing on:
- Critical moments in the game
- Missed opportunities
- Strategic themes
- Tactical patterns
- Suggestions for improvement

Be supportive and focus on learning opportunities."""

        else:  # general analysis
            return f"""You are a knowledgeable and friendly chess coach.

Current position (FEN): {fen}

Answer the user's questions about this chess position clearly and helpfully.
Use chess notation when discussing moves. Be encouraging and educational."""

    def _format_context_messages(self, context: list) -> list:
        """Format context messages for Anthropic API"""
        messages = []
        for msg in context[-10:]:  # Last 10 messages max
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        return messages

    async def _execute_llm_call(self, request: LLMRequest) -> LLMResponse:
        """Execute the actual LLM API call"""
        start_time = time.time()

        try:
            # Build system prompt
            system_prompt = self._build_system_prompt(
                request.fen,
                request.context[0].get("context_type", "analysis") if request.context else "analysis"
            )

            # Format messages
            messages = self._format_context_messages(request.context)

            # Add current query
            messages.append({
                "role": "user",
                "content": request.query
            })

            # Call LLM (synchronous, so wrap in asyncio.to_thread)
            response_content = await asyncio.to_thread(
                self.llm_client.generate,
                prompt=request.query,
                system_message=system_prompt
            )

            # Calculate metrics
            response_time_ms = (time.time() - start_time) * 1000

            # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
            tokens_used = len(request.query + response_content) // 4

            logger.info(
                f"LLM request completed: user={request.user_id[:8]}..., "
                f"time={response_time_ms:.0f}ms, tokens≈{tokens_used}"
            )

            return LLMResponse(
                content=response_content,
                tokens_used=tokens_used,
                response_time_ms=response_time_ms,
                model=self.model_name,
                success=True
            )

        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            logger.error(
                f"LLM request failed: user={request.user_id[:8]}..., "
                f"error={str(e)}", exc_info=True
            )

            return LLMResponse(
                content="",
                tokens_used=0,
                response_time_ms=response_time_ms,
                model=self.model_name,
                success=False,
                error=str(e)
            )

    async def execute_request(self, request: LLMRequest) -> LLMResponse:
        """
        Execute LLM request with concurrency control and retry logic.

        Args:
            request: LLMRequest object with user_id, query, context, etc.

        Returns:
            LLMResponse with content and metadata

        Raises:
            Exception: If request fails after all retries
        """
        user_semaphore = self._get_user_semaphore(request.user_id)

        logger.debug(
            f"Executing LLM request: user={request.user_id[:8]}..., "
            f"global_active={self.active_requests}/{self.MAX_GLOBAL_CONCURRENT}, "
            f"user_active={self.user_request_counts.get(request.user_id, 0)}/{self.MAX_USER_CONCURRENT}"
        )

        # Wait for both global and per-user capacity
        async with self.global_semaphore:
            async with user_semaphore:
                # Update tracking
                self.active_requests += 1
                self.user_request_counts[request.user_id] = \
                    self.user_request_counts.get(request.user_id, 0) + 1

                try:
                    # Retry logic with exponential backoff
                    last_error = None

                    for attempt in range(self.MAX_RETRIES):
                        try:
                            # Execute with timeout
                            response = await asyncio.wait_for(
                                self._execute_llm_call(request),
                                timeout=self.REQUEST_TIMEOUT
                            )

                            if response.success:
                                self.total_requests_processed += 1
                                return response
                            else:
                                last_error = response.error
                                if attempt < self.MAX_RETRIES - 1:
                                    wait_time = 2 ** attempt  # Exponential backoff
                                    logger.warning(
                                        f"LLM request failed (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                                        f"retrying in {wait_time}s: {last_error}"
                                    )
                                    await asyncio.sleep(wait_time)

                        except asyncio.TimeoutError:
                            last_error = "Request timed out"
                            if attempt < self.MAX_RETRIES - 1:
                                wait_time = 2 ** attempt
                                logger.warning(
                                    f"LLM request timeout (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                                    f"retrying in {wait_time}s"
                                )
                                await asyncio.sleep(wait_time)

                        except Exception as e:
                            last_error = str(e)
                            if attempt < self.MAX_RETRIES - 1:
                                wait_time = 2 ** attempt
                                logger.warning(
                                    f"LLM request error (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                                    f"retrying in {wait_time}s: {e}"
                                )
                                await asyncio.sleep(wait_time)

                    # All retries failed
                    self.total_errors += 1
                    error_msg = f"LLM request failed after {self.MAX_RETRIES} retries: {last_error}"
                    logger.error(error_msg)

                    return LLMResponse(
                        content="I apologize, but I'm having trouble generating a response right now. Please try again in a moment.",
                        tokens_used=0,
                        response_time_ms=0,
                        model=self.model_name,
                        success=False,
                        error=error_msg
                    )

                finally:
                    # Update tracking
                    self.active_requests -= 1
                    self.user_request_counts[request.user_id] -= 1

                    # Clean up empty counts
                    if self.user_request_counts[request.user_id] == 0:
                        del self.user_request_counts[request.user_id]

    def get_stats(self) -> dict:
        """Get current statistics"""
        return {
            "active_requests": self.active_requests,
            "total_processed": self.total_requests_processed,
            "total_errors": self.total_errors,
            "active_users": len(self.user_request_counts),
            "user_request_counts": dict(self.user_request_counts),
            "global_capacity": f"{self.active_requests}/{self.MAX_GLOBAL_CONCURRENT}",
            "model": self.model_name
        }


# Global singleton instance
_session_manager: Optional[LLMSessionManager] = None


def get_session_manager() -> LLMSessionManager:
    """Get or create the global LLM session manager instance"""
    global _session_manager
    if _session_manager is None:
        _session_manager = LLMSessionManager()
    return _session_manager
