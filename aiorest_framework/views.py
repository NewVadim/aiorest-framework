import json
import asyncio
import logging

from aiohttp import web

from .exceptions import PermissionDenied, APIException
from .status import HTTP_200_OK
from .request import Request

__author__ = 'vadim'


class APIView(web.View):
    permission_classes = []

    def __init__(self, request):
        super(APIView, self).__init__(request)
        self._request = Request(self._request)
        self.status_code = HTTP_200_OK

    @asyncio.coroutine
    def __iter__(self):
        try:
            yield from self.check_permissions()
            data = yield from super(APIView, self).__iter__()
        except APIException as exc:
            data = exc.detail
            self.status_code = exc.status_code

        logging.debug(json.dumps(data))

        return web.Response(
            body=json.dumps(data).encode('utf-8') if data is not None else None,
            content_type='application/json',
            status=self.status_code,
        )

    async def check_permissions(self):
        """
        Check if the request should be permitted.
        Raises an appropriate exception if the request is not permitted.
        """
        for permission in self.get_permissions():
            if not await permission.has_permission(self.request, self):
                self.permission_denied(message=getattr(permission, 'message', None))

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        return [permission() for permission in self.permission_classes]

    def permission_denied(self, message=None):
        """
        If request is not permitted, determine what kind of exception to raise.
        """
        raise PermissionDenied(detail=message)
