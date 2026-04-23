"""
国内大模型 API 客户端
支持 Kimi、DeepSeek、MiniMax
"""
import os
import time
import requests
from typing import Optional, Dict, List, Generator
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class APIStatus(Enum):
    HEALTHY = "healthy"
    INVALID_KEY = "invalid_key"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    ERROR = "error"

@dataclass
class APIResponse:
    status: APIStatus
    message: str
    response_time_ms: float
    model: Optional[str] = None
    tokens_used: Optional[int] = None

class BaseAPIClient:
    """基础 API 客户端"""
    
    def __init__(self, name: str, base_url: str, api_key: str):
        self.name = name
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
    
    def test_connection(self, timeout: int = 10) -> APIResponse:
        """测试 API 连接"""
        start = time.time()
        try:
            response = self._do_test_request(timeout)
            elapsed = (time.time() - start) * 1000
            return APIResponse(
                status=APIStatus.HEALTHY,
                message="API 正常",
                response_time_ms=elapsed,
                model=response.get('model')
            )
        except requests.exceptions.HTTPError as e:
            elapsed = (time.time() - start) * 1000
            if e.response.status_code == 401:
                return APIResponse(
                    status=APIStatus.INVALID_KEY,
                    message="API Key 无效或已过期",
                    response_time_ms=elapsed
                )
            elif e.response.status_code == 429:
                return APIResponse(
                    status=APIStatus.RATE_LIMITED,
                    message="触发频率限制",
                    response_time_ms=elapsed
                )
            return APIResponse(
                status=APIStatus.ERROR,
                message=f"HTTP错误: {e.response.status_code}",
                response_time_ms=elapsed
            )
        except requests.exceptions.Timeout:
            elapsed = (time.time() - start) * 1000
            return APIResponse(
                status=APIStatus.TIMEOUT,
                message="请求超时",
                response_time_ms=elapsed
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return APIResponse(
                status=APIStatus.ERROR,
                message=f"连接失败: {str(e)}",
                response_time_ms=elapsed
            )
    
    def _do_test_request(self, timeout: int) -> dict:
        """子类必须实现的测试请求"""
        raise NotImplementedError
    
    def chat_completion(self, messages: List[Dict], model: str = None, 
                       timeout: int = 30, stream: bool = False) -> Generator:
        """发送聊天完成请求"""
        raise NotImplementedError
    
    def switch_key(self, new_key: str):
        """切换 API Key"""
        self.api_key = new_key
        self.session.headers["Authorization"] = f"Bearer {new_key}"


class KimiClient(BaseAPIClient):
    """Kimi API 客户端 (Moonshot AI)"""
    
    DEFAULT_MODEL = "moonshot-v1-8k"
    
    def __init__(self, api_key: str):
        super().__init__(
            name="kimi",
            base_url="https://api.moonshot.cn/v1",
            api_key=api_key
        )
    
    def _do_test_request(self, timeout: int) -> dict:
        # 获取模型列表作为测试
        resp = self.session.get(
            f"{self.base_url}/models",
            timeout=timeout
        )
        resp.raise_for_status()
        return {"model": self.DEFAULT_MODEL}
    
    def chat_completion(self, messages, model=None, timeout=30, stream=False):
        model = model or self.DEFAULT_MODEL
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        if stream:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=timeout,
                stream=True
            )
            for line in response.iter_lines():
                if line:
                    yield line.decode('utf-8')
        else:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()


class DeepSeekClient(BaseAPIClient):
    """DeepSeek API 客户端"""
    
    DEFAULT_MODEL = "deepseek-chat"
    
    def __init__(self, api_key: str):
        super().__init__(
            name="deepseek",
            base_url="https://api.deepseek.com/v1",
            api_key=api_key
        )
    
    def _do_test_request(self, timeout: int) -> dict:
        # 用一个简单请求测试
        resp = self.session.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5
            },
            timeout=timeout
        )
        resp.raise_for_status()
        result = resp.json()
        return {
            "model": result.get('model', self.DEFAULT_MODEL),
            "tokens": result.get('usage', {}).get('total_tokens', 0)
        }
    
    def chat_completion(self, messages, model=None, timeout=30, stream=False):
        model = model or self.DEFAULT_MODEL
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=timeout,
            stream=stream
        )
        response.raise_for_status()
        
        if stream:
            for line in response.iter_lines():
                if line:
                    yield line.decode('utf-8')
        else:
            return response.json()


class MiniMaxClient(BaseAPIClient):
    """MiniMax API 客户端"""
    
    DEFAULT_MODEL = "abab6.5-chat"
    
    def __init__(self, api_key: str, group_id: str = None):
        super().__init__(
            name="minimax",
            base_url="https://api.minimax.chat/v1",
            api_key=api_key
        )
        self.group_id = group_id or os.getenv("MINIMAX_GROUP_ID", "")
    
    def _do_test_request(self, timeout: int) -> dict:
        # MiniMax 使用特定的接口格式
        url = f"{self.base_url}/text/chatcompletion_v2"
        resp = self.session.post(
            url,
            json={
                "model": self.DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "hi"}]
            },
            timeout=timeout
        )
        resp.raise_for_status()
        return {"model": self.DEFAULT_MODEL}
    
    def chat_completion(self, messages, model=None, timeout=30, stream=False):
        model = model or self.DEFAULT_MODEL
        
        url = f"{self.base_url}/text/chatcompletion_v2"
        payload = {
            "model": model,
            "messages": messages
        }
        
        if self.group_id:
            payload["group_id"] = self.group_id
        
        response = self.session.post(url, json=payload, timeout=timeout, stream=stream)
        response.raise_for_status()
        
        if stream:
            for line in response.iter_lines():
                if line:
                    yield line.decode('utf-8')
        else:
            return response.json()


class APIClientManager:
    """API 客户端管理器 - 管理多个 API Key"""
    
    def __init__(self):
        self.clients: Dict[str, BaseAPIClient] = {}
        self.current_client: Optional[BaseAPIClient] = None
        self._init_clients()
    
    def _init_clients(self):
        # Kimi
        kimi_key = os.getenv("KIMI_API_KEY")
        if kimi_key:
            self.clients["kimi"] = KimiClient(kimi_key)
        
        # DeepSeek
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            self.clients["deepseek"] = DeepSeekClient(deepseek_key)
        
        # MiniMax
        minimax_key = os.getenv("MINIMAX_API_KEY")
        if minimax_key:
            self.clients["minimax"] = MiniMaxClient(minimax_key)
        
        # 设置默认客户端
        if self.clients:
            self.current_client = list(self.clients.values())[0]
            logger.info(f"默认 API: {self.current_client.name}")
    
    def get_client(self, name: str = None) -> Optional[BaseAPIClient]:
        if name:
            return self.clients.get(name)
        return self.current_client
    
    def switch_to_next(self) -> bool:
        """切换到下一个可用的 API"""
        if not self.clients:
            return False
        
        names = list(self.clients.keys())
        if not self.current_client:
            self.current_client = self.clients[names[0]]
            return True
        
        current_idx = names.index(self.current_client.name)
        next_idx = (current_idx + 1) % len(names)
        self.current_client = self.clients[names[next_idx]]
        
        logger.info(f"切换到 API: {self.current_client.name}")
        return True
    
    def test_all(self) -> Dict[str, APIResponse]:
        """测试所有 API"""
        results = {}
        for name, client in self.clients.items():
            logger.info(f"测试 {name}...")
            results[name] = client.test_connection()
        return results
    
    def get_healthy_clients(self) -> List[BaseAPIClient]:
        """获取所有健康的客户端"""
        healthy = []
        for client in self.clients.values():
            result = client.test_connection(timeout=5)
            if result.status == APIStatus.HEALTHY:
                healthy.append(client)
        return healthy