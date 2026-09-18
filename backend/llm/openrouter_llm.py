"""
OpenRouter LLM Client
Uses OpenAI SDK format to communicate with OpenRouter API
"""
import os
import time
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

class OpenRouterLLM:
    def __init__(self, api_key: str = None, model_name: str = "anthropic/claude-3.5-sonnet", max_tokens: int = 2000, temperature: float = 0.7):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.error("OpenRouter API key not provided or found in environment variables.")
            raise ValueError("OpenRouter API key not provided or found in environment variables.")

        try:
            # OpenRouter uses OpenAI SDK format
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            logger.info(f"OpenRouterLLM initialized with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter client: {e}", exc_info=True)
            raise

        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature

    def _build_messages(self, prompt: str, system_message: str = None) -> list:
        """Build OpenAI-format messages array."""
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(self, prompt: str, system_message: str = None) -> str:
        logger.debug(f"Generating text with model {self.model_name}, prompt (first 50 chars): {prompt[:50]}")
        try:
            messages = self._build_messages(prompt, system_message)

            # Call OpenRouter using OpenAI SDK format
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            # Extract content from OpenAI-style response
            content = response.choices[0].message.content
            if content is None:
                logger.warning("OpenRouter API returned None content.")
                raise RuntimeError("OpenRouter API returned no content")
            return content.strip()

        except Exception as e:
            # Raise instead of returning the error text as content — callers that
            # persist the reply (e.g. lesson chat) must never store an error
            # string as if it were the assistant's answer.
            logger.error(f"Error calling OpenRouter API: {e}", exc_info=True)
            raise

    def generate_stream(self, prompt: str, system_message: str = None):
        """
        Generate streaming response, yielding tokens as they arrive.
        Used for real-time chat display like ChatGPT/Claude.
        """
        logger.debug(f"Streaming text with model {self.model_name}, prompt (first 50 chars): {prompt[:50]}")
        try:
            # Build messages array (OpenAI format)
            messages = []

            # Add system message if provided
            if system_message:
                messages.append({"role": "system", "content": system_message})

            # Add user prompt
            messages.append({"role": "user", "content": prompt})

            # Call OpenRouter with streaming enabled
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True  # Enable streaming
            )

            # Yield each token as it arrives
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Error in streaming OpenRouter API: {e}", exc_info=True)
            yield f"Error: OpenRouter API issue - {e}"

    def generate_stream_with_retry(self, prompt: str, system_message: str = None, max_retries: int = 2):
        """
        Streaming with automatic retry and non-streaming fallback.
        On transient errors, retries streaming up to max_retries times.
        If all streaming attempts fail, falls back to non-streaming generate().
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                messages = self._build_messages(prompt, system_message)
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    stream=True
                )
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return  # Stream completed successfully
            except Exception as e:
                last_error = e
                logger.warning(f"Streaming attempt {attempt + 1}/{max_retries + 1} failed: {e}")
                if attempt < max_retries:
                    time.sleep(1 * (attempt + 1))
                    continue

        # All streaming retries exhausted — fall back to non-streaming
        logger.info("All streaming retries failed, falling back to non-streaming request")
        try:
            result = self.generate(prompt, system_message)
            if not result.startswith("Error:"):
                yield result
                return
        except Exception as fallback_err:
            logger.error(f"Non-streaming fallback also failed: {fallback_err}", exc_info=True)

        yield f"Error: OpenRouter API issue - {last_error}"

    async def agenerate(self, prompt: str, system_message: str = None) -> str:
        # Basic async wrapper - for true async, would need AsyncOpenAI client
        logger.debug(f"Async generating text with model {self.model_name}, prompt (first 50 chars): {prompt[:50]}")
        # This is NOT truly async with the synchronous client.
        # For simplicity in this placeholder, we call the synchronous one.
        return self.generate(prompt, system_message)
