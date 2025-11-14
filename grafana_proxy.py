import os
from fastapi import APIRouter, Request, Response, HTTPException, Depends
import httpx

router = APIRouter(prefix="/grafana")

GRAFANA_URL = os.getenv("GRAFANA_URL")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")


async def require_auth(request: Request):
    # TODO: 프로젝트 인증 방식에 맞게 구현하세요.
    # 현재는 개발 편의를 위해 모든 요청을 허용합니다.
    return True


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request, authorized=Depends(require_auth)):
    if not GRAFANA_URL or not GRAFANA_API_KEY:
        raise HTTPException(status_code=500, detail="Grafana not configured")

    url = f"{GRAFANA_URL.rstrip('/')}/{path}"

    # 전달할 헤더 구성 (Host 등은 제거)
    client_headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "x-forwarded-for", "content-length")}
    client_headers["Authorization"] = f"Bearer {GRAFANA_API_KEY}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.request(
                request.method,
                url,
                headers=client_headers,
                params=request.query_params,
                content=await request.body(),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    # iframe 삽입을 허용하기 위해 일부 보안 헤더 제거/조정
    headers = dict(resp.headers)
    headers.pop("x-frame-options", None)
    headers.pop("content-security-policy", None)

    return Response(content=resp.content, status_code=resp.status_code, headers=headers)
