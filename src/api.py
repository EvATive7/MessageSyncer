import asyncio
import mimetypes
import time
from typing import Annotated, Any, Optional, Union

import uvicorn
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config
import core
import log
import runtime
import store
import task
import util
from model import *

HOST = "0.0.0.0"
PORT = config.main().api.port

# Update this field every time when a destructive update is made.
# If a destructive update is made, use this field to control the response model of API.
# [20241222]
VERSION = 20241222

app = FastAPI(title="MessageSyncerAPI", version=str(VERSION))
api_router = APIRouter(prefix="/api")
res_router = APIRouter(prefix="/res")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.main().api.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"msg": "Internal server error"})


@app.exception_handler(HTTPException)
async def generic_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


def authenticate(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    if credentials.credentials not in config.main().api.token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return True


@dataclass
class AdapterClassInfo:
    name: str
    version: str

    @staticmethod
    def from_class(adapter: type):
        return AdapterClassInfo(
            name=adapter.__name__,
            version=util.get_git_version(adapter._import_path),
        )


@dataclass
class GetterInfo:
    name: str
    class_name: str
    working: bool
    config: dict
    instance_config: dict

    @staticmethod
    def from_getter(getter: Getter):
        return GetterInfo(
            name=getter.name,
            class_name=getter.class_name,
            working=getter._working,
            config=getter.config,
            instance_config=getter.instance_config,
        )


@dataclass
class Article:
    id: str
    userId: str
    ts: int
    content: list[dict]


@dataclass
class AdapterInstallRequestBody:
    url: str


@app.get("/", include_in_schema=False)
async def _():
    return RedirectResponse("./docs")


@api_router.get("/")
async def hello_world() -> dict:
    return {
        "version": {
            "api": VERSION,
            "MessageSyncer": runtime.version,
        }
    }


@api_router.post("/pairs/update_getters", tags=["Pair"])
async def update_getters(auth=Depends(authenticate)):
    core.update_getters()


def _get_adapter(adapter: str):
    return adapter


@api_router.post("/adapter/", response_model=type(None), tags=["Adapter"])
async def install_adapter(body: AdapterInstallRequestBody, auth=Depends(authenticate)):
    try:
        core.install_adapter(body.url)
    except core.AdapterAlreadyExist:
        raise HTTPException(status.HTTP_409_CONFLICT)


@api_router.delete(
    "/adapter/{adapter:str}", response_model=type(None), tags=["Adapter"]
)
async def uninstall_adapter(
    adapter: str = Depends(_get_adapter), auth=Depends(authenticate)
):
    try:
        core.uninstall_adapter(adapter)
    except core.AdapterNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND)


def _get_adapter_class(adapter_class: str) -> Getter:
    ls = [_c for _c in core.imported_adapter_classes if _c.__name__ == adapter_class]
    if len(ls) != 0:
        return ls[0]
    raise HTTPException(status.HTTP_404_NOT_FOUND)


@api_router.get("/adapter_classes/", tags=["AdapterClass"])
async def list_all_adapter_classes(
    auth=Depends(authenticate),
) -> list[AdapterClassInfo]:
    return [AdapterClassInfo.from_class(_c) for _c in core.imported_adapter_classes]


@api_router.get("/adapter_classes/{adapter_class:str}", tags=["AdapterClass"])
async def adapter_class(
    adapter_class: str = Depends(_get_adapter_class), auth=Depends(authenticate)
) -> AdapterClassInfo:
    return AdapterClassInfo.from_class(adapter_class)


@api_router.post(
    "/adapter_classes/{adapter_class:str}/reload",
    response_model=type(None),
    tags=["AdapterClass"],
)
async def reload_adapter_class(
    adapter_class: str = Depends(_get_adapter_class), auth=Depends(authenticate)
):
    core.reload_adapter_class(adapter_class)


def _get_config_manager(config_name: str) -> config.HotReloadConfigManager:
    return config.get_config_manager(name=config_name)


@api_router.get("/config/{config_name:str}", tags=["Config"])
async def get_config(
    config_manager: config.HotReloadConfigManager = Depends(_get_config_manager),
    auth=Depends(authenticate),
) -> dict:
    return config_manager.dict


@api_router.post(
    "/config/{config_name:str}", tags=["Config"], response_model=type(None)
)
async def update_config(
    new: dict,
    config_manager: config.HotReloadConfigManager = Depends(_get_config_manager),
    auth=Depends(authenticate),
):
    config_manager.save_dict(new)


@api_router.get("/config/{config_name:str}/jsonschema", tags=["Config"])
async def get_config_jsonschema(
    config_manager: config.HotReloadConfigManager = Depends(_get_config_manager),
    auth=Depends(authenticate),
) -> dict:
    return config_manager.jsonschema


def _get_getter(getter_str: str) -> Getter:
    ls = [_getter for _getter in core.registered_getters if _getter.name == getter_str]
    if len(ls) != 0:
        return ls[0]
    raise HTTPException(status.HTTP_404_NOT_FOUND)


@api_router.get("/getters/", tags=["Getter"])
async def list_all_getters(auth=Depends(authenticate)) -> list[GetterInfo]:
    return [
        asdict(GetterInfo.from_getter(getter)) for getter in core.registered_getters
    ]


@api_router.post("/getters/refresh", tags=["Getter"])
async def refresh_getters_async(auth=Depends(authenticate)) -> core.RefreshResult:
    return JSONResponse(
        [
            task.create_task(core.refresh(_getter))
            for _getter in core.registered_getters
        ],
        status_code=status.HTTP_202_ACCEPTED,
    )


@api_router.get("/getters/{getter:str}", tags=["Getter"])
async def getter(
    getter: Getter = Depends(_get_getter), auth=Depends(authenticate)
) -> GetterInfo:
    return GetterInfo.from_getter(getter)


@api_router.post("/getters/{getter:str}/refresh", tags=["Getter"])
async def refresh_getter_async(
    getter: Getter = Depends(_get_getter), auth=Depends(authenticate)
) -> core.RefreshResult:
    return JSONResponse(
        task.create_task(core.refresh(getter)), status_code=status.HTTP_202_ACCEPTED
    )


def _get_article(id: str) -> store.Article:
    ar = store.Article.get_or_none(store.Article.id == id)
    if ar:
        return ar
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND)


@api_router.get("/articles/", tags=["Article"])
async def list_articles(
    page: int = 0, page_size: int = 10, auth=Depends(authenticate)
) -> list[Article]:
    return [
        Article(ar.id, ar.userId, ar.ts, ar.content.asdict())
        for ar in store.Article.select()
        .order_by(store.Article.ts.desc())
        .paginate(page, page_size)
    ]


@api_router.get("/articles/{id}", tags=["Article"])
async def article(
    article: store.Article = Depends(_get_article), auth=Depends(authenticate)
) -> Article:
    return Article(article.id, article.userId, article.ts, article.content.asdict())


@api_router.get("/log/", tags=["Log"])
async def list_log(
    page: int = 0, page_size: int = 10, auth=Depends(authenticate)
) -> list[str]:
    data_list = log.log_list
    start_index = max(0, len(data_list) - (page + 1) * page_size)
    end_index = len(data_list) - page * page_size
    return data_list[start_index:end_index]


def _get_task(task_id: str):
    if task_ := task.tasks.get(task_id):
        return task_
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND)


@api_router.get("/task/", tags=["Task"])
async def get_tasks(
    done: bool | None = None,
) -> list[str]:
    _final_tasks = list(task.tasks.keys())
    if done is not None:
        if done is True:
            _final_tasks = [
                _taskid for _taskid in _final_tasks if task.tasks[_taskid].done()
            ]
        elif done is False:
            _final_tasks = [
                _taskid for _taskid in _final_tasks if not task.tasks[_taskid].done()
            ]
    return _final_tasks


@api_router.get("/task/{task_id}", tags=["Task"])
async def task_status(
    task_: asyncio.Task = Depends(_get_task), auth=Depends(authenticate)
) -> dict:
    if task_.done():
        return task_.result()
    else:
        return Response(None, status.HTTP_202_ACCEPTED)


def _get_img(img_id):
    img = store.ImageStorage.get_or_none(store.ImageStorage.id == img_id)
    return img


@res_router.get("/img/{img_id}", tags=["Image"])
async def get_img(img: asyncio.Task = Depends(_get_img)) -> dict:
    file_path = Path("data/pic") / img.filename
    return FileResponse(str(file_path.absolute()), media_type=img.mime)


app.include_router(api_router)
app.include_router(res_router)


async def serve():
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            log_config={
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {},
                "handlers": {},
                "loggers": {
                    "uvicorn": {"handlers": [], "level": "DEBUG", "propagate": False},
                    "uvicorn.error": {
                        "handlers": [],
                        "level": "DEBUG",
                        "propagate": False,
                    },
                    "uvicorn.access": {
                        "handlers": [],
                        "level": "WARNING",
                        "propagate": False,
                    },
                },
            },
        )
    )

    log.getLogger("uvicorn").handlers = log.root.handlers
    log.getLogger("uvicorn.error").handlers = log.root.handlers
    log.getLogger("uvicorn.access").handlers = log.root.handlers

    await server.serve()
