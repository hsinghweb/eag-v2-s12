import asyncio
import aiohttp

async def test():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'http://localhost:11434/api/generate',
                json={'model': 'phi3:mini', 'prompt': 'Say hello in 5 words', 'stream': False}
            ) as response:
                result = await response.json()
                print("Success:", result.get('response', 'No response')[:100])
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

asyncio.run(test())

