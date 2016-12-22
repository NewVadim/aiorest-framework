
__author__ = 'vadim'


class Request:
    def __init__(self, request):
        self._request = request
        self._data = None

    @property
    async def data(self):
        if not self._data:
            if self._request.method == 'GET':
                self._data = self._request.GET

            self._data = await self._request.post()

        return self._data

    def __getattribute__(self, attr):
        """
        If an attribute does not exist on this instance, then we also attempt
        to proxy it to the underlying HttpRequest object.
        """
        try:
            return super(Request, self).__getattribute__(attr)
        except AttributeError:
            return getattr(self._request, attr)