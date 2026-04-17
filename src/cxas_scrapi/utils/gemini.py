import logging
from typing import Optional, Any
from google import genai

logger = logging.getLogger(__name__)

class GeminiGenerate:
    """A wrapper for the Gemini client to generate content."""

    def __init__(
        self,
        project_id: str,
        location: str = "global",
        credentials=None,
        model_name: str = "gemini-3.1-flash-lite-preview",
    ):
        """Initializes the GeminiGenerate client.

        Args:
            project_id: Google Cloud project ID.
            location: Vertex AI location. Defaults to 'global'.
            credentials: Optional Google Cloud credentials.
            model_name: The Gemini model name to use. Defaults to
              'gemini-3.1-flash-lite-preview'.
        """
        self.model_name = model_name
        logger.info(
            f"Initializing GeminiGenerate with model: {self.model_name}"
        )
        self.client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
            credentials=credentials,
        )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_name: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Any] = None,
    ) -> Optional[Any]:
        """Generates content using the Gemini model.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt/instruction.
            model_name: Optional override for the model name.
            response_mime_type: Optional MIME type for the response (e.g.,
              'application/json').
            response_schema: Optional Pydantic model or schema for structured
              output.

        Returns:
            The generated text response or parsed object, or None on failure.
        """
        target_model = model_name or self.model_name
        
        config_args = {}
        if system_prompt:
            config_args["system_instruction"] = system_prompt
        if response_mime_type:
            config_args["response_mime_type"] = response_mime_type
        if response_schema:
            config_args["response_schema"] = response_schema

        config = None
        if config_args:
            config = genai.types.GenerateContentConfig(**config_args)

        try:
            response = self.client.models.generate_content(
                model=target_model, contents=prompt, config=config
            )
            
            if response_mime_type == "application/json" and response_schema:
                return response.parsed
            return response.text
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            return None
