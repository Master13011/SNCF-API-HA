"""Tests for the SNCF API client."""

import asyncio
import base64

import pytest
from aiohttp import ClientError
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.sncf_trains.api import API_BASE, SncfApiClient, encode_token

STOP_AREA = "stop_area:SNCF:87686006"
STOP_POINT = "stop_point:SNCF:87686006:Train"

DEPARTURES_AREA_URL = f"{API_BASE}/v1/coverage/sncf/stop_areas/{STOP_AREA}/departures"
DEPARTURES_POINT_URL = (
    f"{API_BASE}/v1/coverage/sncf/stop_points/{STOP_POINT}/departures"
)
JOURNEYS_URL = f"{API_BASE}/v1/coverage/sncf/journeys"
PLACES_URL = f"{API_BASE}/v1/coverage/sncf/places"


@pytest.fixture
def client(hass, aioclient_mock) -> SncfApiClient:
    """Return an API client using the mocked HTTP session."""
    return SncfApiClient(async_get_clientsession(hass), "my_key")


def _last_call(aioclient_mock):
    """Return (method, url, data, headers) of the last request."""
    return aioclient_mock.mock_calls[-1]


# --- encode_token ------------------------------------------------------------


def test_encode_token_is_basic_auth_with_empty_password():
    assert encode_token("abc") == "YWJjOg=="
    assert base64.b64decode(encode_token("my_key")).decode() == "my_key:"


# --- fetch_departures --------------------------------------------------------


async def test_fetch_departures_stop_area(client, aioclient_mock):
    aioclient_mock.get(DEPARTURES_AREA_URL, json={"departures": [{"id": 1}]})

    result = await client.fetch_departures(STOP_AREA, max_results=5)

    assert result == [{"id": 1}]
    _, url, _, headers = _last_call(aioclient_mock)
    assert url.query["count"] == "5"
    assert url.query["data_freshness"] == "realtime"
    assert headers["Authorization"] == f"Basic {encode_token('my_key')}"


async def test_fetch_departures_stop_point(client, aioclient_mock):
    aioclient_mock.get(DEPARTURES_POINT_URL, json={"departures": [{"id": 2}]})

    assert await client.fetch_departures(STOP_POINT) == [{"id": 2}]
    assert _last_call(aioclient_mock)[1].query["count"] == "10"


async def test_fetch_departures_rejects_unknown_id_without_request(
    client, aioclient_mock
):
    with pytest.raises(ValueError):
        await client.fetch_departures("admin:fr:69123")
    assert aioclient_mock.call_count == 0


async def test_fetch_departures_without_departures_key(client, aioclient_mock):
    aioclient_mock.get(DEPARTURES_AREA_URL, json={})
    assert await client.fetch_departures(STOP_AREA) == []


async def test_fetch_departures_unauthorized(client, aioclient_mock):
    aioclient_mock.get(DEPARTURES_AREA_URL, status=401)
    with pytest.raises(ConfigEntryAuthFailed):
        await client.fetch_departures(STOP_AREA)


async def test_fetch_departures_rate_limited(client, aioclient_mock):
    aioclient_mock.get(DEPARTURES_AREA_URL, status=429)
    with pytest.raises(RuntimeError):
        await client.fetch_departures(STOP_AREA)


async def test_fetch_departures_server_error_returns_none(client, aioclient_mock):
    aioclient_mock.get(DEPARTURES_AREA_URL, status=500)
    assert await client.fetch_departures(STOP_AREA) is None


@pytest.mark.parametrize("error", [ClientError("boom"), asyncio.TimeoutError()])
async def test_fetch_departures_network_error_returns_none(
    client, aioclient_mock, error
):
    aioclient_mock.get(DEPARTURES_AREA_URL, exc=error)
    assert await client.fetch_departures(STOP_AREA) is None


# --- fetch_journeys ----------------------------------------------------------


async def test_fetch_journeys_sends_expected_query(client, aioclient_mock):
    aioclient_mock.get(JOURNEYS_URL, json={"journeys": [{"id": "j1"}]})

    result = await client.fetch_journeys(
        "stop_area:dep", "stop_area:arr", "20261109T070000", count=7
    )

    assert result == [{"id": "j1", "disruptions": []}]
    _, url, _, headers = _last_call(aioclient_mock)
    assert url.query["from"] == "stop_area:dep"
    assert url.query["to"] == "stop_area:arr"
    assert url.query["datetime"] == "20261109T070000"
    assert url.query["count"] == "7"
    assert url.query["datetime_represents"] == "departure"
    assert url.query["data_freshness"] == "realtime"
    assert headers["Authorization"] == f"Basic {encode_token('my_key')}"


async def test_fetch_journeys_attaches_disruptions(client, aioclient_mock):
    aioclient_mock.get(
        JOURNEYS_URL,
        json={
            "journeys": [
                {
                    "sections": [
                        {"display_informations": {"links": [{"type": "disruption", "id": "d1"}]}}
                    ]
                },
                {"sections": []},
            ],
            "disruptions": [{"id": "d1", "severity": {"effect": "SIGNIFICANT_DELAYS"}}],
        },
    )

    journeys = await client.fetch_journeys("a", "b", "20261109T070000")

    assert journeys[0]["disruptions"] == [
        {"id": "d1", "severity": {"effect": "SIGNIFICANT_DELAYS"}}
    ]
    assert journeys[1]["disruptions"] == []


async def test_fetch_journeys_without_journeys_key(client, aioclient_mock):
    aioclient_mock.get(JOURNEYS_URL, json={"error": {"message": "no solution"}})
    assert await client.fetch_journeys("a", "b", "20261109T070000") == []


async def test_fetch_journeys_unauthorized(client, aioclient_mock):
    aioclient_mock.get(JOURNEYS_URL, status=401)
    with pytest.raises(ConfigEntryAuthFailed):
        await client.fetch_journeys("a", "b", "20261109T070000")


async def test_fetch_journeys_rate_limited(client, aioclient_mock):
    aioclient_mock.get(JOURNEYS_URL, status=429)
    with pytest.raises(RuntimeError):
        await client.fetch_journeys("a", "b", "20261109T070000")


async def test_fetch_journeys_server_error_returns_none(client, aioclient_mock):
    aioclient_mock.get(JOURNEYS_URL, status=503)
    assert await client.fetch_journeys("a", "b", "20261109T070000") is None


@pytest.mark.parametrize("error", [ClientError("boom"), asyncio.TimeoutError()])
async def test_fetch_journeys_network_error_returns_none(
    client, aioclient_mock, error
):
    aioclient_mock.get(JOURNEYS_URL, exc=error)
    assert await client.fetch_journeys("a", "b", "20261109T070000") is None


# --- search_stations ---------------------------------------------------------


async def test_search_stations_returns_places(client, aioclient_mock):
    aioclient_mock.get(
        PLACES_URL, json={"places": [{"id": "stop_area:x", "name": "Lyon"}]}
    )

    result = await client.search_stations("Lyon")

    assert result == [{"id": "stop_area:x", "name": "Lyon"}]
    _, url, _, headers = _last_call(aioclient_mock)
    assert url.query["q"] == "Lyon"
    assert url.query["type[]"] == "stop_point"
    assert headers["Authorization"] == f"Basic {encode_token('my_key')}"


async def test_search_stations_without_places_key(client, aioclient_mock):
    aioclient_mock.get(PLACES_URL, json={})
    assert await client.search_stations("zzz") == []


async def test_search_stations_server_error_returns_none(client, aioclient_mock):
    aioclient_mock.get(PLACES_URL, status=500)
    assert await client.search_stations("Lyon") is None


@pytest.mark.parametrize("error", [ClientError("boom"), asyncio.TimeoutError()])
async def test_search_stations_network_error_returns_none(
    client, aioclient_mock, error
):
    aioclient_mock.get(PLACES_URL, exc=error)
    assert await client.search_stations("Lyon") is None
