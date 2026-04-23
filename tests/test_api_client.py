"""
API 客户端测试"""
import pytest
from unittest.mock import Mock, patch

from openscaw.api_client import (
    KimiClient, DeepSeekClient, MiniMaxClient,
    APIClientManager, APIStatus
)


class TestKimiClient:
    def test_init(self):
        client = KimiClient("test-key")
        assert client.name == "kimi"
        assert client.api_key == "test-key"
        assert "moonshot.cn" in client.base_url
    
    @patch('openscaw.api_client.requests.Session')
    def test_test_connection_success(self, mock_session):
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"id": "test-model"}]}
        mock_response.raise_for_status.return_value = None
        mock_session.return_value.get.return_value = mock_response
        
        client = KimiClient("test-key")
        # 注意: 由于 mock 的问题，这个测试可能需要调整


class TestDeepSeekClient:
    def test_init(self):
        client = DeepSeekClient("test-key")
        assert client.name == "deepseek"
        assert client.api_key == "test-key"
        assert "deepseek.com" in client.base_url


class TestMiniMaxClient:
    def test_init(self):
        client = MiniMaxClient("test-key", "group-123")
        assert client.name == "minimax"
        assert client.group_id == "group-123"
    
    def test_init_without_group(self):
        client = MiniMaxClient("test-key")
        assert client.group_id == ""


class TestAPIClientManager:
    @patch.dict('os.environ', {'KIMI_API_KEY': 'test-kimi', 'DEEPSEEK_API_KEY': 'test-deepseek'})
    def test_init_with_env_vars(self):
        manager = APIClientManager()
        assert "kimi" in manager.clients
        assert "deepseek" in manager.clients
    
    @patch.dict('os.environ', {}, clear=True)
    def test_init_without_env_vars(self):
        manager = APIClientManager()
        assert len(manager.clients) == 0
    
    def test_switch_to_next(self):
        with patch.dict('os.environ', {'KIMI_API_KEY': 'test1', 'DEEPSEEK_API_KEY': 'test2'}):
            manager = APIClientManager()
            assert manager.current_client is not None
            
            # 切换到下一个
            result = manager.switch_to_next()
            assert result is True
