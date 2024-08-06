import unittest, time
from unittest.mock import MagicMock, patch
from bin.har_client import HarIngester
from datetime import datetime
from requests import exceptions

epoch = datetime(1970, 1, 1)

NOW_EPOCH = int(time.time())
LAST_HALF_HOUR = int(NOW_EPOCH - 1800)


class TestHarIngester(unittest.TestCase):

    def setUp(self):
        config = {
            "access_token": "fake_token",
            "o11y_url": "https://fake.url",
            "synthetics_test_id": "fake_test_id",
            "synthetics_runlocation": "fake_location",
        }
        self.logger = MagicMock()
        self.ingester = HarIngester(config, self.logger)

    @patch("bin.har_client.requests.get")
    def test_fetch_data_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        mock_get.return_value = mock_response

        result = self.ingester.fetch_data("https://fake.url", {"param": "value"})
        self.assertEqual(result, {"key": "value"})
        self.logger.error.assert_not_called()

    @patch("bin.har_client.requests.get")
    def test_fetch_data_failure(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = exceptions.HTTPError("Not Found")
        mock_get.return_value = mock_response

        result = self.ingester.fetch_data("https://fake.url", {"param": "value"})
        self.assertIsNone(result)
        self.logger.error.assert_called_with("HTTP error occurred: Not Found")

    @patch("bin.har_client.requests.get")
    def test_get_run_time_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"key": [[1234567890000]]}}
        mock_get.return_value = mock_response

        result = self.ingester.get_run_time("check_name")
        expected_result = [
            {
                "test_id": "fake_test_id",
                "test_name": "check_name",
                "last_test_run": 1234567890000,
                "location_list": ["fake_location"],
            }
        ]
        self.assertEqual(result, expected_result)
        self.logger.warning.assert_not_called()

    @patch("bin.har_client.requests.get")
    def test_get_run_time_no_data(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            self.ingester.get_run_time("check_name")
        self.logger.warning.assert_called_with(
            f"No run data found for {LAST_HALF_HOUR}, exiting."
        )

    @patch("bin.har_client.requests.get")
    def test_get_artifacts_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "artifacts": [{"type": "har", "url": "https://fake.har.url"}]
        }
        mock_get.return_value = mock_response

        active_tests = {
            "test_id": "fake_test_id",
            "last_test_run": 1234567890000,
            "location_list": ["fake_location"],
        }
        result = self.ingester.get_artifacts(active_tests)
        self.assertEqual(result, "https://fake.har.url")

    @patch("bin.har_client.requests.get")
    def test_get_artifacts_no_artifacts(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"artifacts": []}
        mock_get.return_value = mock_response

        active_tests = {
            "test_id": "fake_test_id",
            "last_test_run": 1234567890000,
            "location_list": ["fake_location"],
        }
        result = self.ingester.get_artifacts(active_tests)
        self.assertIsNone(result)

    @patch("bin.har_client.requests.get")
    def test_get_har_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "log": {
                "pages": [{"id": "page_1", "title": "https://example.com"}],
                "entries": [
                    {
                        "startedDateTime": "2024-01-01T00:00:00.000Z",
                        "time": 100,
                        "request": {
                            "url": "https://example.com/resource",
                            "method": "GET",
                        },
                        "response": {
                            "status": 200,
                            "statusText": "OK",
                            "content": {"mimeType": "text/html", "size": 1024},
                            "headers": [],
                            "cookies": [],
                        },
                        "timings": {"blah": 1},
                        "pageref": "page_1",
                        "serverIPAddress": "192.168.1.1",
                    }
                ],
            }
        }
        mock_get.return_value = mock_response

        result = self.ingester.get_har("fake_test_id", "test_name", "/fake_har_url")
        expected_result = [
            {
                "time": 1704067200000,
                "time_taken": 100,
                "test_id": "fake_test_id",
                "test_name": "test_name",
                "resource": "https://example.com/resource",
                "content_type": "text/html",
                "content_size": 1024,
                "http_method": "GET",
                "http_status": 200,
                "http_status_description": "OK",
                "page_ref": "page_1",
                "response_headers": ["null"],
                "response_cookies": [],
                "server_ip": "192.168.1.1",
                "timings": {"blah": 1},
                "redirect_url": "",
                "page_url": "https://example.com",
            }
        ]
        self.assertEqual(result, expected_result)

    @patch("bin.har_client.requests.get")
    def test_get_active_checks_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tests": [
                {
                    "id": "1",
                    "name": "Test 1",
                    "lastRunAt": "2024-01-01T00:00:00.000Z",
                    "locationIds": ["location_1"],
                }
            ]
        }
        mock_get.return_value = mock_response

        epoch = datetime.utcfromtimestamp(0)
        result = self.ingester.get_active_checks()
        expected_result = [
            {
                "test_id": 1,
                "test_name": "Test 1",
                "last_test_run": round(
                    (
                        datetime.strptime(
                            "2024-01-01T00:00:00.000Z", "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                        - epoch
                    ).total_seconds()
                    * 1000
                ),
                "location_list": ["location_1"],
            }
        ]
        self.assertEqual(result, expected_result)

    @patch("bin.har_client.requests.get")
    def test_get_single_test_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "test": {
                "active": True,
                "locationIds": ["fake_location"],
                "name": "Fake Test",
            }
        }
        mock_get.return_value = mock_response

        result = self.ingester.get_single_test()
        self.assertEqual(result, '"Fake Test"')
        self.logger.warning.assert_not_called()

    @patch("bin.har_client.requests.get")
    def test_get_single_test_inactive(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "test": {
                "active": False,
                "locationIds": ["fake_location"],
                "name": "Fake Test",
            }
        }
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            self.ingester.get_single_test()
        self.logger.warning.assert_called_with(
            "Check not active or location not matched - please check Synthetics configuration in Splunk Observability Cloud"
        )


if __name__ == "__main__":
    unittest.main()
