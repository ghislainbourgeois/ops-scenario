import pytest
from ops.charm import CharmBase
from ops.framework import Framework
from ops.model import ActiveStatus, BlockedStatus

from scenario.state import Event, Relation, State, Status, _CharmSpec


@pytest.fixture(scope="function")
def mycharm():
    class MyCharm(CharmBase):
        _call = None
        called = False

        def __init__(self, framework: Framework):
            super().__init__(framework)

            for evt in self.on.events().values():
                self.framework.observe(evt, self._on_event)

        def _on_event(self, event):
            if MyCharm._call:
                MyCharm.called = True
                MyCharm._call(self, event)

    return MyCharm


def test_charm_heals_on_start(mycharm):
    def pre_event(charm):
        pre_event._called = True
        assert charm.unit.status == BlockedStatus("foo")
        assert not charm.called

    def call(charm, _):
        if charm.unit.status.message == "foo":
            charm.unit.status = ActiveStatus("yabadoodle")

    def post_event(charm):
        post_event._called = True
        assert charm.unit.status == ActiveStatus("yabadoodle")
        assert charm.called

    mycharm._call = call

    initial_state = State(
        config={"foo": "bar"}, leader=True, status=Status(unit=BlockedStatus("foo"))
    )

    out = initial_state.trigger(
        charm_type=mycharm,
        meta={"name": "foo"},
        config={"options": {"foo": {"type": "string"}}},
        event="start",
        post_event=post_event,
        pre_event=pre_event,
    )

    assert out.status.unit == ActiveStatus("yabadoodle")

    out.juju_log = []  # exclude juju log from delta
    out.stored_state = initial_state.stored_state  # ignore stored state in delta.
    assert out.jsonpatch_delta(initial_state) == [
        {
            "op": "replace",
            "path": "/status/unit/message",
            "value": "yabadoodle",
        },
        {
            "op": "replace",
            "path": "/status/unit/name",
            "value": "active",
        },
        {
            "op": "add",
            "path": "/status/unit_history/0",
            "value": {"message": "foo", "name": "blocked"},
        },
    ]


def test_relation_data_access(mycharm):
    mycharm._call = lambda *_: True

    def check_relation_data(charm):
        foo_relations = charm.model.relations["relation_test"]
        assert len(foo_relations) == 1
        foo_rel = foo_relations[0]
        assert len(foo_rel.units) == 2

        remote_units_data = {}
        for remote_unit in foo_rel.units:
            remote_units_data[remote_unit.name] = dict(foo_rel.data[remote_unit])

        remote_app_data = foo_rel.data[foo_rel.app]

        assert remote_units_data == {
            "karlos/0": {"foo": "bar"},
            "karlos/1": {"baz": "qux"},
        }

        assert remote_app_data == {"yaba": "doodle"}

    State(
        relations=[
            Relation(
                endpoint="relation_test",
                interface="azdrubales",
                relation_id=1,
                remote_app_name="karlos",
                remote_app_data={"yaba": "doodle"},
                remote_units_data={0: {"foo": "bar"}, 1: {"baz": "qux"}},
            )
        ]
    ).trigger(
        charm_type=mycharm,
        meta={
            "name": "foo",
            "requires": {"relation_test": {"interface": "azdrubales"}},
        },
        event="update_status",
        post_event=check_relation_data,
    )
