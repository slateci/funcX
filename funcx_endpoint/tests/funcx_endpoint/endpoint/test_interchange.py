import logging
import os
import shutil
from importlib.machinery import SourceFileLoader

import pika
import pytest

from funcx_endpoint.endpoint.endpoint import Endpoint
from funcx_endpoint.endpoint.interchange import EndpointInterchange

logger = logging.getLogger("mock_funcx")


class TestStart:
    @pytest.fixture(autouse=True)
    def test_setup_teardown(self):
        # Code that will run before your test, for example:

        funcx_dir = f"{os.getcwd()}"
        config_dir = os.path.join(funcx_dir, "mock_endpoint")
        assert not os.path.exists(config_dir)
        # A test function will be run at this point
        yield
        # Code that will run after your test, for example:
        shutil.rmtree(config_dir)

    def test_endpoint_id(self, mocker):
        mock_client = mocker.patch("funcx_endpoint.endpoint.interchange.FuncXClient")
        mock_client.return_value = None

        manager = Endpoint(funcx_dir=os.getcwd())
        config_dir = os.path.join(manager.funcx_dir, "mock_endpoint")

        manager.configure_endpoint("mock_endpoint", None)
        endpoint_config = SourceFileLoader(
            "config", os.path.join(config_dir, "config.py")
        ).load_module()

        for executor in endpoint_config.config.executors:
            executor.passthrough = False

        ic = EndpointInterchange(
            endpoint_config.config,
            reg_info=None,
            endpoint_id="mock_endpoint_id",
        )

        for executor in ic.executors.values():
            assert executor.endpoint_id == "mock_endpoint_id"

    def test_start_no_reg_info(self, mocker):
        mocker.patch("funcx_endpoint.endpoint.interchange.threading.Thread")

        def _fake_retry(func, *args, **kwargs):
            return func()

        mocker.patch("funcx_endpoint.endpoint.interchange.retry_call", _fake_retry)

        mock_client = mocker.patch("funcx_endpoint.endpoint.interchange.FuncXClient")
        mock_client.return_value = None

        mock_register_endpoint = mocker.patch(
            "funcx_endpoint.endpoint.interchange.register_endpoint"
        )
        result_url = "amqp://localhost:5672"
        task_url = "amqp://localhost:5672"
        mock_register_endpoint.return_value = (
            {
                "exchange_name": "results",
                "exchange_type": "topic",
                "result_url": result_url,
                "pika_conn_params": pika.URLParameters(result_url),
            },
            {
                "exchange_name": "tasks",
                "exchange_type": "direct",
                "task_url": task_url,
                "pika_conn_params": pika.URLParameters(task_url),
            },
        )

        manager = Endpoint(funcx_dir=os.getcwd())
        config_dir = os.path.join(manager.funcx_dir, "mock_endpoint")

        manager.configure_endpoint("mock_endpoint", None)
        endpoint_config = SourceFileLoader(
            "config", os.path.join(config_dir, "config.py")
        ).load_module()

        for executor in endpoint_config.config.executors:
            executor.passthrough = False

        mock_quiesce = mocker.patch.object(
            EndpointInterchange, "quiesce", return_value=None
        )
        mock_main_loop = mocker.patch.object(
            EndpointInterchange, "_main_loop", return_value=None
        )

        ic = EndpointInterchange(
            config=endpoint_config.config,
            reg_info=None,
            endpoint_id="mock_endpoint_id",
        )

        ic.results_outgoing = mocker.Mock()

        # this must be set to force the retry loop in the start method to only run once
        ic._test_start = True
        ic.start()

        # we need to ensure that retry_call is called during interchange
        # start if reg_info has not been passed into the interchange
        mock_quiesce.assert_called()
        mock_main_loop.assert_called()
        mock_register_endpoint.assert_called()
