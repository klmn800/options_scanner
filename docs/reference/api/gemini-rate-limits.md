# Gemini API Rate Limits Documentation

## Overview

Rate limits regulate the number of requests to the Gemini API within a given timeframe. They are measured across three key dimensions:

- Requests per minute (RPM)
- Tokens per minute (TPM)
- Requests per day (RPD)

## Usage Tiers

### Tier Qualifications

| Tier | Qualifications |
|------|----------------|
| Free | Users in eligible countries |
| Tier 1 | Billing account linked to project |
| Tier 2 | Total spend > $250, 30+ days since payment |
| Tier 3 | Total spend > $1,000, 30+ days since payment |

## Rate Limit Highlights

### Free Tier Limits (Example Models)

| Model | RPM | TPM | RPD |
|-------|-----|-----|-----|
| Gemini 2.5 Pro | 5 | 250,000 | 100 |
| Gemini 2.5 Flash | 10 | 250,000 | 250 |

### Tier 1 Limits (Example Models)

| Model | RPM | TPM | RPD |
|-------|-----|-----|-----|
| Gemini 2.5 Pro | 150 | 2,000,000 | 10,000 |
| Gemini 2.5 Flash | 1,000 | 1,000,000 | 10,000 |

### Tier 2 and Tier 3 Limits

Significantly higher limits, with Tier 3 offering the most generous quotas. For example:

Tier 3 for Gemini 2.5 Flash:
- RPM: 10,000
- TPM: 8,000,000
- Batch Enqueued Tokens: 1,000,000,000

## Batch Mode Limits

- Concurrent batch requests: 100
- Input file size limit: 2GB
- File storage limit: 20GB

## Upgrading Tiers

To upgrade:
1. Enable Cloud Billing for your Google Cloud project
2. Meet spending and time requirements for higher tiers

## Important Notes

- Rate limits reset at specific intervals (per minute/day)
- Quotas are per-project, not per-API key
- Different models have different limits
- Preview/experimental models may have more restrictive limits

## Source
Retrieved from: https://ai.google.dev/gemini-api/docs/rate-limits
Date: 2025-09-05