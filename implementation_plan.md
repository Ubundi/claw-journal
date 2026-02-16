# Plan to Update UI

## Backend Updates

1.  **Extend `UsageRepository` in `claw_journal/storage.py`**:
    -   Add `get_dashboard_summary()`: Returns total spend, total tokens, session count, active agent count.
    -   Add `get_cost_trend(days)`: Returns daily cost for chart (already covered by `get_daily_usage` but might need formatting).
    -   Add `get_cost_by_agent(limit)`: Returns top agents by cost (group by `session_key`).
    -   Add `get_top_tools(limit)`: Returns top tools by usage count. (This might require querying `event_type` or `raw_json` if tools are logged there).
    -   Add `get_recent_sessions(limit)`: Returns recent session details (already covered by `get_session_usage` but might need specific formatting for the dashboard table).

2.  **Extend `UsageService` in `claw_journal/service.py`**:
    -   Add `get_dashboard_data()` which calls the above repository methods and aggregates the result into the format expected by the frontend:
        ```json
        {
          "summary": { ... },
          "costTrend": [ ... ],
          "costByAgent": [ ... ],
          "topTools": [ ... ],
          "recentSessions": [ ... ]
        }
        ```

3.  **Update `create_app` in `claw_journal/api.py`**:
    -   Add `/api/dashboard-data` endpoint that calls `usage_service.get_dashboard_data()`.
    -   Ensure CORS is configured if the frontend is served separately (dev mode) or integrate static file serving for production.

## Frontend Updates

1.  **Create Frontend Structure**:
    -   Initialize a React project in a `frontend` directory (using Vite or similar, or just manually creating files if user prefers minimal dependencies, but `dash_plan.txt` implies a standard setup).
    -   Install dependencies: `lucide-react`, `recharts`, `axios`, `clsx`, `tailwind-merge` (standard utils).

2.  **Implement Dashboard Component**:
    -   Create `Dashboard.jsx` (or `.tsx`) following the design in `dash_plan.txt` and the image.
    -   Implement the charts using Recharts.
    -   Implement the "Recent Sessions" table.
    -   Fetch data from `/api/dashboard-data`.

3.  **Integration**:
    -   Configure the frontend to proxy requests to the backend (e.g., in `vite.config.js`).
    -   (Optional) Build the frontend and serve it via FastAPI static files for a single-deployable unit.

## Specific API Logic

-   **Active Agents**: define as unique `session_key`s with activity in the last N days (or just all time if N is large).
-   **Cache Stats**: If not available in DB, return mock/zero values or derive from `context_tokens` if that represents cache.
-   **Top Tools**: If not tracked, return empty list or mock.

## Execution Order

1.  Create frontend project structure.
2.  Implement frontend components.
3.  Update backend API.
4.  Connect them.
