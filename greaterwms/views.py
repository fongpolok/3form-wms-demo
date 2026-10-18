import mimetypes

from django.conf import settings
from django.http import FileResponse


def favicon(request):
    path = settings.BASE_DIR / 'frontend' / 'dist' / 'brand' / 'favicon.png'
    content_type, _ = mimetypes.guess_type(str(path))
    resp = FileResponse(open(path, 'rb'), content_type=content_type)
    resp['Cache-Control'] = "max-age=86400"
    return resp


def spa(request, *args, **kwargs):
    """Serve the built Vue app. Read from disk on every request (no template
    caching), so a rebuilt frontend is picked up without restarting Django."""
    path = settings.BASE_DIR / 'frontend' / 'dist' / 'index.html'
    if not path.exists():
        from django.http import HttpResponse
        return HttpResponse("Frontend not built yet. Run: cd frontend && npm install && npm run build", status=503,
                            content_type="text/plain")
    resp = FileResponse(open(path, 'rb'), content_type='text/html; charset=utf-8')
    resp['Cache-Control'] = 'no-cache'
    return resp
