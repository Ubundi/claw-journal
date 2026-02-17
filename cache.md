# Cache Cost & Accuracy Notes (OAuth)

This document explains what Claw Journal can and cannot calculate reliably for cache usage while connected via OAuth.

## Short answer

- We can calculate token and cost totals when those fields are present in logs/snapshots.
- We **cannot guarantee exact cache-hit billing accuracy** in OAuth mode unless provider-specific cache token fields are emitted in the data source.

## What Claw Journal calculates today

For each event/session/day, Claw Journal uses observed values when available:

- `input_tokens`
- `output_tokens`
- `total_tokens`
- `cost_usd` (if present)

If `cost_usd` is missing and estimation is enabled, Claw Journal estimates:

- `input_cost_usd = input_tokens / 1_000_000 * input_per_million`
- `output_cost_usd = output_tokens / 1_000_000 * output_per_million`
- `cost_usd = input_cost_usd + output_cost_usd`

Cost-source labels in the dashboard:

- `observed`: direct cost came from logs
- `estimated`: cost derived from pricing table
- `missing`: insufficient fields to compute cost
- `subscription`: Claude Max mode attribution

## Why cache accounting is hard in OAuth mode

Provider cache billing usually needs extra fields such as:

- cache read tokens (discounted or zero-rated)
- cache write tokens (often priced differently)
- non-cached input tokens

In OAuth environments, these fields are often omitted or normalized away before they reach local logs. If we only see aggregated input/output tokens, we cannot separate:

- cached-input vs uncached-input
- cache-write vs regular-input

Without that split, cache-hit rates and cache-specific spend are approximations at best.

## Current confidence model

Use this interpretation when reviewing numbers:

- **High confidence**: observed `cost_usd` present in events
- **Medium confidence**: full token counts present and pricing table matches actual provider contract
- **Low confidence (cache-specific)**: OAuth logs without explicit cache token fields

## Practical guidance

If you want cache-accurate billing diagnostics, collect one of:

1. provider-native usage payloads that include cache read/write token fields
2. gateway events with cache dimensions preserved
3. direct API-key mode traces where cache metrics are exposed

Until then, treat cache-related totals as directional, not audit-grade.
