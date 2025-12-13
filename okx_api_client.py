"""
文件名称: okx_api_client.py
文件用途: OKX Web3 API客户端模块，负责与OKX区块链数据API交互

主要功能:
    1. get_transactions_by_address(): 根据地址获取交易历史摘要列表
       - 支持多链查询（通过chains参数指定）
       - 返回交易的基本信息（哈希、时间、链ID等）
    
    2. get_transaction_detail_by_hash(): 根据交易哈希获取交易详情
       - 包含完整的交易信息（内部交易、代币转账、Gas费用等）
       - 需要提供链ID和交易哈希

API认证机制:
    OKX API使用HMAC-SHA256签名认证，需要以下信息：
    - API_KEY: API密钥
    - SECRET_KEY: 密钥（用于签名）
    - PASSPHRASE: 密码短语
    - TIMESTAMP: UTC时间戳（ISO格式，精确到毫秒）

签名流程:
    1. 构造签名字符串：timestamp + method + request_path + query_string
    2. 使用SECRET_KEY对签名字符串进行HMAC-SHA256加密
    3. 将加密结果进行Base64编码
    4. 将签名放入请求头的OK-ACCESS-SIGN字段

请求头说明:
    - OK-ACCESS-KEY: API密钥
    - OK-ACCESS-SIGN: HMAC签名
    - OK-ACCESS-TIMESTAMP: 时间戳
    - OK-ACCESS-PASSPHRASE: 密码短语
    - Content-Type: application/json

错误处理:
    - 检查HTTP状态码（200表示成功）
    - 检查API返回的业务状态码（code="0"表示成功）
    - 对于错误情况，打印错误信息并返回空列表或抛出异常

注意事项:
    - API调用频率限制：建议在请求之间添加延迟（如1.1秒）
    - 时间戳必须使用UTC时间，格式为ISO 8601
    - 签名计算必须严格按照文档要求，否则会认证失败

依赖库:
    - requests: HTTP请求库
    - hmac: HMAC签名算法
    - base64: Base64编码
    - datetime: 时间处理
    - urllib.parse: URL编码

作者: AI链上分析器开发团队
创建日期: 2025-11-01
"""

import requests
import hmac
import base64
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

# ========== API配置信息 ==========
# 注意：这些是敏感信息，实际使用时应该从环境变量或配置文件中读取
API_KEY = "8dc54cb0-2f9b-4f80-8c28-3e9d9df90c08"
SECRET_KEY = "81D30EE41CB8AEA28593F0AD39E921B1"
# 如果您的API Key有Passphrase，请在这里填写。
PASSPHRASE = "aBc8706802!@#" 
BASE_URL = "https://web3.okx.com"

# ========== 调试信息 ==========
# Streamlit 部署环境下，OKX 可能因 IP 白名单 / 限流 / 网络策略等原因请求失败。
# get_transactions_by_address 出错时会返回空列表，为了便于定位问题，这里保留最近一次请求的元信息。
LAST_TX_BY_ADDRESS_META = {}

def get_transactions_by_address(address: str, chains: str, limit: int = 20):
    """
    通过地址获取交易历史记录。
    
    这是获取交易数据的入口函数，返回交易摘要列表。
    摘要包含基本信息，但不包含详细的内部交易和代币转账信息。
    如果需要详细信息，需要调用 get_transaction_detail_by_hash()。
    
    参数:
        address: 链上账户地址（例如：0x1234...）
        chains: 查询的链，多条链以","分隔（例如："1" 或 "1,56,137"）
                链ID说明：1=以太坊主网, 56=BSC, 137=Polygon, 42161=Arbitrum等
        limit: 返回条数，默认为20（最大支持的数量取决于API限制）
    
    返回:
        包含交易数据的列表，每个元素是一个字典，包含：
        - transactions: 交易列表
        - 其他元数据（如果有）
        
        如果API请求失败或返回错误，返回空列表 []
    
    异常处理:
        - HTTP错误：打印错误信息，返回空列表
        - API业务错误：打印错误信息，返回空列表
        - 网络错误：会抛出requests异常（由调用方处理）
    
    示例:
        >>> data = get_transactions_by_address("0x1234...", "1", 20)
        >>> print(len(data))  # 打印返回的数据块数量
    """
    # API端点路径
    request_path = "/api/v6/dex/post-transaction/transactions-by-address"
    
    # 生成UTC时间戳（ISO格式，精确到毫秒）
    # 格式示例：2025-11-01T12:00:00.000Z
    timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    
    # ========== 准备查询参数 ==========
    # 将参数编码为URL查询字符串格式
    params = {
        'address': address,
        'chains': chains,
        'limit': str(limit)
    }
    query_string = urlencode(params)
    
    # ========== 准备签名 ==========
    # OKX API要求对每个请求进行HMAC-SHA256签名
    # 签名字符串格式：timestamp + HTTP方法 + 请求路径 + 查询字符串
    message = timestamp + 'GET' + request_path + '?' + query_string
    
    # 使用SECRET_KEY对签名字符串进行HMAC-SHA256加密
    mac = hmac.new(bytes(SECRET_KEY, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    # 将加密结果进行Base64编码，得到最终的签名
    signature = base64.b64encode(d)

    # ========== 准备请求头 ==========
    # 包含API认证信息和内容类型
    headers = {
        'Content-Type': 'application/json',
        'OK-ACCESS-KEY': API_KEY,           # API密钥
        'OK-ACCESS-SIGN': signature,        # HMAC签名
        'OK-ACCESS-TIMESTAMP': timestamp,     # 时间戳
        'OK-ACCESS-PASSPHRASE': PASSPHRASE,  # 密码短语
    }

    # 构造完整的请求URL
    url = BASE_URL + request_path
    
    # ========== 发送请求 ==========
    # 使用GET方法发送请求，查询参数通过params传递
    global LAST_TX_BY_ADDRESS_META
    LAST_TX_BY_ADDRESS_META = {
        "address": address,
        "chains": chains,
        "limit": limit,
        "request_path": request_path,
        "url": url,
        "timestamp": timestamp
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.RequestException as e:
        LAST_TX_BY_ADDRESS_META.update({
            "error_type": type(e).__name__,
            "error": str(e),
        })
        print(f"Network Error in get_transactions_by_address: {e}")
        return []

    LAST_TX_BY_ADDRESS_META.update({
        "http_status": response.status_code,
        "response_text_preview": (response.text or "")[:800]
    })

    # ========== 检查响应 ==========
    if response.status_code == 200:
        # HTTP请求成功，检查业务状态码
        try:
            response_json = response.json()
        except ValueError as e:
            LAST_TX_BY_ADDRESS_META.update({
                "error_type": "JSONDecodeError",
                "error": str(e),
            })
            print(f"JSON Decode Error in get_transactions_by_address: {e}")
            return []

        LAST_TX_BY_ADDRESS_META.update({
            "api_code": response_json.get("code"),
            "api_msg": response_json.get("msg"),
        })

        if response_json.get("code") == "0":
            # API业务成功，返回数据
            data = response_json.get("data", []) or []
            LAST_TX_BY_ADDRESS_META["data_len"] = len(data) if isinstance(data, list) else None
            return data
        else:
            # API返回业务错误（例如：参数错误、权限不足等）
            print(f"API Error in get_transactions_by_address: {response_json.get('msg')}")
            return []
    else:
        # HTTP请求失败（例如：404、500等）
        print(f"HTTP Error in get_transactions_by_address: {response.status_code}")
        return []

def get_transaction_detail_by_hash(chain_index: str, tx_hash: str):
    """
    根据交易哈希查询某个交易的详情。
    
    这个函数返回交易的完整信息，包括：
    - 基本信息：发送方、接收方、金额、Gas费用等
    - 内部交易：合约调用产生的内部ETH转账
    - 代币转账：ERC20代币的转账记录
    - 其他元数据：区块高度、nonce、方法ID等
    
    参数:
        chain_index: 链的唯一标识（例如："1"表示以太坊主网）
        tx_hash: 交易哈希（例如：0x1234...）
    
    返回:
        包含交易详情的列表或字典
        - 某些链可能返回多条记录（例如：L2链可能包含L1和L2的记录）
        - 通常返回一个包含单个交易详情的列表
    
    异常处理:
        - HTTP错误：调用response.raise_for_status()抛出异常
        - API业务错误：抛出Exception，包含错误信息
    
    注意:
        与get_transactions_by_address不同，这个函数在错误时会抛出异常，
        而不是返回空值。调用方需要处理异常。
    
    示例:
        >>> detail = get_transaction_detail_by_hash("1", "0x1234...")
        >>> print(detail[0]['txhash'])  # 打印交易哈希
    """
    # API端点路径
    request_path = "/api/v6/dex/post-transaction/transaction-detail-by-txhash"
    
    # 生成UTC时间戳（与get_transactions_by_address相同）
    timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    # ========== 准备查询参数 ==========
    params = {
        'chainIndex': chain_index,
        'txHash': tx_hash,
    }
    query_string = urlencode(params)

    # ========== 准备签名 ==========
    # 签名流程与get_transactions_by_address完全相同
    message = timestamp + 'GET' + request_path + '?' + query_string
    mac = hmac.new(bytes(SECRET_KEY, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    signature = base64.b64encode(d)

    # ========== 准备请求头 ==========
    headers = {
        'Content-Type': 'application/json',
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': PASSPHRASE,
    }
    
    # 构造完整的请求URL
    url = BASE_URL + request_path
    
    # ========== 发送请求 ==========
    response = requests.get(url, headers=headers, params=params)

    # ========== 检查响应 ==========
    if response.status_code == 200:
        response_json = response.json()
        if response_json.get("code") == "0":
            # API业务成功，返回数据
            return response_json.get("data")
        else:
            # API返回业务错误，抛出异常
            # 这样调用方可以知道具体是什么错误，并决定如何处理
            raise Exception(f"API returned an error for tx_hash {tx_hash}: {response_json.get('msg')}")
    else:
        # HTTP请求失败，抛出异常
        # raise_for_status()会根据状态码抛出相应的异常
        response.raise_for_status()
