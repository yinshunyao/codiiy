import dashscope
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QwenClient:
    """
    Qwen API 客户端
    用于调用阿里 dashscope SDK 的各种模型
    """
    
    def __init__(self, api_key):
        """
        初始化客户端
        
        Args:
            api_key (str): DashScope API 密钥
        """
        self.api_key = api_key
        dashscope.api_key = api_key
    
    def call_model(self, model, messages, **kwargs):
        """
        调用指定模型
        
        Args:
            model (str): 模型名称
            messages (list): 消息列表
            **kwargs: 其他参数
            
        Returns:
            dict: 包含调用结果的字典
        """
        try:
            logger.info("Calling model %s with %s messages", model, len(messages or []))
            if self._has_multimodal_content(messages):
                multimodal_api = getattr(dashscope, "MultiModalConversation", None)
                if multimodal_api and hasattr(multimodal_api, "call"):
                    response = multimodal_api.call(
                        model=model,
                        messages=messages,
                        **kwargs
                    )
                else:
                    logger.warning("检测到多模态消息，但 SDK 未提供 MultiModalConversation，回退到 Generation.call")
                    response = dashscope.Generation.call(
                        model=model,
                        messages=messages,
                        **kwargs
                    )
            else:
                response = dashscope.Generation.call(
                    model=model,
                    messages=messages,
                    **kwargs
                )
            
            if response.status_code == 200:
                logger.info(f"Model call successful: {response.output}")
                return {
                    "success": True,
                    "data": response.output
                }
            else:
                logger.error(f"Model call failed: {response}")
                return {
                    "success": False,
                    "error": f"Model call failed with status code: {response.status_code}"
                }
        except Exception as e:
            logger.error(f"Error calling model: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def _has_multimodal_content(self, messages):
        for message in messages or []:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if any(key in block for key in ("file", "image", "video", "audio")):
                    return True
        return False
    
    def chat_completion(self, model, messages, temperature=0.7, max_tokens=1024):
        """
        聊天完成
        
        Args:
            model (str): 模型名称
            messages (list): 消息列表
            temperature (float): 温度参数
            max_tokens (int): 最大 token 数
            
        Returns:
            dict: 包含聊天结果的字典
        """
        return self.call_model(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def text_generation(self, model, prompt, temperature=0.7, max_tokens=1024):
        """
        文本生成
        
        Args:
            model (str): 模型名称
            prompt (str): 提示文本
            temperature (float): 温度参数
            max_tokens (int): 最大 token 数
            
        Returns:
            dict: 包含生成结果的字典
        """
        messages = [{
            "role": "user",
            "content": prompt
        }]
        return self.call_model(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )