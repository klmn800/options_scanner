# OpenAI API Models Reference

*Based on config.json and current knowledge - verify against official docs*

## Available Models (2025)

### GPT-4o Family
- **gpt-4o**: Most capable GPT-4 model, multimodal, 128k context
- **gpt-4o-mini**: Fast and cheap GPT-4 level, 128k context

### GPT-4 Family  
- **gpt-4-turbo**: GPT-4 with improved instruction following, 128k context
- **gpt-4**: Original GPT-4, high capability, 8k context

### GPT-3.5 Family
- **gpt-3.5-turbo**: Fast and cheap, good for simple tasks, 4k context
- **gpt-3.5-turbo-16k**: GPT-3.5 with larger context window, 16k context

### Reasoning Models
- **o1-preview**: Reasoning model, slower but better at complex problems
- **o1-mini**: Faster reasoning model, good for coding and math

## Chat Completions API

### Basic Request Format
```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "max_tokens": 1000,
  "temperature": 0.7
}
```

### Key Parameters
- `model`: Model identifier (see above)
- `messages`: Array of message objects with role/content
- `max_tokens`: Maximum tokens in response (default varies by model)
- `temperature`: Randomness (0.0-2.0, default 1.0)
- `top_p`: Nucleus sampling (0.0-1.0, default 1.0)
- `frequency_penalty`: Penalize repeated tokens (-2.0 to 2.0)
- `presence_penalty`: Penalize new topics (-2.0 to 2.0)

### Message Roles
- `system`: Instructions for the model
- `user`: User input/questions
- `assistant`: Model responses
- `function`: Function call results (for function calling)

## Rate Limits (Typical)

### Free Tier
- 3 requests per minute
- 200 requests per day
- Model-dependent token limits

### Paid Tier 1
- 3,500 requests per minute  
- 10,000 tokens per minute
- Higher daily limits

*Note: Exact limits vary by model and account status*

## Pricing (Approximate - Verify Current)

### Input/Output Token Pricing (per 1M tokens)
- **GPT-4o**: $5/$15
- **GPT-4o-mini**: $0.15/$0.60
- **GPT-4-turbo**: $10/$30
- **GPT-3.5-turbo**: $0.50/$1.50

## Error Codes

- `400`: Bad request (invalid parameters)
- `401`: Invalid API key
- `429`: Rate limit exceeded
- `500`: Server error
- `503`: Service unavailable

## Best Practices

1. **Model Selection**: Use cheapest model that meets requirements
2. **Token Management**: Monitor usage to control costs
3. **Error Handling**: Implement retry logic for transient errors
4. **Rate Limiting**: Respect rate limits to avoid 429 errors

## Source
Configuration: config.json openai_api section
Last updated: 2025-09-05
Official docs: https://platform.openai.com/docs