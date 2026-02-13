from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .service import UsageService


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def dashboard_home() -> str:
        return """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Claw Journal Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; background: #0b0d10; color: #e6edf3; }
        h1, h2 { margin: 0 0 12px; }
        .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
        .card { background: #151a21; border: 1px solid #2d333b; border-radius: 10px; padding: 14px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { border-bottom: 1px solid #2d333b; text-align: left; padding: 6px; }
        .muted { color: #8b949e; font-size: 12px; }
        .pill { display:inline-block; padding:4px 8px; border-radius:999px; border:1px solid #2d333b; margin-right:8px; }
        a { color:#58a6ff; }
    </style>
</head>
<body>
    <h1>Claw Journal</h1>
    <p class="muted">Local dashboard for current backend MVP. Refresh to update.</p>

    <div class="card" style="margin-bottom:16px;" id="profileCard">
        <strong id="modeSummary">Mode: loading...</strong>
        <div class="muted" id="modeDetails"></div>
        <div class="muted" id="dataNotes"></div>
    </div>

    <div class="card" style="margin-bottom:16px;">
        <span class="pill" id="observed">Observed: 0</span>
        <span class="pill" id="estimated">Estimated: 0</span>
        <span class="pill" id="missing">Missing: 0</span>
        <span class="pill" id="subscription">Subscription: 0</span>
    </div>

    <div class="grid">
        <section class="card">
            <h2>Session Usage (Logs)</h2>
            <p class="muted" id="logsStatus"></p>
            <table id="sessionsTable">
                <thead><tr><th>Session</th><th>Provider</th><th>Model</th><th>Tokens</th><th>Input Cost</th><th>Output Cost</th><th>Total Cost</th></tr></thead>
                <tbody></tbody>
            </table>
        </section>

        <section class="card">
            <h2>Reconciled Sessions</h2>
            <table id="reconciledTable">
                <thead><tr><th>Session</th><th>Model</th><th>Total Tokens</th><th>Observed Cost</th></tr></thead>
                <tbody></tbody>
            </table>
        </section>

        <section class="card">
            <h2>Daily Usage</h2>
            <table id="dailyTable">
                <thead><tr><th>Date</th><th>Input</th><th>Output</th><th>Total</th><th>Input Cost</th><th>Output Cost</th><th>Total Cost</th></tr></thead>
                <tbody></tbody>
            </table>
        </section>

        <section class="card">
            <h2>Pricing Configuration</h2>
            <p class="muted">Add or update input/output rates (USD per 1M tokens). Changes are written to pricing file.</p>
            <form id="pricingForm">
                <input id="provider" placeholder="provider (e.g. anthropic)" required style="width: 100%; margin-bottom: 6px;" />
                <input id="model" placeholder="model (e.g. claude-opus-4-5)" required style="width: 100%; margin-bottom: 6px;" />
                <input id="inputRate" type="number" step="0.0001" min="0" placeholder="input_per_million" required style="width: 100%; margin-bottom: 6px;" />
                <input id="outputRate" type="number" step="0.0001" min="0" placeholder="output_per_million" required style="width: 100%; margin-bottom: 6px;" />
                <button type="submit">Save Pricing</button>
            </form>
            <p class="muted" id="pricingResult"></p>
        </section>
    </div>

    <p class="muted" style="margin-top:16px;">APIs: <a href="/api/usage/sessions?limit=20">sessions</a> · <a href="/api/usage/reconciled?limit=20">reconciled</a> · <a href="/api/usage/daily?days=30">daily</a></p>

    <script>
        function renderRows(tableId, rows, fields) {
            const tbody = document.querySelector(`#${tableId} tbody`);
            tbody.innerHTML = "";
            for (const row of rows) {
                const tr = document.createElement("tr");
                for (const field of fields) {
                    const td = document.createElement("td");
                    const value = row[field];
                    td.textContent = value === null || value === undefined ? "-" : String(value);
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            }
        }

        async function load() {
            const [sessions, reconciled, daily, costs, profile, planCost] = await Promise.all([
                fetch('/api/usage/sessions?limit=20').then(r => r.json()),
                fetch('/api/usage/reconciled?limit=20').then(r => r.json()),
                fetch('/api/usage/daily?days=30').then(r => r.json()),
                fetch('/api/usage/cost-sources').then(r => r.json()),
                fetch('/api/system/profile').then(r => r.json()),
                fetch('/api/usage/plan-cost').then(r => r.json())
            ]);

            renderRows('sessionsTable', sessions.rows || [], ['session_id', 'provider', 'model', 'total_tokens', 'input_cost_usd', 'output_cost_usd', 'cost_usd']);
            renderRows('reconciledTable', reconciled.rows || [], ['session_id', 'model', 'total_tokens', 'observed_cost_usd']);
            renderRows('dailyTable', daily.rows || [], ['usage_date', 'input_tokens', 'output_tokens', 'total_tokens', 'input_cost_usd', 'output_cost_usd', 'cost_usd']);

            const c = costs.rows || {};
            document.getElementById('observed').textContent = `Observed: ${c.observed || 0}`;
            document.getElementById('estimated').textContent = `Estimated: ${c.estimated || 0}`;
            document.getElementById('missing').textContent = `Missing: ${c.missing || 0}`;
            document.getElementById('subscription').textContent = `Subscription: ${c.subscription || 0}`;

            const p = profile || {};
            document.getElementById('modeSummary').textContent = `Mode: auth=${p.auth_mode || 'unknown'} · billing=${p.billing_mode || 'unknown'}`;
            document.getElementById('modeDetails').textContent = p.billing_mode === 'claude_max'
              ? `Claude Max monthly plan: $${p.claude_max_monthly_usd || 0} (token costs shown as subscription-included)`
              : 'Token billing mode: costs shown from observed or estimated per-token rates.';

                        if (planCost && planCost.enabled) {
                                document.getElementById('modeDetails').textContent += ` Effective daily plan cost: $${planCost.daily_usd}`;
                        }

            const notes = (p.notes || []).join(' ');
            document.getElementById('dataNotes').textContent = notes || '';

            const sessionsRows = sessions.rows || [];
            const reconciledRows = reconciled.rows || [];
            if (sessionsRows.length === 0 && reconciledRows.length > 0) {
                document.getElementById('logsStatus').textContent = 'No log-derived usage events found in current logs. Reconciled sessions are shown from gateway session totals.';
            } else if (sessionsRows.length > 0) {
                document.getElementById('logsStatus').textContent = 'Log-derived usage events detected.';
            } else {
                document.getElementById('logsStatus').textContent = 'No usage data detected yet.';
            }
        }

        async function savePricing(event) {
            event.preventDefault();
            const payload = {
                provider: document.getElementById('provider').value.trim(),
                model: document.getElementById('model').value.trim(),
                input_per_million: Number(document.getElementById('inputRate').value),
                output_per_million: Number(document.getElementById('outputRate').value)
            };

            const response = await fetch('/api/pricing/upsert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!response.ok) {
                document.getElementById('pricingResult').textContent = `Failed: ${data.detail || 'unknown error'}`;
                return;
            }
            document.getElementById('pricingResult').textContent = `Saved ${data.provider}/${data.model}. Restart or wait for next ingest cycle to apply.`;
            await load();
        }

        document.getElementById('pricingForm').addEventListener('submit', savePricing);

        load().catch(err => {
            console.error(err);
            alert('Failed to load dashboard data. Check server logs.');
        });
    </script>
</body>
</html>
    """

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/usage/daily")
    def daily_usage(days: int = Query(default=30, ge=1, le=365)) -> dict[str, object]:
        return {"days": days, "rows": usage_service.daily_usage(days=days)}

    @app.get("/api/usage/sessions")
    def session_usage(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.session_usage(limit=limit)}

    @app.get("/api/reasoning")
    def reasoning(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.reasoning_events(limit=limit)}

    @app.get("/api/usage/reconciled")
    def reconciled_usage(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.reconciled_session_usage(limit=limit)}

    @app.get("/api/usage/cost-sources")
    def cost_sources() -> dict[str, object]:
        return {"rows": usage_service.cost_source_summary()}

    @app.get("/api/system/profile")
    def system_profile() -> dict[str, object]:
        return usage_service.system_profile()

    @app.get("/api/pricing")
    def pricing_table() -> dict[str, object]:
        return usage_service.pricing_table()

    @app.get("/api/usage/plan-cost")
    def plan_cost() -> dict[str, object]:
        return usage_service.plan_cost_summary()

    @app.post("/api/pricing/upsert")
    def pricing_upsert(payload: dict = Body(...)) -> dict[str, object]:
        provider = str(payload.get("provider") or "").strip()
        model = str(payload.get("model") or "").strip()
        if not provider or not model:
            raise HTTPException(status_code=400, detail="provider and model are required")

        input_per_million = float(payload.get("input_per_million") or 0.0)
        output_per_million = float(payload.get("output_per_million") or 0.0)
        if input_per_million < 0 or output_per_million < 0:
            raise HTTPException(
                status_code=400,
                detail="input_per_million and output_per_million must be >= 0",
            )

        return usage_service.upsert_model_pricing(
            provider=provider,
            model=model,
            input_per_million=input_per_million,
            output_per_million=output_per_million,
        )

    return app
