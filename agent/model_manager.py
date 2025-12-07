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
            self.gemini_api_url = os.getenv("GEMINI_API_URL")
            if not self.gemini_api_url:
                model_name = self.model_info.get("model", "gemini-2.0-flash")
                self.gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        
        # OpenAI API configuration
        elif self.model_type == "openai":
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
            self.openai_model = self.model_info.get("model", "gpt-4o-mini")
        
        # Groq API configuration
        elif self.model_type == "groq":
            self.groq_api_key = os.getenv("GROQ_API_KEY")
            self.groq_model = self.model_info.get("model", "llama-3.1-8b-instant")

    async def generate_text(self, prompt: str) -> str:
        if self.model_type == "gemini":
            return await self._gemini_generate(prompt)
        elif self.model_type == "openai":
            return await self._openai_generate(prompt)
        elif self.model_type == "groq":
            return await self._groq_generate(prompt)
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

    async def _openai_generate(self, prompt: str) -> str:
        """Generate text using OpenAI API"""
        try:
            url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": self.openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4096
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.openai_api_key}"
                    },
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"OpenAI API error {response.status}: {error_text}")
                    
                    result = await response.json()
                    return result["choices"][0]["message"]["content"].strip()
                    
        except aiohttp.ClientError as e:
            raise RuntimeError(f"OpenAI connection error: {type(e).__name__}: {str(e)}")
        except Exception as e:
            if "RuntimeError" in str(type(e)):
                raise
            raise RuntimeError(f"OpenAI generation failed: {type(e).__name__}: {str(e)}")

    async def _groq_generate(self, prompt: str, retry_count: int = 0) -> str:
        """Generate text using Groq API (free tier available) with auto-retry for rate limits"""
        import asyncio
        import re
        
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            
            # Truncate prompt if too long (to reduce token usage)
            max_prompt_chars = 12000  # ~3000 tokens
            if len(prompt) > max_prompt_chars:
                prompt = prompt[:max_prompt_chars] + "\n\n[TRUNCATED - respond based on available context]"
            
            payload = {
                "model": self.groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 1024  # Reduced further to avoid rate limits
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.groq_api_key}"
                    },
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 429 and retry_count < 5:
                        # Rate limit - extract wait time and retry
                        error_text = await response.text()
                        wait_match = re.search(r'try again in (\d+\.?\d*)s', error_text)
                        wait_time = float(wait_match.group(1)) if wait_match else 30
                        wait_time = min(wait_time + 5, 60)  # Add buffer, cap at 60s
                        print(f"    [RATE LIMIT] Waiting {wait_time:.1f}s before retry ({retry_count+1}/5)...")
                        await asyncio.sleep(wait_time)
                        return await self._groq_generate(prompt, retry_count + 1)
                    
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Groq API error {response.status}: {error_text}")
                    
                    result = await response.json()
                    return result["choices"][0]["message"]["content"].strip()
                    
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Groq connection error: {type(e).__name__}: {str(e)}")
        except Exception as e:
            if "RuntimeError" in str(type(e)):
                raise
            raise RuntimeError(f"Groq generation failed: {type(e).__name__}: {str(e)}")

    async def _ollama_generate(self, prompt: str) -> str:
        """Generate text using Ollama (local)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.model_info["url"]["generate"],
                    json={"model": self.model_info["model"], "prompt": prompt, "stream": False},
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 min timeout for local models
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Ollama error {response.status}: {error_text}")
                    result = await response.json()
                    return result["response"].strip()
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Ollama connection error: {type(e).__name__}: {str(e)}")
        except Exception as e:
            if "RuntimeError" in str(type(e)):
                raise
            raise RuntimeError(f"Ollama generation failed: {type(e).__name__}: {str(e)}")
