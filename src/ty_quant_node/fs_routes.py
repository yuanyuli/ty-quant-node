"""ComfyUI 内的安全本地目录浏览接口。"""

from pathlib import Path

from .core.security import configured_allowed_roots, resolve_allowed_path


def _json_error(web, message: str, status: int = 400):
    return web.json_response({"error": message}, status=status)


def register_routes() -> bool:
    """在 ComfyUI PromptServer 存在时注册目录浏览路由。

    独立运行测试或命令行环境没有 server 模块时返回 False，不影响节点导入。
    """

    try:
        from aiohttp import web
        from server import PromptServer
    except (ImportError, ModuleNotFoundError):
        return False

    routes = PromptServer.instance.routes

    @routes.get("/ty-quant-node/fs/roots")
    async def list_roots(request):
        del request
        roots = configured_allowed_roots()
        return web.json_response({"roots": [str(root) for root in roots]})

    @routes.get("/ty-quant-node/fs/list")
    async def list_directory(request):
        raw_path = request.query.get("path", "")
        if not raw_path:
            return _json_error(web, "path 不能为空")
        try:
            directory = resolve_allowed_path(raw_path, configured_allowed_roots(), must_exist=True)
        except ValueError as exc:
            return _json_error(web, str(exc), status=403)
        if not directory.is_dir():
            return _json_error(web, "path 必须是目录")
        entries = []
        try:
            children = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
            for child in children:
                if child.name.startswith("."):
                    continue
                entries.append({"name": child.name, "path": str(child), "is_dir": child.is_dir()})
        except OSError as exc:
            return _json_error(web, f"目录读取失败: {exc}", status=500)
        return web.json_response({"path": str(directory), "parent": str(directory.parent), "entries": entries})

    return True

