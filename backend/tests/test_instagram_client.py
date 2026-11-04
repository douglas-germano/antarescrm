from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from app.common import APIError
from app.services.instagram import client, fetch_account, fetch_profile
from helpers.instagram import configure_instagram


def response(body, ok=True):
    return SimpleNamespace(ok=ok, json=lambda: body)


def test_graph_adapter_passes_bearer_credentials_and_bounded_timeouts(env, monkeypatch):
    web, data = env
    configure_instagram(web, data)
    web.application.config['INSTAGRAM_API_VERSION'] = 'v42.0'
    send = Mock(return_value=response({'message_id': 'provider-message'}))
    monkeypatch.setattr(client.requests, 'request', send)
    assert (
        client.graph('1234/messages', 'private-token', method='POST', json={'message': {'text': 'hello'}})['message_id']
        == 'provider-message'
    )
    assert send.call_args.args == ('POST', 'https://graph.instagram.com/v42.0/1234/messages')
    assert send.call_args.kwargs['headers'] == {'Authorization': 'Bearer private-token'}
    assert send.call_args.kwargs['timeout'] == (5, 20)


@pytest.mark.parametrize(
    'failure', [requests.RequestException('private-provider-token'), ValueError('private-provider-token')]
)
def test_graph_adapter_errors_do_not_expose_provider_secrets(env, monkeypatch, failure):
    monkeypatch.setattr(client.requests, 'request', Mock(side_effect=failure))
    with pytest.raises(APIError) as error:
        client.graph('me', 'private-provider-token')
    assert error.value.status == 502
    assert 'private-provider-token' not in error.value.message


def test_graph_adapter_rejects_provider_errors_and_invalid_account_profiles(env, monkeypatch):
    monkeypatch.setattr(
        client.requests, 'request', Mock(return_value=response({'error': {'message': 'private'}}, False))
    )
    with pytest.raises(APIError):
        client.graph('me', 'private-token')
    monkeypatch.setattr(
        client, 'graph', lambda *args, **kwargs: {'user_id': 'not-a-professional-account', 'username': 'user'}
    )
    with pytest.raises(APIError) as error:
        client.profile('private-token')
    assert error.value.status == 422


def test_oauth_adapter_exchanges_tokens_and_rejects_missing_long_lived_token(env, monkeypatch):
    web, data = env
    configure_instagram(web, data)
    initial = Mock(return_value=response({'access_token': 'short-token'}))
    exchange = Mock(return_value=response({'access_token': 'long-token', 'expires_in': 1000}))
    monkeypatch.setattr(client.requests, 'post', initial)
    monkeypatch.setattr(client.requests, 'get', exchange)
    assert client.oauth_tokens('authorization-code') == {'access_token': 'long-token', 'expires_in': 1000}
    assert initial.call_args.kwargs['data']['code'] == 'authorization-code'
    assert exchange.call_args.kwargs['params']['access_token'] == 'short-token'
    exchange.return_value = response({'access_token': 'long-token'})
    with pytest.raises(APIError) as error:
        client.oauth_tokens('authorization-code')
    assert error.value.status == 502


def test_profile_adapter_best_effort_and_invalid_encryption(env, monkeypatch):
    web, data = env
    connection = configure_instagram(web, data)
    get = Mock(return_value=response({'name': 'Joana', 'username': 'joana'}))
    monkeypatch.setattr(client.requests, 'get', get)
    assert fetch_profile(connection, '5678') == {'name': 'Joana', 'username': 'joana'}
    assert get.call_args.kwargs['timeout'] == (2, 4)
    assert fetch_account('private-token') == {'name': 'Joana', 'username': 'joana'}
    assert get.call_args.kwargs['timeout'] == (2, 5)
    get.return_value = response({'error': {}}, False)
    assert fetch_account('private-token') is None
    assert fetch_profile(connection, '5678') is None
    connection.encrypted_token = 'not-encrypted'
    assert fetch_profile(connection, '5678') is None
