"""
Local API Gateway (port 8080) for local development outside Docker.
Mirrors the exact routing rules of backend/gateway/default.conf.template (Nginx):
  - /api/ingestion/{path}  -> http://127.0.0.1:8004/{path}
  - /api/analytics/{path}  -> http://127.0.0.1:8001/{path}
  - /api/clustering/{path} -> http://127.0.0.1:8002/{path}
  - /api/prediction/{path} -> http://127.0.0.1:8003/{path}
"""
from __future__ import annotations

import os
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx

UPSTREAMS = {
    "ingestion": os.getenv("INGESTION_UPSTREAM", "http://127.0.0.1:8004"),
    "analytics": os.getenv("ANALYTICS_UPSTREAM", "http://127.0.0.1:8001"),
    "clustering": os.getenv("CLUSTERING_UPSTREAM", "http://127.0.0.1:8002"),
    "prediction": os.getenv("PREDICTION_UPSTREAM", "http://127.0.0.1:8003"),
}

app = FastAPI(title="Flight Observatory API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway", "upstreams": UPSTREAMS}


@app.get("/")
async def root():
    return {
        "service": "gateway",
        "docs": [
            "/api/ingestion/docs",
            "/api/analytics/docs",
            "/api/clustering/docs",
            "/api/prediction/docs",
        ],
    }


@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_service(service: str, path: str, request: Request):
    upstream_base = UPSTREAMS.get(service)
    if not upstream_base:
        return Response(
            content='{"detail":"Route not found"}',
            status_code=404,
            media_type="application/json",
        )

    query_string = request.url.query
    target_url = f"{upstream_base.rstrip('/')}/{path}"
    if query_string:
        target_url = f"{target_url}?{query_string}"

    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "connection")
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except httpx.RequestError as exc:
        return Response(
            content=f'{{"detail":"Upstream service \'{service}\' unreachable at {upstream_base}: {exc}"}}',
            status_code=502,
            media_type="application/json",
        )
