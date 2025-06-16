from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    # The regex now correctly captures a UUID.
    re_path(r'ws/docs/(?P<document_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/$', consumers.DocConsumer.as_asgi()),
]
