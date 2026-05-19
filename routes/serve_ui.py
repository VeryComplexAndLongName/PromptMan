from fastapi.responses import FileResponse


def serve_ui_route() -> FileResponse:
    return FileResponse("ui/html/index.html")
