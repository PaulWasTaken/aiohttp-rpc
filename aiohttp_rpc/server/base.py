import abc
import asyncio
import typing

from aiohttp import web

from .. import constants, errors, middlewares as rpc_middleware, protocol, utils


__all__ = (
    'BaseJsonRpcServer',
)


class BaseJsonRpcServer(abc.ABC):
    methods: typing.Dict[str, protocol.JsonRpcMethod]
    middlewares: typing.Tuple[typing.Type[rpc_middleware.BaseJsonRpcMiddleware], ...]
    json_serialize: typing.Callable
    _middleware_chain: typing.Callable

    def __init__(self, *,
                 json_serialize: typing.Callable = utils.json_serialize,
                 middlewares: typing.Iterable = (),
                 methods: typing.Optional[typing.Dict[str, protocol.JsonRpcMethod]] = None) -> None:
        if methods is None:
            methods = {'get_methods': protocol.JsonRpcMethod('', self.get_methods)}

        self.methods = methods

        self.middlewares = tuple(middlewares)
        self.load_middlewares()

        self.json_serialize = json_serialize

    def load_middlewares(self):
        self._middleware_chain = self._process_single_request

        for middleware_class in reversed(self.middlewares):
            if isinstance(middleware_class, (list, tuple,)):
                middleware_class, kwargs = middleware_class
                self._middleware_chain = middleware_class(server=self, get_response=self._middleware_chain, **kwargs)
                continue

            self._middleware_chain = middleware_class(server=self, get_response=self._middleware_chain)

    def add_method(self,
                   method: typing.Union[protocol.JsonRpcMethod, tuple, list, typing.Callable], *,
                   replace: bool = False) -> protocol.JsonRpcMethod:
        if not isinstance(method, protocol.JsonRpcMethod):
            if callable(method):
                method = protocol.JsonRpcMethod('', method)
            else:
                method = protocol.JsonRpcMethod(*method)

        if not replace and method.name in self.methods:
            raise errors.InvalidParams(f'Method {method.name} has already been added.')

        self.methods[method.name] = method

        return method

    def add_methods(self,
                    methods: typing.Iterable[typing.Union[protocol.JsonRpcMethod, tuple, list, typing.Callable]], *,
                    replace: bool = False) -> typing.List[protocol.JsonRpcMethod]:
        return [
            self.add_method(method, replace=replace)
            for method in methods
        ]

    async def call(self,
                   method: str, *,
                   args: typing.Optional[list] = None,
                   kwargs: typing.Optional[dict] = None,
                   extra_args: typing.Optional[dict] = None) -> typing.Any:
        if args is None:
            args = []

        if kwargs is None:
            kwargs = {}

        if method not in self.methods:
            raise errors.MethodNotFound

        return await self.methods[method](args=args, kwargs=kwargs, extra_args=extra_args)

    def get_methods(self) -> dict:
        return {
            name: {
                'doc': method.func.__doc__,
                'args': method.supported_args,
                'kwargs': method.supported_kwargs,
            }
            for name, method in self.methods.items()
        }

    async def _process_input_data(self,
                                  data: typing.Union[dict, list], *,
                                  http_request: typing.Optional[web.Request] = None) -> typing.Any:
        if isinstance(data, list):
            json_responses = await asyncio.gather(*(
                self._process_single_json_request(raw_rcp_request, http_request=http_request)
                for raw_rcp_request in data
            ), return_exceptions=True)

            for i, json_response in enumerate(json_responses):
                if isinstance(json_response, errors.JsonRpcError):
                    json_responses[i] = protocol.JsonRpcResponse(error=json_response)
                elif isinstance(json_response, Exception):
                    json_responses[i] = protocol.JsonRpcResponse(
                        error=errors.JsonRpcError(utils.get_exc_message(json_response)),
                    )

            return json_responses

        if isinstance(data, dict):
            return await self._process_single_json_request(data, http_request=http_request)

        response = protocol.JsonRpcResponse(error=errors.ParseError('Data must be a dict or an list.'))
        return response.to_dict()

    async def _process_single_json_request(self,
                                           json_request: dict, *,
                                           http_request: typing.Optional[web.Request] = None) -> dict:
        if not isinstance(json_request, dict):
            raise errors.ParseError('Data must be a dict or an list.')

        msg_id = json_request.get('id')

        try:
            request = protocol.JsonRpcRequest.from_dict(json_request, context={'http_request': http_request})
        except errors.JsonRpcError as e:
            response = protocol.JsonRpcResponse(msg_id=msg_id, error=e)
            return response.to_dict()

        response = await self._middleware_chain(request)
        return response.to_dict()

    async def _process_single_request(self, request: protocol.JsonRpcRequest) -> protocol.JsonRpcResponse:
        result, error = constants.NOTHING, constants.NOTHING

        try:
            result = await self.call(
                request.method,
                args=request.args,
                kwargs=request.kwargs,
                extra_args=request.extra_args,
            )
        except errors.JsonRpcError as e:
            error = e

        response = protocol.JsonRpcResponse(
            msg_id=request.msg_id,
            jsonrpc=request.jsonrpc,
            result=result,
            error=error,
        )

        return response