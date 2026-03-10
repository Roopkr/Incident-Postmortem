import os
import logging

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class LLMFactory:
    def __init__(self, model: str = "gpt-4.1-nano", temperature: float = 0.2) -> None:
        self.model = model
        self.temperature = temperature

    def _load_environment(self) -> None:
        if not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            load_dotenv()
            logger.debug("Environment loaded from .env for local execution")

    def get_llm(self) -> ChatOpenAI:
        self._load_environment()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY is missing; cannot initialize LLM client")
            raise ValueError(
                "OPENAI_API_KEY is missing. Add it to your .env file for local development "
                "or configure it in AWS Lambda environment variables for production."
            )

        logger.info("Initializing ChatOpenAI model=%s temperature=%s", self.model, self.temperature)
        return ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            api_key=api_key,
        )
