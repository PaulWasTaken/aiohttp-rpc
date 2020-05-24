import aiohttp_rpc

import pytest

from aiohttp_rpc import exceptions
from tests import utils


@pytest.mark.asyncio
async def test_args(aiohttp_client):
    def method(a=1):
        return [1, 2, a]

    rpc_server = aiohttp_rpc.JsonRpcServer()
    rpc_server.add_method(method)

    assert await rpc_server.call('method') == [1, 2, 1]
    assert await rpc_server.call('method', args=[1]) == [1, 2, 1]

    client = await utils.make_client(aiohttp_client, rpc_server)

    async with aiohttp_rpc.JsonRpcClient('/rpc', session=client) as rpc:
        assert await rpc.call('method') == [1, 2, 1]
        assert await rpc.call('method', 1) == [1, 2, 1]


@pytest.mark.asyncio
async def test_kwargs(aiohttp_client):
    def method(a=1, *, b=2):
        return [1, a, b]

    rpc_server = aiohttp_rpc.JsonRpcServer()
    rpc_server.add_method(method)

    with pytest.raises(exceptions.InvalidParams):
        await rpc_server.call('method', args=[1, 2])

    assert await rpc_server.call('method', kwargs={'a': 1, 'b': 2}) == [1, 1, 2]
    assert await rpc_server.call('method', args=[2], kwargs={'b': 2}) == [1, 2, 2]

    client = await utils.make_client(aiohttp_client, rpc_server)

    async with aiohttp_rpc.JsonRpcClient('/rpc', session=client) as rpc:
        assert await rpc.call('method', a=1, b=2) == [1, 1, 2]

        with pytest.raises(exceptions.InvalidParams):
            await rpc.call('method', 2, b=2)


@pytest.mark.asyncio
async def test_varargs(aiohttp_client):
    def method(a=1, *args):
        return [a, *args]

    rpc_server = aiohttp_rpc.JsonRpcServer()
    rpc_server.add_method(method)

    assert await rpc_server.call('method') == [1]
    assert await rpc_server.call('method', args=[2]) == [2]
    assert await rpc_server.call('method', args=[2, 3]) == [2, 3]

    client = await utils.make_client(aiohttp_client, rpc_server)

    async with aiohttp_rpc.JsonRpcClient('/rpc', session=client) as rpc:
        assert await rpc.call('method') == [1]
        assert await rpc.call('method', 2) == [2]
        assert await rpc.call('method', 2, 3) == [2, 3]


@pytest.mark.asyncio
async def test_varkw(aiohttp_client):
    def method(a=1, **kwargs):
        return [a, kwargs]

    rpc_server = aiohttp_rpc.JsonRpcServer()
    rpc_server.add_method(method)

    with pytest.raises(exceptions.InvalidParams):
        await rpc_server.call('method', args=[1, 2])

    assert await rpc_server.call('method', kwargs={'a': 1, 'b': 2}) == [1, {'b': 2}]

    client = await utils.make_client(aiohttp_client, rpc_server)

    async with aiohttp_rpc.JsonRpcClient('/rpc', session=client) as rpc:
        with pytest.raises(exceptions.InvalidParams):
            await rpc.call('method', 1, 2)

        assert await rpc.call('method', a=1, b=2) == [1, {'b': 2}]

