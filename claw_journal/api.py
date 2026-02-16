from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .service import UsageService


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        .grid { display: grid; gap: 16px; grid-template-columns: 1fr; }
        .card { background: #151a21; border: 1px solid #2d333b; border-radius: 10px; padding: 14px; overflow: hidden; }
        .table-container { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 600px; }
        th, td { border-bottom: 1px solid #2d333b; text-align: left; padding: 6px; white-space: nowrap; }
        .muted { color: #8b949e; font-size: 12px; }
        .pill { display:inline-block; padding:4px 8px; border-radius:999px; border:1px solid #2d333b; margin-right:8px; }
        .clickable { cursor: pointer; }
        .clickable:hover { background: #1f2630; }
        .info { color: #8b949e; margin-left: 6px; }
        .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
        #sessionEvents { max-height: 320px; overflow-y: auto; }
        .event-item { border-bottom: 1px solid #2d333b; padding: 8px 0; }
        .event-header { font-size: 12px; color: #8b949e; margin-bottom: 4px; }
        .event-text { white-space: pre-wrap; font-size: 13px; line-height: 1.35; }
        a { color:#58a6ff; }
    </style>
</head>
<body>
    <h1>Claw Journal</h1>
    <p class="muted">Local dashboard for current backend MVP. Refresh to update.</p>

    <div class="card" style="margin-bottom:16px;" id="profileCard">
        <strong id="modeSummary">Mode: loading...</strong>
        <div class="muted" id="modeDetails"></div>
        <div class="muted" id="costHint"></div>
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
            <div class="table-container">
                <table id="sessionsTable">
                    <thead><tr><th>Session</th><th>Provider</th><th>Model</th><th>Tokens</th><th class="cost-col">Input Cost</th><th class="cost-col">Output Cost</th><th class="cost-col">Total Cost</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </section>

        <section class="card">
            <h2>Reconciled Sessions</h2>
            <div class="table-container">
                <table id="reconciledTable">
                    <thead><tr><th>Session</th><th>Model</th><th>Total Tokens</th><th>Observed Cost</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </section>

        <section class="card">
            <h2>Daily Usage</h2>
            <div class="table-container">
                <table id="dailyTable">
                    <thead><tr><th>Date</th><th>Input</th><th>Output</th><th>Total</th><th class="cost-col">Input Cost</th><th class="cost-col">Output Cost</th><th class="cost-col">Total Cost</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </section>

        <section class="card">
            <h2>Models Used by OpenClaw</h2>
            <div class="table-container">
                <table id="modelsTable">
                    <thead><tr><th>Provider</th><th>Model</th><th>Sessions</th><th>Total Tokens</th><th>Pricing Source</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </section>

        <section class="card">
            <h2>Token Accuracy Check</h2>
            <p class="muted" id="accuracySummary"></p>
            <div class="table-container">
                <table id="accuracyTable">
                    <thead><tr><th>Session</th><th>Model</th><th>Snapshot Tokens</th><th>Backfilled Tokens</th><th>Delta</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </section>

        <section class="card" style="grid-column: 1 / -1;">
            <h2>Session Detail</h2>
            <p class="muted">Click any session row to inspect extracted text and raw event lines.</p>
            <div id="sessionDetailTitle" class="mono muted">No session selected.</div>
            <div id="sessionEvents"></div>
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
        let currentBillingMode = 'token';

        function renderSimpleRows(tableId, rows, fields) {
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

        function toggleCostColumns(showCosts) {
            document.querySelectorAll('.cost-col').forEach(el => {
                el.style.display = showCosts ? '' : 'none';
            });
        }

        function money(value) {
            const number = Number(value || 0);
            return `$${number.toFixed(6)}`;
        }

        function renderSessionRows(tableId, rows) {
            const tbody = document.querySelector(`#${tableId} tbody`);
            tbody.innerHTML = "";
            for (const row of rows) {
                const tr = document.createElement('tr');
                tr.classList.add('clickable');
                tr.addEventListener('click', () => loadSessionDetail(row.session_id));

                const cells = [
                    row.session_id,
                    row.provider,
                    row.model,
                    row.total_tokens,
                    money(row.input_cost_usd),
                    money(row.output_cost_usd),
                    money(row.cost_usd),
                ];
                for (let i = 0; i < cells.length; i++) {
                    const td = document.createElement('td');
                    td.textContent = cells[i] === null || cells[i] === undefined ? '-' : String(cells[i]);
                    if (!currentBillingMode || currentBillingMode === 'claude_max') {
                        if (i >= 4) {
                            td.style.display = 'none';
                        }
                    }
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            }
        }

        function renderDailyRows(rows) {
            const tbody = document.querySelector('#dailyTable tbody');
            tbody.innerHTML = '';
            for (const row of rows) {
                const tr = document.createElement('tr');
                const cells = [
                    row.usage_date,
                    row.input_tokens,
                    row.output_tokens,
                    row.total_tokens,
                    money(row.input_cost_usd),
                    money(row.output_cost_usd),
                    money(row.cost_usd),
                ];
                for (let i = 0; i < cells.length; i++) {
                    const td = document.createElement('td');
                    td.textContent = cells[i] === null || cells[i] === undefined ? '-' : String(cells[i]);
                    if (!currentBillingMode || currentBillingMode === 'claude_max') {
                        if (i >= 4) {
                            td.style.display = 'none';
                        }
                    }
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            }
        }

        function renderModels(modelsResponse) {
            const tbody = document.querySelector('#modelsTable tbody');
            tbody.innerHTML = '';
            const catalog = modelsResponse.available_models || [];
            const catalogMap = new Map(catalog.map(m => [`${(m.provider || '').toLowerCase()}/${(m.model || '').toLowerCase()}`, m]));
            for (const row of (modelsResponse.used_models || [])) {
                const key = `${(row.provider || '').toLowerCase()}/${(row.model || '').toLowerCase()}`;
                const catalogModel = catalogMap.get(key);
                const tr = document.createElement('tr');
                const pricingSource = catalogModel ? 'OpenRouter auto' : 'Local/manual';
                const values = [row.provider || '-', row.model || '-', row.sessions || 0, row.total_tokens || 0, pricingSource];
                for (const value of values) {
                    const td = document.createElement('td');
                    td.textContent = String(value);
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            }
        }

        function renderAccuracy(accuracyResponse) {
            const summary = accuracyResponse.summary || {};
            document.getElementById('accuracySummary').textContent =
                `Checked ${summary.sessions_checked || 0} sessions, matches=${summary.snapshot_matches || 0}, mismatches=${summary.snapshot_mismatches || 0}`;

            const tbody = document.querySelector('#accuracyTable tbody');
            tbody.innerHTML = '';
            for (const row of (accuracyResponse.rows || [])) {
                const tr = document.createElement('tr');
                const values = [
                    row.session_id,
                    row.model || '-',
                    row.snapshot_total_tokens || 0,
                    row.snapshot_event_total_tokens || 0,
                    row.snapshot_delta_tokens || 0,
                ];
                for (const value of values) {
                    const td = document.createElement('td');
                    td.textContent = String(value);
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            }
        }

        async function loadSessionDetail(sessionId) {
            if (!sessionId || sessionId === 'unknown') {
                return;
            }
            const result = await fetch(`/api/usage/session/${encodeURIComponent(sessionId)}?limit=120`).then(r => r.json());
            document.getElementById('sessionDetailTitle').textContent = `Session: ${result.session_id || sessionId}`;
            const container = document.getElementById('sessionEvents');
            container.innerHTML = '';

            for (const row of (result.rows || [])) {
                const item = document.createElement('div');
                item.className = 'event-item';

                const header = document.createElement('div');
                header.className = 'event-header';
                header.textContent = `${row.event_ts || '-'} · ${row.event_type || '-'} · tokens=${row.total_tokens || 0}`;
                item.appendChild(header);

                const text = document.createElement('div');
                text.className = 'event-text';
                text.textContent = row.human_text || row.reasoning_text || '(No user-facing text extracted)';
                item.appendChild(text);

                const raw = document.createElement('details');
                const rawSummary = document.createElement('summary');
                rawSummary.className = 'muted';
                rawSummary.textContent = 'Raw event JSON';
                raw.appendChild(rawSummary);
                const rawBody = document.createElement('pre');
                rawBody.className = 'mono';
                rawBody.textContent = row.raw_json || '';
                raw.appendChild(rawBody);
                item.appendChild(raw);

                container.appendChild(item);
            }
        }

        async function load() {
            const [sessions, reconciled, daily, costs, profile, planCost, models, accuracy] = await Promise.all([
                fetch('/api/usage/sessions?limit=20').then(r => r.json()),
                fetch('/api/usage/reconciled?limit=20').then(r => r.json()),
                fetch('/api/usage/daily?days=30').then(r => r.json()),
                fetch('/api/usage/cost-sources').then(r => r.json()),
                fetch('/api/system/profile').then(r => r.json()),
                fetch('/api/usage/plan-cost').then(r => r.json()),
                fetch('/api/system/models').then(r => r.json()),
                fetch('/api/system/token-accuracy?limit=40').then(r => r.json())
            ]);

            const p = profile || {};
            currentBillingMode = p.billing_mode || 'token';
            const showCosts = currentBillingMode !== 'claude_max';
            toggleCostColumns(showCosts);

            renderSessionRows('sessionsTable', sessions.rows || []);
            renderSimpleRows('reconciledTable', reconciled.rows || [], ['session_id', 'model', 'total_tokens', 'observed_cost_usd']);
            renderDailyRows(daily.rows || []);
            renderModels(models || {});
            renderAccuracy(accuracy || {});

            const c = costs.rows || {};
            document.getElementById('observed').textContent = `Observed: ${c.observed || 0}`;
            document.getElementById('estimated').textContent = `Estimated: ${c.estimated || 0}`;
            document.getElementById('missing').textContent = `Missing: ${c.missing || 0}`;
            document.getElementById('subscription').textContent = `Subscription: ${c.subscription || 0}`;

            document.getElementById('modeSummary').textContent = `Mode: auth=${p.auth_mode || 'unknown'} · billing=${p.billing_mode || 'unknown'}`;
            document.getElementById('modeDetails').textContent = p.billing_mode === 'claude_max'
              ? `Claude Max monthly plan: $${p.claude_max_monthly_usd || 0} (token costs shown as subscription-included)`
              : 'Token billing mode: costs shown from observed or estimated per-token rates.';

            document.getElementById('costHint').textContent = p.billing_mode === 'claude_max'
              ? 'ℹ Monthly subscription billing is active, so per-token dollar values are intentionally hidden in this view.'
              : '';

                        if (planCost && planCost.enabled) {
                                document.getElementById('modeDetails').textContent += ` Effective daily plan cost: $${planCost.daily_usd}`;
                        }

            const notes = (p.notes || []).join(' ');
            document.getElementById('dataNotes').textContent = notes || '';

            const sessionsRows = sessions.rows || [];
            const reconciledRows = reconciled.rows || [];
            const status = (p.data_status || {});
            if (status.log_usage_available) {
                document.getElementById('logsStatus').textContent = 'Log-derived usage events detected.';
            } else if (status.snapshot_backfill_available) {
                document.getElementById('logsStatus').textContent = 'Log-derived usage events are absent; charts are populated using snapshot-to-timeseries backfill from gateway sessions.';
            } else if (sessionsRows.length === 0 && reconciledRows.length > 0) {
                document.getElementById('logsStatus').textContent = 'No log-derived usage events found in current logs. Reconciled sessions are shown from gateway session totals.';
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

    @app.get("/api/dashboard-data")
    def dashboard_data() -> dict[str, object]:
        return usage_service.get_dashboard_data()

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

    @app.get("/api/system/models")
    def system_models() -> dict[str, object]:
        return usage_service.model_catalog()

    @app.get("/api/system/token-accuracy")
    def token_accuracy(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return usage_service.token_accuracy(limit=limit)

    @app.get("/api/system/session-snapshots")
    def session_snapshots(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return usage_service.session_snapshots(limit=limit)

    @app.get("/api/system/logs-explorer")
    def logs_explorer(
        file_limit: int = Query(default=12, ge=1, le=30),
        tail_lines: int = Query(default=80, ge=1, le=300),
    ) -> dict[str, object]:
        return usage_service.logs_explorer(file_limit=file_limit, tail_lines=tail_lines)

    @app.get("/api/usage/session/{session_id}")
    def session_detail(session_id: str, limit: int = Query(default=300, ge=1, le=2000)) -> dict[str, object]:
        return usage_service.session_detail(session_id=session_id, limit=limit)

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
