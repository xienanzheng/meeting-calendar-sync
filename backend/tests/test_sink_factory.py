import pytest

from mcs.calendar import SinkNotConfigured, get_sink
from mcs.calendar.graph import GraphSink
from mcs.calendar.graph_auth import GraphAuth
from mcs.calendar.ics import IcsSink
from mcs.config import Settings


def make(**kw):
    return Settings(_env_file=None, use_keychain=False, **kw)


def test_ics_is_default():
    assert isinstance(get_sink(make()), IcsSink)


def test_graph_without_configuration_raises():
    with pytest.raises(SinkNotConfigured, match="not configured"):
        get_sink(make(calendar_sink="graph"), GraphAuth(None, None))


def test_graph_with_configuration():
    auth = GraphAuth("cid", "tid", app_factory=lambda client_id, authority: object())
    assert isinstance(get_sink(make(calendar_sink="graph"), auth), GraphSink)
