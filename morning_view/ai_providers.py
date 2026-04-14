#!/usr/bin/env python3
"""
AI Provider Interface for Morning Views TUI

Unified interface for multiple AI providers:
- Anthropic (Claude Haiku, Sonnet, Opus)
- OpenAI (GPT-4o, GPT-4o-mini)
- xAI (Grok)
- Google (Gemini Pro, Flash)

Each provider handles:
- API initialization
- Message formatting
- Token tracking
- Cost calculation

Author: Ben
Date: 2025-10-09
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Tuple

# Suppress Google AI SDK warnings about GCP credentials
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import SDKs
try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# ========== Configuration Loading ==========

def load_config():
    """Load API keys and config from config.json

    Returns:
        dict: Full config dictionary
    """
    config_path = Path(__file__).parent.parent / 'config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# ========== Provider Classes ==========

class AnthropicProvider:
    """Claude (Haiku, Sonnet, Opus) provider"""

    def __init__(self, config: dict):
        if anthropic is None:
            raise Exception("anthropic package not installed. Run: pip install anthropic")

        claude_config = config['claude_api']
        self.api_key = claude_config['api_key']
        self.client = anthropic.Anthropic(api_key=self.api_key)

        # Read models and pricing from config
        self.models = claude_config.get('available_models', {})
        self.pricing = claude_config.get('pricing', {})
        self.default_model = claude_config.get('model', 'claude-3-5-haiku-20241022')

    def call(self, system_prompt: str, user_prompt: str, model: str = 'haiku', max_tokens: int = 4000) -> Tuple[str, Dict]:
        """Call Claude API

        Args:
            system_prompt: System instructions
            user_prompt: User message
            model: Model name ('haiku', 'sonnet', 'opus')
            max_tokens: Maximum response tokens

        Returns:
            Tuple of (response_text, usage_dict)

        Raises:
            Exception: With diagnostic message if API call fails
        """
        model_id = self.models.get(model, self.default_model)

        try:
            message = self.client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            # Extract response and usage
            response_text = message.content[0].text
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens

            # Calculate cost
            pricing = self.pricing.get(model_id, self.pricing.get(self.default_model, {'input': 1.00, 'output': 5.00}))
            cost_usd = (
                (input_tokens / 1_000_000) * pricing['input'] +
                (output_tokens / 1_000_000) * pricing['output']
            )

            usage = {
                'provider': 'anthropic',
                'model': model_id,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_usd': cost_usd
            }

            return response_text, usage

        except Exception as e:
            error_msg = str(e)
            if 'authentication' in error_msg.lower() or 'api_key' in error_msg.lower():
                raise Exception(f"Anthropic API authentication failed. Check your API key in config.json. Error: {error_msg}")
            elif 'rate_limit' in error_msg.lower():
                raise Exception(f"Anthropic API rate limit exceeded. Please wait a moment and try again. Error: {error_msg}")
            elif 'overloaded' in error_msg.lower():
                raise Exception(f"Anthropic API is overloaded. Try again in a few moments. Error: {error_msg}")
            else:
                raise Exception(f"Anthropic API call failed ({model_id}): {error_msg}")


class OpenAIProvider:
    """OpenAI (GPT-4o, GPT-4o-mini) provider"""

    def __init__(self, config: dict):
        if OpenAI is None:
            raise Exception("openai package not installed. Run: pip install openai")

        openai_config = config['openai_api']
        self.api_key = openai_config['api_key']
        self.client = OpenAI(api_key=self.api_key)

        # Read models and pricing from config
        self.models = openai_config.get('available_models', {})
        self.pricing = openai_config.get('pricing', {})
        self.default_model = openai_config.get('default_model', 'gpt-4o-mini')

    def call(self, system_prompt: str, user_prompt: str, model: str = 'gpt-4o-mini', max_tokens: int = 4000) -> Tuple[str, Dict]:
        """Call OpenAI API

        Args:
            system_prompt: System instructions
            user_prompt: User message
            model: Model name ('gpt-4o', 'gpt-4o-mini')
            max_tokens: Maximum response tokens

        Returns:
            Tuple of (response_text, usage_dict)

        Raises:
            Exception: With diagnostic message if API call fails
        """
        model_id = self.models.get(model, self.default_model)

        try:
            response = self.client.chat.completions.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract response and usage
            response_text = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Calculate cost
            pricing = self.pricing.get(model_id, self.pricing.get(self.default_model, {'input': 0.15, 'output': 0.60}))
            cost_usd = (
                (input_tokens / 1_000_000) * pricing['input'] +
                (output_tokens / 1_000_000) * pricing['output']
            )

            usage = {
                'provider': 'openai',
                'model': model_id,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_usd': cost_usd
            }

            return response_text, usage

        except Exception as e:
            error_msg = str(e)
            if 'authentication' in error_msg.lower() or 'api_key' in error_msg.lower() or 'unauthorized' in error_msg.lower():
                raise Exception(f"OpenAI API authentication failed. Check your API key in config.json. Error: {error_msg}")
            elif 'rate_limit' in error_msg.lower() or 'quota' in error_msg.lower():
                raise Exception(f"OpenAI API rate limit or quota exceeded. Error: {error_msg}")
            elif 'model' in error_msg.lower() and 'not found' in error_msg.lower():
                raise Exception(f"OpenAI model '{model_id}' not available. Check your account access. Error: {error_msg}")
            else:
                raise Exception(f"OpenAI API call failed ({model_id}): {error_msg}")


class XAIProvider:
    """xAI (Grok) provider - uses OpenAI SDK with custom base_url"""

    def __init__(self, config: dict):
        if OpenAI is None:
            raise Exception("openai package not installed. Run: pip install openai")

        xai_config = config['xai_api']
        self.api_key = xai_config['api_key']
        self.base_url = xai_config['base_url']
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        # Read models and pricing from config
        self.models = xai_config.get('available_models', {})
        self.pricing = xai_config.get('pricing', {})
        self.default_model = xai_config.get('default_model', 'grok-2-1212')

    def call(self, system_prompt: str, user_prompt: str, model: str = 'grok-2', max_tokens: int = 4000) -> Tuple[str, Dict]:
        """Call xAI Grok API

        Args:
            system_prompt: System instructions
            user_prompt: User message
            model: Model name ('grok-2')
            max_tokens: Maximum response tokens

        Returns:
            Tuple of (response_text, usage_dict)

        Raises:
            Exception: With diagnostic message if API call fails
        """
        model_id = self.models.get(model, self.default_model)

        try:
            response = self.client.chat.completions.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract response and usage
            response_text = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Calculate cost
            pricing = self.pricing.get(model_id, self.pricing.get(self.default_model, {'input': 2.00, 'output': 10.00}))
            cost_usd = (
                (input_tokens / 1_000_000) * pricing['input'] +
                (output_tokens / 1_000_000) * pricing['output']
            )

            usage = {
                'provider': 'xai',
                'model': model_id,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_usd': cost_usd
            }

            return response_text, usage

        except Exception as e:
            error_msg = str(e)
            if 'authentication' in error_msg.lower() or 'api_key' in error_msg.lower() or 'unauthorized' in error_msg.lower():
                raise Exception(f"xAI API authentication failed. Check your API key in config.json. Error: {error_msg}")
            elif 'rate_limit' in error_msg.lower():
                raise Exception(f"xAI API rate limit exceeded. Note: Free tier has limited calls. Error: {error_msg}")
            elif 'connection' in error_msg.lower() or 'timeout' in error_msg.lower():
                raise Exception(f"xAI API connection failed. Check your internet connection. Error: {error_msg}")
            else:
                raise Exception(f"xAI API call failed ({model_id}): {error_msg}")


class GeminiProvider:
    """Google Gemini provider"""

    def __init__(self, config: dict):
        if genai is None:
            raise Exception("google-generativeai package not installed. Run: pip install google-generativeai")

        gemini_config = config['gemini_api']
        self.api_key = gemini_config['api_key']
        genai.configure(api_key=self.api_key)

        # Read models and pricing from config
        self.models = gemini_config.get('available_models', {})
        self.pricing = gemini_config.get('pricing', {})
        self.default_model = gemini_config.get('default_model', 'gemini-2.0-flash')

    def call(self, system_prompt: str, user_prompt: str, model: str = 'gemini-flash', max_tokens: int = 4000) -> Tuple[str, Dict]:
        """Call Google Gemini API

        Args:
            system_prompt: System instructions
            user_prompt: User message
            model: Model name ('gemini-pro', 'gemini-flash')
            max_tokens: Maximum response tokens

        Returns:
            Tuple of (response_text, usage_dict)

        Raises:
            Exception: With diagnostic message if API call fails
        """
        model_id = self.models.get(model, self.default_model)

        try:
            # Create model with system instruction
            gemini_model = genai.GenerativeModel(
                model_name=model_id,
                system_instruction=system_prompt
            )

            # Generate response
            response = gemini_model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens
                )
            )

            # Extract response
            response_text = response.text

            # Estimate tokens (Gemini doesn't always provide usage)
            try:
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
            except:
                # Rough estimation: ~4 chars per token
                input_tokens = len(system_prompt + user_prompt) // 4
                output_tokens = len(response_text) // 4

            # Calculate cost
            pricing = self.pricing.get(model_id, self.pricing.get(self.default_model, {'input': 0.075, 'output': 0.30}))
            cost_usd = (
                (input_tokens / 1_000_000) * pricing['input'] +
                (output_tokens / 1_000_000) * pricing['output']
            )

            usage = {
                'provider': 'google',
                'model': model_id,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_usd': cost_usd
            }

            return response_text, usage

        except Exception as e:
            error_msg = str(e)
            if 'api_key' in error_msg.lower() or 'invalid' in error_msg.lower() and 'key' in error_msg.lower():
                raise Exception(f"Google Gemini API authentication failed. Check your API key in config.json. Error: {error_msg}")
            elif 'quota' in error_msg.lower() or 'limit' in error_msg.lower():
                raise Exception(f"Google Gemini API quota/rate limit exceeded. Error: {error_msg}")
            elif 'permission' in error_msg.lower() or 'access' in error_msg.lower():
                raise Exception(f"Google Gemini model access denied. Check if '{model_id}' is available in your region/account. Error: {error_msg}")
            else:
                raise Exception(f"Google Gemini API call failed ({model_id}): {error_msg}")


# ========== Provider Factory ==========

_provider_cache = {}

def get_provider(provider_name: str):
    """Get AI provider instance (cached)

    Args:
        provider_name: One of 'anthropic', 'openai', 'xai', 'google'

    Returns:
        Provider instance

    Raises:
        Exception: If provider not found or initialization fails
    """
    # Return cached instance if available
    if provider_name in _provider_cache:
        return _provider_cache[provider_name]

    # Load config
    config = load_config()

    # Create provider
    if provider_name == 'anthropic':
        provider = AnthropicProvider(config)
    elif provider_name == 'openai':
        provider = OpenAIProvider(config)
    elif provider_name == 'xai':
        provider = XAIProvider(config)
    elif provider_name == 'google':
        provider = GeminiProvider(config)
    else:
        raise Exception(f"Unknown provider: {provider_name}. Available: anthropic, openai, xai, google")

    # Cache and return
    _provider_cache[provider_name] = provider
    return provider


# ========== Convenience Function ==========

def call_ai(provider: str, system_prompt: str, user_prompt: str, model: str = None, max_tokens: int = 4000) -> Tuple[str, Dict]:
    """Call any AI provider with unified interface

    Args:
        provider: Provider name ('anthropic', 'openai', 'xai', 'google')
        system_prompt: System instructions
        user_prompt: User message
        model: Model name (provider-specific, defaults to cheap/fast option)
        max_tokens: Maximum response tokens

    Returns:
        Tuple of (response_text, usage_dict)

    Example:
        >>> text, usage = call_ai('anthropic', system_prompt, user_prompt, model='haiku')
        >>> print(f"Cost: ${usage['cost_usd']:.4f}")
    """
    provider_instance = get_provider(provider)

    # Use default model if none specified
    if model is None:
        defaults = {
            'anthropic': 'haiku',
            'openai': 'gpt-4o-mini',
            'xai': 'grok-2',
            'google': 'gemini-flash'
        }
        model = defaults.get(provider)

    return provider_instance.call(system_prompt, user_prompt, model, max_tokens)


# ========== CLI Testing ==========

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test AI providers')
    parser.add_argument('provider', choices=['anthropic', 'openai', 'xai', 'google'],
                       help='Provider to test')
    parser.add_argument('--model', help='Model name (provider-specific)')
    parser.add_argument('--prompt', default='What is 2+2? Explain briefly.',
                       help='Test prompt')

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"Testing Provider: {args.provider}")
    print(f"{'='*70}\n")

    try:
        system_prompt = "You are a helpful assistant. Be concise."
        response, usage = call_ai(args.provider, system_prompt, args.prompt, model=args.model)

        print(f"Response:\n{response}\n")
        print(f"{'='*70}")
        print(f"Provider: {usage['provider']}")
        print(f"Model: {usage['model']}")
        print(f"Input Tokens: {usage['input_tokens']:,}")
        print(f"Output Tokens: {usage['output_tokens']:,}")
        print(f"Cost: ${usage['cost_usd']:.4f}")
        print(f"{'='*70}\n")

    except Exception as e:
        print(f"ERROR: {e}\n")
        sys.exit(1)
