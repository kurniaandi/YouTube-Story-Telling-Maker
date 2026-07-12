import json
import time
from pathlib import Path
from openai import OpenAI


class MultiProviderKeyRotator:
    """
    Rotasi API key multi-provider (Groq, Cerebras, SambaNova, dll).
    Setiap provider punya base_url + model-nya masing-masing.
    """

    def __init__(self, config_path="my_config.json"):
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"{config_path} tidak ditemukan")

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.providers = []
        if "llm_providers" in config and isinstance(config["llm_providers"], list):
            for p in config["llm_providers"]:
                keys = [k.strip() for k in p.get("api_keys", []) if k.strip()]
                if keys:
                    self.providers.append({
                        "name": p["name"],
                        "base_url": p["base_url"],
                        "model": p["model"],
                        "keys": keys,
                        "key_index": 0,
                    })
        elif "groq_api_keys" in config and isinstance(config["groq_api_keys"], list):
            keys = [k.strip() for k in config["groq_api_keys"] if k.strip()]
            self.providers.append({
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b-versatile",
                "keys": keys,
                "key_index": 0,
            })
        elif "groq_api_key" in config and config["groq_api_key"]:
            self.providers.append({
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b-versatile",
                "keys": [config["groq_api_key"].strip()],
                "key_index": 0,
            })

        if not self.providers:
            raise ValueError(
                "Tidak ada llm_providers atau groq_api_key(s) ditemukan di "
                "my_config.json"
            )

        self.provider_index = 0
        total_keys = sum(len(p["keys"]) for p in self.providers)
        names = ", ".join(f"{p['name']}({len(p['keys'])})" for p in self.providers)
        print(f"🔑 MultiProviderKeyRotator siap: {len(self.providers)} provider, "
              f"{total_keys} total API key -> {names}")

    def _current_provider(self):
        return self.providers[self.provider_index]

    def get_client(self):
        """Return (OpenAI client, model_name, provider_name) untuk key aktif saat ini."""
        provider = self._current_provider()
        key = provider["keys"][provider["key_index"]]
        client = OpenAI(base_url=provider["base_url"], api_key=key)
        return client, provider["model"], provider["name"]

    def rotate_key(self):
        """Rotasi ke key berikutnya dalam provider aktif. Kalau provider
        aktif sudah habis semua key-nya, pindah ke provider berikutnya."""
        provider = self._current_provider()
        old_name, old_index = provider["name"], provider["key_index"]

        if provider["key_index"] + 1 < len(provider["keys"]):
            provider["key_index"] += 1
            print(f"🔄 Rotasi key dalam provider '{old_name}': "
                  f"index {old_index} -> {provider['key_index']}")
        else:
            provider["key_index"] = 0
            self.provider_index = (self.provider_index + 1) % len(self.providers)
            new_provider = self._current_provider()
            print(f"🔀 Semua key '{old_name}' habis, PINDAH PROVIDER -> "
                  f"'{new_provider['name']}' (index 0)")

    def call_with_rotation(self, call_fn, max_retries=None):
        """call_fn menerima (client, model_name) dan harus memanggil
        client.chat.completions.create(model=model_name, ...)"""
        if max_retries is None:
            max_retries = sum(len(p["keys"]) for p in self.providers)

        last_error = None
        for attempt in range(max_retries):
            client, model_name, provider_name = self.get_client()
            try:
                return call_fn(client, model_name)
            except Exception as e:
                error_str = str(e).lower()
                last_error = e
                if "rate limit" in error_str or "429" in error_str or "quota" in error_str:
                    print(f"⚠️ Rate limit di provider '{provider_name}': {e}")
                    self.rotate_key()
                    time.sleep(2)
                    continue
                else:
                    raise

        raise RuntimeError(
            f"Semua provider & key gagal (rate limit terus). "
            f"Error terakhir: {last_error}"
        )


GroqKeyRotator = MultiProviderKeyRotator  # alias backward-compat