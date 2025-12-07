import os
import json
import yaml
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
MODELS_JSON = ROOT / "config" / "models.json"
PROFILE_YAML = ROOT / "config" / "profiles.yaml"

class ModelManager:
    def __init__(self):
        self.config = json.loads(MODELS_JSON.read_text())
        self.profile = yaml.safe_load(PROFILE_YAML.read_text())

        self.text_model_key = self.profile["llm"]["text_generation"]
        self.model_info = self.config["models"][self.text_model_key]
        self.model_type = self.model_info["type"]

        # Gemini API configuration
        if self.model_type == "gemini":
            self.gemini_api_key = os.getenv("GEMINI_API_KEY")
            # Use GEMINI_API_URL if provided, otherwise construct default
            self.gemini_api_url = os.getenv("GEMINI_API_URL")
            if not self.gemini_api_url:
                model_name = self.model_info.get("model", "gemini-2.0-flash")
                self.gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

    async def generate_text(self, prompt: str) -> str:
        if self.model_type == "gemini":
            return await self._gemini_generate(prompt)

        elif self.model_type == "ollama":
            return await self._ollama_generate(prompt)

        raise NotImplementedError(f"Unsupported model type: {self.model_type}")

    async def _gemini_generate(self, prompt: str) -> str:
        """Generate text using Gemini REST API"""
        try:
            url = f"{self.gemini_api_url}?key={self.gemini_api_key}"
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 4096
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Gemini API error {response.status}: {error_text}")
                    
                    result = await response.json()
                    
                    # Extract text from response
                    candidates = result.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                    
                    raise RuntimeError(f"Unexpected Gemini response format: {result}")
                    
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Gemini connection error: {type(e).__name__}: {str(e)}")
        except Exception as e:
            if "RuntimeError" in str(type(e)):
                raise
            raise RuntimeError(f"Gemini generation failed: {type(e).__name__}: {str(e)}")

    async def _ollama_generate(self, prompt: str) -> str:
        try:
            # ✅ Use aiohttp for truly async requests
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.model_info["url"]["generate"],
                    json={"model": self.model_info["model"], "prompt": prompt, "stream": False}
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    return result["response"].strip()
        except Exception as e:
            raise RuntimeError(f"Ollama generation failed: {str(e)}")
