"""
文件名称: data_processor.py
文件用途: 数据处理和清洗模块，负责处理和格式化从API获取的原始交易数据

主要功能:
    1. extract_tx_info_from_summary(): 从交易摘要中提取关键信息
       - 提取交易哈希、链ID、时间戳
       - 格式化时间戳为可读格式
    
    2. filter_important_internal_transactions(): 过滤重要的内部交易
       - 过滤掉不重要的合约间调用
       - 只保留涉及用户或外部地址的交易
    
    3. process_and_clean_details(): 处理和清洗交易详情
       - 格式化时间戳、Gas费用等字段
       - 组织数据结构，匹配链上浏览器格式
       - 过滤代币转账，只保留相关记录

数据处理说明:
    - 使用Decimal进行精确的数值计算（避免浮点数精度问题）
    - 统一时间格式：将毫秒时间戳转换为可读的日期时间格式
    - Gas费用计算：将Wei转换为ETH，Gwei转换为可读格式
    - 数据过滤：根据交易类型（用户发起/被动接收）过滤代币转账

精度处理:
    - 使用Decimal类型处理大数值（Wei、Gwei等）
    - Decimal精度设置为28位，足够处理区块链数值
    - 提供安全的数值转换函数，避免类型错误

数据格式:
    处理后的数据格式完全匹配链上浏览器的显示格式，包括：
    - 基本信息：交易哈希、状态、区块高度、时间
    - 地址信息：发送方、接收方、是否合约
    - Gas信息：Gas限制、Gas使用量、Gas价格、手续费
    - 交易内容：金额、代币符号、内部交易、代币转账

依赖库:
    - json: JSON数据处理
    - datetime: 时间处理
    - decimal: 精确数值计算

作者: AI链上分析器开发团队
创建日期: 2025-11-01
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, getcontext

# ========== Decimal精度配置 ==========
# 设置Decimal的精度为28位，足够处理区块链中的大数值（Wei、Gwei等）
getcontext().prec = 28

# ========== 以太坊单位常量 ==========
# Wei是ETH的最小单位，1 ETH = 10^18 Wei
WEI_PER_ETH = Decimal("1000000000000000000")
# Gwei是常用的Gas价格单位，1 Gwei = 10^9 Wei
WEI_PER_GWEI = Decimal("1000000000")


def _safe_decimal(value) -> Decimal:
    """
    安全地把各种类型的数字转换成Decimal类型
    
    这个函数很安全，即使输入有问题也不会让程序崩溃
    如果转换失败，就返回0
    
    需要什么：
        value: 可以是字符串、数字、None等，什么都能接受
    
    给你什么：
        一个Decimal对象，如果转换失败就给你0
    
    什么时候用：
        - API返回的数字可能是字符串格式，需要转换
        - 有些字段可能是空的，需要处理
        - 不想因为数字格式不对就让程序崩溃
    """
    try:
        # 如果是空的或者None，直接返回0
        if value in (None, ""):
            return Decimal(0)
        # 先转成字符串，再转成Decimal
        # 这样不管输入是整数、小数还是字符串，都能处理
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        # 如果转换失败了（比如输入了乱七八糟的东西），就返回0
        return Decimal(0)


def _format_decimal(value: Decimal, unit: str = "") -> str:
    """
    把Decimal数字格式化成好看的文字
    
    比如：123.456000 会变成 123.456，去掉多余的0
    还可以在后面加单位，比如 "ETH"、"Gwei"
    
    需要什么：
        value: 要格式化的数字
        unit: 可选的单位（比如 "ETH"），不传就不加单位
    
    给你什么：
        格式化好的字符串，比如 "123.456 ETH" 或者 "100"
    
    怎么做的：
        - 如果是0，就返回 "0" 或者 "0 ETH"
        - 否则先转成18位小数，然后去掉末尾的0和小数点
        - 如果给了单位，就在后面加上
    """
    if value == 0:
        return "0" if not unit else f"0 {unit}"
    # 先转成18位小数，然后去掉末尾的0和小数点
    # 这样既精确又好看，不会显示一堆没用的0
    value_str = f"{value:.18f}".rstrip('0').rstrip('.')
    return value_str if not unit else f"{value_str} {unit}"


def _compute_gas_cost(gas_amount, gas_price_wei: Decimal) -> str:
    """
    计算这笔交易花了多少Gas费（用ETH表示）
    
    计算公式很简单：Gas费用 = Gas使用量 × Gas价格
    
    需要什么：
        gas_amount: 用了多少Gas（可以是字符串或数字）
        gas_price_wei: Gas价格是多少（单位是Wei）
    
    给你什么：
        格式化好的Gas费用，单位是ETH（比如 "0.001 ETH"）
    
    怎么算的：
        - 先把Gas使用量转成Decimal
        - 如果Gas使用量或价格是0，就直接返回"0"
        - 否则用公式算：Gas使用量 × Gas价格 ÷ Wei_PER_ETH
        - 最后格式化成好看的字符串
    """
    # 先把Gas使用量转成Decimal
    gas_units = _safe_decimal(gas_amount)
    # 如果Gas使用量或价格是0，就不用算了，直接返回"0"
    if gas_units == 0 or gas_price_wei == 0:
        return "0"
    # 计算Gas费用：Gas使用量 × Gas价格（Wei） ÷ Wei_PER_ETH
    # 这样就能得到ETH单位的费用了
    cost_eth = (gas_units * gas_price_wei) / WEI_PER_ETH
    # 格式化成好看的字符串返回
    return _format_decimal(cost_eth)


def extract_tx_info_from_summary(raw_data: list) -> list:
    """
    从API返回的交易摘要里，把每笔交易的关键信息提取出来
    
    提取什么信息：
    - chainIndex: 这是哪条链（比如以太坊、BSC）
    - txHash: 交易的唯一标识（就像交易的身份证号）
    - timestamp: 交易发生的时间（格式化成好看的样子）
    
    需要什么：
        raw_data: API返回的原始数据，是一个列表
    
    给你什么：
        一个列表，里面每个元素是一个字典，包含上面说的三个信息
    
    怎么处理的：
        - API返回的时间是毫秒（13位数），先除以1000变成秒
        - 然后格式化成 "2025-11-01 12:00:00" 这样的格式
        - 把每笔交易的信息打包成字典，放到列表里
    """
    tx_info_list = []

    # 如果原始数据为空，直接返回空列表
    if not raw_data:
        return tx_info_list
    
    # 遍历原始数据列表（API可能返回多个数据块）
    for data_chunk in raw_data:
        # 从数据块中提取交易列表
        transaction_list = data_chunk.get("transactions", [])
        
        # 遍历每笔交易，提取关键信息
        for tx in transaction_list:
            # 初始化时间戳为空字符串
            formatted_time = ""
            # 获取原始时间戳（毫秒级，字符串格式）
            timestamp_ms = tx.get("txTime")
            
            # 如果时间戳存在且是数字字符串，进行格式化
            if timestamp_ms and timestamp_ms.isdigit():
                # 将毫秒时间戳转换为秒时间戳
                timestamp_s = int(timestamp_ms) / 1000
                # 格式化为可读的日期时间格式：YYYY-MM-DD HH:MM:SS
                formatted_time = datetime.fromtimestamp(timestamp_s).strftime('%Y-%m-%d %H:%M:%S')

            # 构建交易信息字典
            tx_info_list.append({
                "chainIndex": tx.get("chainIndex"),  # 链ID
                "txHash": tx.get("txHash"),          # 交易哈希
                "timestamp": formatted_time           # 格式化的时间戳
            })
    
    return tx_info_list

def filter_important_internal_transactions(internal_txs: list, user_address: str) -> list:
    """
    把不重要的内部交易过滤掉，只保留重要的
    
    什么是内部交易：
        就是合约调用时产生的ETH转账，不是用户直接发起的交易
    
    哪些算重要的（满足一个就保留）：
        1. 金额不是0的（有真金白银在流动）
        2. 跟用户地址有关的（发送方或接收方是用户）
        3. 至少有一边不是合约的（涉及真实用户）
    
    哪些会被过滤掉：
        - 金额是0的（没意义）
        - 纯合约之间的调用（用户不关心，通常是合约内部逻辑）
    
    需要什么：
        internal_txs: 内部交易列表
        user_address: 用户要查的地址
    
    给你什么：
        过滤后的重要内部交易列表
    
    为什么这样过滤：
        就像链上浏览器一样，只显示用户关心的交易
        用户不关心合约内部的复杂逻辑，只关心跟自己有关的或者有实际资金流动的
    """
    user_address_lower = user_address.lower()
    important_txs = []
    
    # 遍历所有内部交易
    for tx in internal_txs:
        # 提取地址和合约标识（统一转换为小写，便于比较）
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()
        is_from_contract = tx.get("isFromContract", False)
        is_to_contract = tx.get("isToContract", False)
        
        # ========== 获取金额 ==========
        # 安全地提取金额，如果转换失败则默认为0
        try:
            amount = float(tx.get("amount", "0"))
        except (ValueError, TypeError):
            amount = 0
        
        # ========== 规则1: 金额为0的直接跳过 ==========
        # 没有实际资金流动的交易，通常不重要
        if amount == 0:
            continue
        
        # ========== 规则2: 涉及用户地址的交易，保留 ==========
        # 如果交易的发送方或接收方是用户地址，说明与用户相关，必须保留
        if user_address_lower in [from_addr, to_addr]:
            important_txs.append(tx)
            continue
        
        # ========== 规则3: 至少有一端不是合约的交易，保留 ==========
        # 如果至少有一端是外部地址（不是合约），说明涉及真实用户，保留
        # 纯合约到合约的调用（两端都是合约）通常不重要，可以过滤
        if not (is_from_contract and is_to_contract):
            important_txs.append(tx)
            continue
        
        # ========== 其他情况（纯合约到合约的调用）跳过 ==========
        # 如果两端都是合约，且不涉及用户，通常是合约的内部逻辑，可以过滤
    
    return important_txs

def process_and_clean_details(raw_details_list: list, user_address: str) -> list:
    """
    把API返回的原始交易数据整理成好看的格式
    
    这个函数做的事情：
    1. 提取交易的基本信息（哈希、时间、状态等）
    2. 计算Gas费用，转成ETH单位
    3. 过滤掉不重要的内部交易
    4. 根据交易类型决定保留哪些代币转账
    5. 整理成跟链上浏览器一样的格式
    
    需要什么：
        raw_details_list: API返回的原始交易数据列表
        user_address: 用户要查的地址（用来判断是不是用户发起的交易）
    
    给你什么：
        整理好的交易数据列表，格式跟链上浏览器一样
    
    怎么处理的：
        - 如果是用户发起的交易：保留所有代币转账（因为用户可能做了复杂操作）
        - 如果是被动接收的交易：只保留发给用户的转账（用户只关心收到的）
        - Gas费用从Wei转成ETH，方便看
        - 时间戳格式化成 "2025-11-01 12:00:00" 这样的格式
    """
    cleaned_details = []
    user_address_lower = user_address.lower()

    # 遍历所有交易详情
    for detail in raw_details_list:
        # 跳过空数据
        if not detail:
            continue
        
        # ========== 1. 基本信息提取 ==========
        # 判断交易是否由用户发起（用于后续的过滤逻辑）
        tx_initiator = detail.get("fromDetails", [{}])[0].get("address", "").lower()
        is_user_initiated = (tx_initiator == user_address_lower)
        
        # ========== 格式化时间戳 ==========
        # 将毫秒时间戳转换为可读的日期时间格式
        formatted_time = ""
        timestamp_ms = detail.get("txTime")
        if timestamp_ms and timestamp_ms.isdigit():
            timestamp_s = int(timestamp_ms) / 1000
            formatted_time = datetime.fromtimestamp(timestamp_s).strftime('%Y-%m-%d %H:%M:%S')
        
        # ========== 提取发送方和接收方信息 ==========
        # fromDetails和toDetails是列表格式，取第一个元素
        from_detail = detail.get("fromDetails", [{}])[0] if detail.get("fromDetails") else {}
        to_detail = detail.get("toDetails", [{}])[0] if detail.get("toDetails") else {}
        
        # ========== 提取Gas价格（Wei单位） ==========
        gas_price_wei = _safe_decimal(detail.get("gasPrice", "0"))

        # ========== 构建交易详情对象 ==========
        # 按照链上浏览器的格式组织数据
        tx_detail = {
            # ========== 基本信息 ==========
            "txhash": detail.get("txhash"),                    # 交易哈希
            "txStatus": detail.get("txStatus"),                # 交易状态：success/fail/pending
            "height": detail.get("height"),                     # 区块高度
            "txTime": formatted_time,                          # 格式化的时间戳
            "chainIndex": detail.get("chainIndex"),             # 链ID
            
            # ========== 发送方和接收方 ==========
            "from": {
                "address": from_detail.get("address", ""),      # 发送方地址
                "isContract": from_detail.get("isContract", False)  # 是否是合约
            },
            "to": {
                "address": to_detail.get("address", ""),        # 接收方地址
                "isContract": to_detail.get("isContract", False)  # 是否是合约
            },
            
            # ========== 交易金额和币种 ==========
            "amount": detail.get("amount", ""),                 # 交易金额
            "symbol": detail.get("symbol", ""),                 # 币种符号（例如：ETH）
            
            # ========== Gas信息 ==========
            # Gas限制和Gas使用量转换为ETH单位，便于理解
            "gasLimit": _compute_gas_cost(detail.get("gasLimit", ""), gas_price_wei),
            "gasUsed": _compute_gas_cost(detail.get("gasUsed", ""), gas_price_wei),
            # Gas价格转换为Gwei单位（更常用的单位）
            "gasPrice": _format_decimal(gas_price_wei / WEI_PER_GWEI if gas_price_wei else Decimal(0)),
            
            # ========== 手续费 ==========
            "txFee": detail.get("txFee", ""),                  # 交易手续费
            
            # ========== 其他信息 ==========
            "nonce": detail.get("nonce", ""),                   # 交易nonce
            "methodId": detail.get("methodId", ""),              # 方法ID（合约调用时）
            "l1OriginHash": detail.get("l1OriginHash", ""),     # L1原始哈希（L2链使用）
            
            # ========== 交易行为标识 ==========
            # 用于AI分析：判断交易是否由用户主动发起
            "isUserInitiated": is_user_initiated,
            
            # ========== 重要的内部交易 ==========
            # 过滤后的内部交易，只保留重要的（涉及用户或外部地址的交易）
            "internalTransactions": filter_important_internal_transactions(
                detail.get("internalTransactionDetails", []),
                user_address
            ),
            
            # ========== ERC20代币转账 ==========
            # 初始化为空列表，后续根据交易类型填充
            "tokenTransfers": []
        }
        
        # ========== 2. 处理ERC20代币转账 ==========
        # 根据交易类型决定保留哪些代币转账
        if is_user_initiated:
            # ========== 用户发起的交易 ==========
            # 保留所有Token转账，因为用户可能进行了复杂的操作
            # 例如：在DEX上交换代币，可能涉及多个代币转账
            tx_detail["tokenTransfers"] = detail.get("tokenTransferDetails", [])
        else:
            # ========== 被动接收的交易 ==========
            # 只保留发送给用户的代币转账
            # 用户只关心收到的代币，不关心其他地址之间的转账
            tx_detail["tokenTransfers"] = [
                t for t in detail.get("tokenTransferDetails", [])
                if t.get("to", "").lower() == user_address_lower
            ]
        
        # 将处理后的交易详情添加到结果列表
        cleaned_details.append(tx_detail)

    return cleaned_details
