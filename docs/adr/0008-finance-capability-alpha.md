# 0008 - Finance Capability Alpha

## Status

Accepted

## Context

Japanese Capability Alpha proved that one real capability can be added through
Capability Registry and Tool Registry metadata. Sprint 4 needs to prove that a
different domain can be added without changing Brain or Core routing.

Finance is a useful second domain because it needs deterministic calculations
and structured summaries, while avoiding external APIs in alpha.

## Decision

Implement Finance Capability Alpha inside `jarvis.capabilities.finance`.

The capability follows the small application structure:

```text
finance/
  __init__.py
  metadata.py
  tools/
    average_price.py
    compound.py
    exchange.py
    portfolio.py
    profit.py
  prompts/
  tests/
```

The capability owns five SAFE tools:

- `finance_compound`
- `finance_average_price`
- `finance_profit`
- `finance_portfolio`
- `finance_exchange`

Each tool exposes ToolMetadata with `capability="finance"`, aliases, supported
intents, examples, SAFE permission metadata, and route confidence. Brain remains
unaware of Finance.

No live exchange, brokerage, or market data API is used in this sprint.

Finance prioritizes dogfooding workflows in this order: compound simulation,
average price, profit calculation, portfolio summary, and exchange conversion.

## Consequences

- Jarvis now supports two independent capability applications: Japanese and
  Finance.
- Both capabilities work through the same Registry -> Permission -> Dispatcher
  platform.
- Finance Alpha is deterministic and safe, but not financial advice.
- The next step should be a v0.4 Alpha Architecture Review before adding more
  capability domains.
