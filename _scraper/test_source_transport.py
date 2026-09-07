import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import requests
from source_transport import interrupted_get


class TransportTest(unittest.TestCase):
    @patch('source_transport.time.sleep')
    def test_broken_response_retries_exact_read(self, sleep):
        result=SimpleNamespace(status_code=200)
        get=Mock(side_effect=[requests.exceptions.ChunkedEncodingError(),result])
        self.assertIs(interrupted_get(get,'https://example.test',params={'p':255}),result)
        self.assertEqual(get.call_args_list[0],get.call_args_list[1])
        sleep.assert_called_once_with(3)

    @patch('source_transport.time.sleep')
    def test_continued_network_failure_is_bounded(self, sleep):
        get=Mock(side_effect=requests.exceptions.Timeout())
        with self.assertRaises(requests.exceptions.Timeout):interrupted_get(get,'https://example.test')
        self.assertEqual(get.call_count,4)
        self.assertEqual([x.args[0] for x in sleep.call_args_list],[3,10,30])

    def test_protection_response_is_never_retried(self):
        for status in (302,403,429):
            response=SimpleNamespace(status_code=status)
            get=Mock(return_value=response)
            self.assertIs(interrupted_get(get,'https://example.test'),response)
            self.assertEqual(get.call_count,1)


if __name__=='__main__':unittest.main()
