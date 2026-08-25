#!/usr/bin/env python3
"""补充 TikTokDownloader 未暴露的收藏作品 Web API（端口 5556）。"""
import asyncio
import json
import os
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI
from pydantic import BaseModel, Field
from uvicorn import Config, Server

from src.config import Parameter, Settings
from src.custom import VOLUME
from src.interface.collection import Collection
from src.interface.template import API
from src.manager import Database, DownloadRecorder
from src.module import Cookie
from src.record import BaseLogger
from src.tools import ColorfulConsole

app = FastAPI(title="Douyin Collection API", version="1.0.0")
CHROME_FETCH = os.environ.get("A_BOGUS_FETCH_URL", "http://127.0.0.1:5557/fetch")


class CollectionRequest(BaseModel):
    pages: int | None = Field(default=2, ge=1)
    count: int = Field(default=20, ge=1, le=50)
    source: bool = True


class DataResponse(BaseModel):
    message: str
    data: list[dict[str, Any]] | None
    params: dict[str, Any] | None = None


def _chrome_fetch(path: str, params: dict[str, str], method: str, body: str = "") -> dict[str, Any]:
    payload = json.dumps(
        {
            "query": urlencode(params),
            "method": method,
            "path": path,
            "body": body,
        }
    ).encode("utf-8")
    req = Request(
        CHROME_FETCH,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_via_chrome(pages: int, count: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: int | str = 0
    params = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "update_version_code": "170400",
        "pc_client_type": "1",
        "version_code": "170400",
        "version_name": "17.4.0",
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "139.0.0.0",
        "browser_online": "true",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "12",
        "device_memory": "32",
        "platform": "PC",
        "publish_video_strategy_type": "2",
    }
    for _ in range(pages):
        out = _chrome_fetch(
            "/aweme/v1/web/aweme/listcollection/",
            params,
            "POST",
            f"count={count}&cursor={cursor}",
        )
        payload = out.get("payload") if isinstance(out.get("payload"), dict) else {}
        batch = payload.get("aweme_list") or []
        if not isinstance(batch, list):
            batch = []
        status = payload.get("status_code", out.get("jsonStatus"))
        if not batch and status not in (0, None):
            msg = payload.get("status_msg") or out.get("jsonMsg") or f"status={status}"
            raise RuntimeError(str(msg))
        items.extend(item for item in batch if isinstance(item, dict))
        if not payload.get("has_more"):
            break
        cursor = payload.get("cursor") or 0
        if cursor in (0, "0", None):
            break
    return items


async def fetch_collection(pages: int, count: int) -> list[dict[str, Any]]:
    chrome_error: Exception | None = None
    try:
        data = await asyncio.to_thread(fetch_via_chrome, pages, count)
        if data:
            return data
    except (URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        chrome_error = exc

    console = ColorfulConsole()
    settings = Settings(VOLUME, console)
    cookie_mod = Cookie(settings, console)
    db = Database()
    await db.__aenter__()
    parameter = None
    try:
        config = {i["NAME"]: i["VALUE"] for i in await db.read_config_data()}
        recorder = DownloadRecorder(db, config["Record"], console)
        parameter = Parameter(
            settings,
            cookie_mod,
            logger=BaseLogger,
            console=console,
            **settings.read(),
            recorder=recorder,
        )
        parameter.set_headers_cookie()
        await parameter.update_params()
        API.init_progress_object(server_mode=True)
        collection = Collection(parameter, pages=pages, count=count)
        data = await collection.run()
        if data:
            return data
        if chrome_error:
            raise chrome_error
        return []
    finally:
        if parameter is not None:
            await parameter.close_client()
        await db.__aexit__(None, None, None)


@app.post("/douyin/collection", response_model=DataResponse)
async def douyin_collection(body: CollectionRequest) -> DataResponse:
    try:
        data = await fetch_collection(body.pages or 2, body.count)
        if not data:
            return DataResponse(message="获取数据失败！", data=None, params=body.model_dump())
        return DataResponse(message="获取数据成功！", data=data, params=body.model_dump())
    except Exception as exc:  # noqa: BLE001
        return DataResponse(
            message=f"获取数据失败：{exc}",
            data=None,
            params=body.model_dump(),
        )


async def main() -> None:
    config = Config(app, host="0.0.0.0", port=5556, log_level="warning")
    server = Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
