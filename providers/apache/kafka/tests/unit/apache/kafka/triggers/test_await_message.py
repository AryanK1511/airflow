# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import asyncio
import json

import pytest

from airflow.models import Connection
from airflow.providers.apache.kafka.hooks.consume import KafkaConsumerHook
from airflow.providers.apache.kafka.triggers.await_message import AwaitMessageTrigger

from tests_common.test_utils.version_compat import AIRFLOW_V_3_0_PLUS, get_base_airflow_version_tuple


def apply_function_false(message):
    return False


def apply_function_true(message):
    return True


class MockedMessage:
    def __init__(*args, **kwargs):
        pass

    def error(*args, **kwargs):
        return False


class MockedConsumer:
    def __init__(*args, **kwargs) -> None:
        pass

    def poll(*args, **kwargs):
        return MockedMessage()

    def commit(*args, **kwargs):
        return True


class TestTrigger:
    @pytest.fixture(autouse=True)
    def setup_connections(self, create_connection_without_db):
        create_connection_without_db(
            Connection(
                conn_id="kafka_d",
                conn_type="kafka",
                extra=json.dumps(
                    {"socket.timeout.ms": 10, "bootstrap.servers": "localhost:9092", "group.id": "test_group"}
                ),
            )
        )

    def test_trigger_serialization(self):
        trigger = AwaitMessageTrigger(
            kafka_config_id="kafka_d",
            apply_function="test.noop",
            topics=["noop"],
            apply_function_args=[1, 2],
            apply_function_kwargs=dict(one=1, two=2),
            poll_timeout=10,
            poll_interval=5,
        )

        assert isinstance(trigger, AwaitMessageTrigger)

        classpath, kwargs = trigger.serialize()

        assert classpath == "airflow.providers.apache.kafka.triggers.await_message.AwaitMessageTrigger"
        assert kwargs == dict(
            kafka_config_id="kafka_d",
            apply_function="test.noop",
            topics=["noop"],
            apply_function_args=[1, 2],
            apply_function_kwargs=dict(one=1, two=2),
            poll_timeout=10,
            poll_interval=5,
        )

    @pytest.mark.asyncio
    async def test_trigger_run_good(self, mocker):
        mocker.patch.object(KafkaConsumerHook, "get_consumer", return_value=MockedConsumer)

        trigger = AwaitMessageTrigger(
            kafka_config_id="kafka_d",
            apply_function="unit.apache.kafka.triggers.test_await_message.apply_function_true",
            topics=["noop"],
            poll_timeout=0.0001,
            poll_interval=5,
        )

        task = asyncio.create_task(trigger.run().__anext__())
        await asyncio.sleep(1.0)
        assert task.done() is True
        asyncio.get_event_loop().stop()

    @pytest.mark.asyncio
    async def test_trigger_run_bad(self, mocker):
        mocker.patch.object(KafkaConsumerHook, "get_consumer", return_value=MockedConsumer)

        trigger = AwaitMessageTrigger(
            kafka_config_id="kafka_d",
            apply_function="unit.apache.kafka.triggers.test_await_message.apply_function_false",
            topics=["noop"],
            poll_timeout=0.0001,
            poll_interval=5,
        )

        task = asyncio.create_task(trigger.run().__anext__())
        await asyncio.sleep(1.0)
        assert task.done() is False
        asyncio.get_event_loop().stop()


@pytest.mark.skipif(not AIRFLOW_V_3_0_PLUS, reason="Requires Airflow 3.0.+")
class TestMessageQueueTrigger:
    def test_provider_integrations(self, cleanup_providers_manager):
        if get_base_airflow_version_tuple() < (3, 0, 1):
            pytest.skip("This test is only for Airflow 3.0.1+")

        queue = "kafka://localhost:9092/topic1"
        from airflow.providers.common.messaging.triggers.msg_queue import MessageQueueTrigger

        trigger = MessageQueueTrigger(queue=queue, apply_function="mock_kafka_trigger_apply_function")
        assert isinstance(trigger.trigger, AwaitMessageTrigger)
