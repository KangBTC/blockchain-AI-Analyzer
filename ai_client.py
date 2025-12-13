"""
文件名称: ai_client.py
文件用途: 用来调用AI分析单笔交易的

这个文件做的事情很简单：
- 把交易数据发给AI，让AI分析这笔交易做了什么
- AI会返回一段分析文字，说明这笔交易的本质

用的AI服务：
    - OpenRouter（一个AI模型聚合平台，可以访问很多AI模型）
    - GPT-5 Pro模型（用来分析交易）

AI会分析什么：
    1. 这笔交易的基本信息（哈希、时间）
    2. 完整的交易数据（包括内部交易、代币转账等）
    3. 判断是不是用户主动发起的
    4. 识别涉及了哪些协议（Uniswap、Aave等）
    5. 计算资产变动（用户花了多少，得到了多少）
    6. 识别协议的真实用途（DeFi、交易所、跨链桥等）

AI返回什么：
    一段Markdown格式的分析文字，包含：
    - 交易哈希和时间
    - 操作类型（比如"卖出代币"、"授权"等）
    - 详细的行为分析
    - Gas费用信息

如果AI调用失败了，会返回错误信息，但不会让程序崩溃

依赖库:
    - openai: 用来调用AI的库
    - json: 用来处理JSON数据

作者: AI链上分析器开发团队
创建日期: 2025-11-01
"""

import os
import json
import streamlit as st
from openai import OpenAI

# ========== AI客户端配置 ==========
# 从 Streamlit Secrets 读取配置
try:
    API_KEY = st.secrets["OPENROUTER_API_KEY"]
except (FileNotFoundError, KeyError):
    # 如果没有找到 secrets，可以设置一个空值或者抛出更友好的错误
    # 但为了兼容性，这里暂时留空，会在 app.py 里通过 try-except 处理
    API_KEY = ""

MODEL = "google/gemini-2.5-flash"  # 使用的AI模型

# 创建OpenAI客户端（兼容OpenRouter API）
# 注意：如果 API_KEY 为空，初始化可能会报错，建议在使用前检查
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",  # OpenRouter的API地址
    api_key=API_KEY,
    default_headers={
        "HTTP-Referer": "http://localhost",      # HTTP Referer（可选）
        "X-Title": "AI On-Chain Analyzer"       # 应用标题（可选）
    },
)

# ========== Prompt模板 ==========
# 这是发送给AI的提示词模板，定义了分析任务和要求
PROMPT_TEMPLATE = """
你是一个专业的区块链交易分析师。
你的任务是分析以下单笔交易的JSON数据，解读并总结出该链上行为的本质与资金流向。

交易哈希: {txhash}
交易时间: {txtime}

交易数据:
{transaction_data}

请严格遵循以下分析规则：
1.  审查 `isUserInitiated` 字段，明确是否为用户主动操作；若为主动操作，需要衡量用户输入与输出资产的净差额。
2.  深度分析 `tokenTransfers`、`internalTransactions` 与主交易信息，识别关键合约、协议（如 Uniswap、Curve、跨链桥等）及其扮演的角色。
3.  量化资产变动，明确用户投入与获得的代币数量及符号，必要时注明是估算值（使用"约"）。
4.  **重要：在分析用户行为时，必须利用你的知识库来正确识别各种协议和服务的真实用途。**
  - 区分不同类型的服务：DeFi协议（Uniswap、Aave等）、CEX（Coinbase、Binance等）、跨链桥（Stargate等）、服务提供商（圈外知名公司或服务）、NFT市场、游戏平台等。
  - **不要默认所有操作都是纯币圈操作**。如果用户向服务提供商支付代币，应该识别为"购买服务/支付费用"，而不是"跨链"或"DeFi操作"。

输出要求：
- 回答必须是 JSON 对象，且仅包含名为 "analysis" 的字段。
- "analysis" 字段内容必须是中文 Markdown 文本，并严格按照下面的结构生成（请替换花括号内容，保留星号与缩进）：
* **交易哈希({txhash}) - 时间: {txtime}**
    * **操作类型：** （列出1个操作标签，例如"卖出代币 (Swap)"； "授权 (Approve)"，"撤出流动性"，等等）
    * **行为分析：** （用2-3句具体描述链上行为，必须包含主要代币数量、兑换/转移路径、核心协议或地址的角色，并点明用户的最终意图。）
    * **Gas费用：** （列出本次交易的 gasUsed、gasPrice 与 txFee；若缺失则说明原因。）
- 禁止输出笼统描述或遗漏关键数据，必要时可结合 `internalTransactions` 辅助推断。
"""

def analyze_transaction(transaction_summary: dict) -> dict:
    """
    让AI分析一笔交易，看看这笔交易到底做了什么
    
    具体做什么：
    1. 把交易数据整理好，发给AI
    2. 告诉AI要分析什么（交易数据、分析规则等）
    3. AI分析完后，把结果解析出来
    4. 返回分析结果
    
    需要什么：
        transaction_summary: 一笔交易的完整数据（包括哈希、时间、地址、转账等）
    
    给你什么：
        一个字典，里面有个"analysis"字段，是AI写的分析文字
    
    如果AI调用失败了：
        会返回一个包含错误信息的字典，但不会让程序崩溃
    """
    # 提取交易哈希（用于Prompt和错误处理）
    tx_hash = transaction_summary.get('txhash', 'unknown')
    
    try:
        # ========== 准备Prompt ==========
        # 提取交易时间
        tx_time = transaction_summary.get('txTime', '未知时间')
        # 将交易摘要格式化为JSON字符串（缩进2，保留中文字符）
        tx_data_str = json.dumps(transaction_summary, indent=2, ensure_ascii=False)
        
        # 使用Prompt模板构建完整的Prompt
        # 将交易数据、哈希、时间填入模板
        prompt = PROMPT_TEMPLATE.format(
            transaction_data=tx_data_str,
            txhash=tx_hash,
            txtime=tx_time
        )

        # ========== 调用AI API ==========
        # 使用OpenAI兼容的API调用AI模型
        response = client.chat.completions.create(
            model=MODEL,  # 使用的AI模型
            messages=[
                # System消息：定义AI的角色和行为
                {"role": "system", "content": "你是专业的链上交易分析师。你必须返回仅包含 'analysis' 字段的JSON，其中 analysis 为中文Markdown，包含交易哈希、操作类型、行为分析以及Gas费用，避免笼统描述或缺少关键数据。"},
                # User消息：包含具体的分析任务和数据
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},  # 要求返回JSON格式
            temperature=1,  # 温度参数：1表示较低的随机性，获得更稳定详尽的输出
        )
        
        # ========== 提取AI响应 ==========
        # 从响应中提取AI生成的内容
        ai_response_str = response.choices[0].message.content
        
        # ========== 解析JSON结果 ==========
        try:
            # 将AI返回的JSON字符串解析为Python字典
            analysis_result = json.loads(ai_response_str)
            return analysis_result
        except json.JSONDecodeError as json_err:
            # 如果JSON解析失败，返回包含原始响应的错误信息
            # 只显示前200个字符，避免错误信息过长
            return {"analysis": f"AI返回了无效的JSON格式。原始响应: {ai_response_str[:200]}"}

    except Exception as e:
        # ========== 错误处理 ==========
        # 如果AI分析失败（API错误、网络错误等），返回包含错误信息的字典
        # 这样可以避免整个分析流程中断
        return {"analysis": f"AI analysis failed: {str(e)}"}
