# XAI Grok Models Reference

*Based on research and config.json - Official docs access restricted*

## Available Models (2025)

### Grok 4 Family
- **grok-4**: Most intelligent model in the world, 256k context, real-time search
- **grok-4-heavy**: Most powerful Grok 4 version (SuperGrok Heavy tier)

### Grok 3 Family
- **grok-3**: Standard Grok 3 model, good balance of capability and cost
- **grok-3-mini**: Budget-friendly model for fast agents

### Grok 2 Family  
- **grok-2**: Previous generation Grok model
- **grok-2-image-1212**: Text-to-image generation model

### Specialized Models
- **grok-code-fast-1**: Fast and economical model for coding tasks

## API Compatibility

- Fully compatible with OpenAI API format
- Same endpoint structure as OpenAI/Anthropic
- Easy migration from other providers

## Request Format

```json
{
  "model": "grok-2",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "max_tokens": 8000,
  "temperature": 0.7
}
```

## Key Features

### Context Windows
- **Grok 4**: 256,000 tokens
- **Other models**: Varies (typically 32k-128k)

### Knowledge Cutoff
- **Grok 3/4**: November 2024
- **Real-time Search**: Available via API (Grok 4)

### Live Search Integration
- $25 per 1,000 sources retrieved
- $0.025 per individual source
- Access to X, open web, verified databases

## Pricing (Approximate)

### Grok 3
- **Input**: $3 per 1M tokens (~750,000 words)
- **Output**: $15 per 1M tokens

*Other model pricing varies - check official docs*

## Personality

Grok models are known for:
- Wit and humor in responses
- Direct, honest answers
- Willingness to discuss controversial topics
- Less restrictive than other AI models

## Rate Limits

*Specific rate limits depend on account tier and funding*
- Higher limits for funded accounts
- Model-specific restrictions may apply

## Error Handling

Common errors:
- `404`: Model not found or no access
- `401`: Invalid API key
- `429`: Rate limit exceeded
- Team ID required for support requests

## Best Practices

1. **Model Selection**: Use grok-3-mini for cost efficiency
2. **Context Management**: Leverage large context windows effectively  
3. **Search Integration**: Use real-time search for current information
4. **Personality**: Take advantage of Grok's unique personality traits

## Configuration

Base URL: `https://api.x.ai/v1`
Compatible with OpenAI client libraries

## Source
Research from XAI announcements and API testing
Configuration: config.json xai_api section  
Last updated: 2025-09-05
Official docs: https://docs.x.ai/ (access restricted)