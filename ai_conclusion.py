"""
文件名称: ai_conclusion.py
文件用途: AI总结和对话模块，负责生成综合分析报告和管理对话会话

主要功能:
    1. generate_conclusion(): 生成最终的地址行为总结报告
       - 汇总所有单笔交易的AI分析结果
       - 生成用户画像和行为总结
       - 包含专业分析和大白话解读两部分
    
    2. chat_with_report(): 基于报告进行对话
       - 处理用户提问
       - 基于报告和分析摘要生成回答
       - 支持对话历史

AI模型配置:
    - 服务提供商: OpenRouter
    - 模型: google/gemini-2.5-flash-preview-09-2025（Gemini模型）
    - 用途: 总结报告生成和对话（与单笔交易分析使用不同的模型）

报告结构:
    报告包含以下部分：
    1. 核心用户画像：身份标签和行为依据
    2. 主要操作模式：常见的操作类型和交互协议
    3. 资产偏好与策略：资产类别和投资策略
    4. 行为模式总结：交易频率、活跃时间、规模等

报告特点:
    - 每个部分都包含"专业分析"和"大白话解读"
    - 专业分析：客观、数据驱动，使用行业术语
    - 大白话解读：通俗易懂，帮助非专业用户理解

对话功能:
    - 基于已生成的报告和分析摘要
    - 支持多轮对话
    - 每次回答都包含完整的上下文（报告+分析摘要+历史对话）

依赖库:
    - openai: OpenAI Python客户端（兼容OpenRouter）

作者: AI链上分析器开发团队
创建日期: 2025-11-01
"""

import os
import streamlit as st
from openai import OpenAI

# ========== AI客户端配置 ==========
# 注意：与 ai_client.py 使用相同的API Key，但使用不同的模型
# 总结报告使用Gemini模型，单笔交易分析使用GPT模型
MODEL = "google/gemini-3-pro-preview"  # Gemini模型，适合总结和对话

# 延迟初始化客户端，在函数调用时再读取 secrets
_client = None

def get_client():
    """获取 OpenAI 客户端实例（延迟初始化）"""
    global _client
    if _client:
        return _client
    
    try:
        api_key = st.secrets["OPENROUTER_API_KEY"]
    except (FileNotFoundError, KeyError, AttributeError):
        # 如果无法读取 secrets，尝试使用环境变量或抛出错误
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError("❌ 未找到 OPENROUTER_API_KEY！请在 .streamlit/secrets.toml 中配置。")
    
    _client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "AI On-Chain Analyzer"
        },
    )
    return _client

# ========== 总结报告Prompt模板 ==========
# 这个Prompt用于生成最终的地址行为总结报告
CONCLUSION_PROMPT_TEMPLATE = """
你是一名拥有10年经验的资深链上侦探和加密货币分析师。
你的任务是基于以下单笔交易的分析摘要，为地址 {address} 生成一份深度行为画像报告。

**核心目标：** 透过交易数据，看穿该地址背后的"人"是谁，他在做什么，以及他的水平如何。

**交易分析摘要:**
{analyses_summary}

**请严格按照以下 Markdown 结构输出报告（不要输出任何开场白）：**

### 🕵️‍♂️ 链上深度画像：{address}

#### 1. 核心身份与评级
*   **身份标签**： (例如：资深 DeFi 玩家 / 空投猎人 / 交易所且大户 / 甚至可能是黑客/诈骗者。**请大胆推断**)
*   **操作段位**： (青铜 / 黄金 / 钻石 / 王者。根据交互协议的复杂度和资金规模判断)
*   **大白话人设**： (用一句生动的话描述他，例如："这就是个典型的冲土狗亏钱的散户" 或 "这是一个极度精明、只在头部协议挖矿的大鲸鱼"。)

#### 2. 资金与策略分析
*   **资金流向图谱**：
    *   **主要来源**： (钱从哪来？CEX 提币？挖矿收益？还是其他钱包转入？)
    *   **主要去向**： (钱去了哪？囤币？提供流动性？还是转回交易所套现？)
*   **核心策略拆解**：
    *   (详细分析他的盈利模式。例如：他似乎在通过 Aave 循环借贷做多 ETH；或者他专注于在 Uniswap 上通过极窄的区间提供流动性赚取手续费。)

#### 3. 行为模式与习惯
*   **活跃特征**： (高频/低频？喜欢在深夜操作？是否对 Gas 费敏感？)
*   **交互偏好**： (偏好头部安全协议，还是喜欢尝试高风险的新盘子？)

#### 4. ⚠️ 风险与安全评估
*   **潜在风险**： (是否存在高风险操作？例如：授权给了不明合约、频繁交互类似钓鱼网站的地址。)
*   **侦探建议**： (如果你是他的顾问，你会给他什么建议？)

---
**分析要求：**
1.  **拒绝流水账**：不要罗列"他买了这个，他又卖了那个"。请告诉我**"他为什么这么做"**。
2.  **利用知识库**：你必须识别出 Uniswap, Aave, Curve, Blur, Opensea 等协议，并知道它们是干什么的。
3.  **数据支撑**：在下结论时，尽量引用摘要中的数据（如交易金额、具体代币）作为证据。
"""

def generate_conclusion(address: str, analyses: list[str]) -> str:
    """
    根据所有交易的AI分析结果，生成最终的地址行为总结报告。
    
    这个函数汇总所有单笔交易的AI分析，生成一份综合的用户画像和行为总结。
    报告包含专业分析和大白话解读，既满足专业用户需求，也便于非专业用户理解。
    
    参数:
        address: 用户查询的地址（用于报告标题）
        analyses: 包含所有单笔交易ai_analysis字段内容的列表
                  每个元素是一个Markdown格式的分析文本
    
    返回:
        AI生成的Markdown格式总结报告字符串
    
    报告生成流程:
        1. 检查是否有足够的分析数据
        2. 将所有分析摘要用分隔符连接
        3. 构建Prompt（包含地址和分析摘要）
        4. 调用AI生成报告
        5. 返回报告文本
    
    AI模型配置:
        - 使用Gemini模型（适合总结和生成长文本）
        - Temperature设置为0.3（较低，确保输出稳定）
    
    报告特点:
        - 包含4个主要部分：用户画像、操作模式、资产偏好、行为模式
        - 每个部分都有专业分析和大白话解读
        - 基于实际交易数据，避免过度猜测
    """
    # 如果没有分析数据，返回提示信息
    if not analyses:
        return f"地址 {address} 没有足够的数据生成总结报告。"

    # ========== 准备分析摘要 ==========
    # 将所有单笔交易的分析结果用分隔符连接
    # 这样AI可以看到所有交易的分析，进行综合总结
    analyses_summary = "\n\n---\n\n".join(analyses)

    # ========== 构建Prompt ==========
    # 将地址和分析摘要填入Prompt模板
    prompt = CONCLUSION_PROMPT_TEMPLATE.format(
        address=address,
        analyses_summary=analyses_summary
    )

    try:
        # ========== 调用AI生成报告 ==========
        # 获取客户端（延迟初始化，确保 secrets 已加载）
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL,  # 使用Gemini模型
            messages=[
                # System消息：定义AI的角色和输出格式要求
                {"role": "system", "content": "你是一名专业的链上分析师，擅长将复杂的链上行为用清晰、易懂的语言解读。你的分析需要既保持专业性，又要让非专业人士能轻松理解。请严格按照用户指定的Markdown结构输出报告。"},
                # User消息：包含具体的总结任务和数据
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,  # 较低的温度，确保输出稳定一致
        )
        
        # ========== 提取并返回报告 ==========
        conclusion_report = response.choices[0].message.content
        return conclusion_report

    except Exception as e:
        # ========== 错误处理 ==========
        # 如果生成报告失败，返回错误信息
        return f"生成最终总结报告时出错: {str(e)}"

# ========== 对话Prompt模板 ==========
# 这个Prompt用于基于报告进行对话
CHAT_PROMPT_TEMPLATE = """
你是一个专业的链上分析AI助手。
你已经为地址 {address} 生成了一份总结报告。现在，用户将基于这份报告和原始的交易分析数据向你提问。

**核心上下文 - 总结报告:**
---
{report}
---

**原始数据 - 单笔交易分析摘要:**
---
{analyses_summary}
---

请遵循以下规则回答用户的问题:
1.  你的回答必须严格基于上面提供的"总结报告"和"单笔交易分析摘要"。
2.  不要杜撰任何报告中不存在的信息。如果问题的答案在上下文中找不到，请明确告知用户"根据现有信息，我无法回答这个问题"。
3.  保持回答简洁、直接。
"""

def chat_with_report(address: str, report: str, analyses_summary: str, history: list, user_query: str) -> str:
    """
    基于已生成的报告和分析数据，处理用户的追问。
    
    这个函数实现对话功能，允许用户就报告和数据提问。
    AI会基于报告、分析摘要和历史对话生成回答。
    
    参数:
        address: 被分析的地址（用于上下文）
        report: 已生成的总结报告（核心上下文）
        analyses_summary: 所有单笔交易分析的字符串集合（原始数据上下文）
        history: 对话历史（之前的问答记录）
        user_query: 用户的新问题
    
    返回:
        AI的回答（字符串）
    
    对话机制:
        - 每次调用都包含完整的上下文（报告+分析摘要）
        - 支持多轮对话（通过history参数）
        - AI只能基于提供的上下文回答，不能杜撰信息
    
    技术实现:
        - 构建包含完整上下文的system prompt
        - 将历史对话和当前问题添加到消息列表
        - 调用AI生成回答
    """
    # ========== 构建系统提示 ==========
    # 每次都构建包含完整上下文的系统提示
    # 这样AI可以基于报告和分析摘要回答问题
    system_prompt = CHAT_PROMPT_TEMPLATE.format(
        address=address,
        report=report,
        analyses_summary=analyses_summary
    )

    # ========== 构造消息列表 ==========
    # 消息列表包含：
    # 1. System消息：包含报告和分析摘要（上下文）
    # 2. 历史对话：之前的问答记录
    # 3. 当前问题：用户的新问题
    messages_for_api = [
        {"role": "system", "content": system_prompt}
    ] + history + [{"role": "user", "content": user_query}]


    try:
        # ========== 调用AI生成回答 ==========
        # 获取客户端（延迟初始化，确保 secrets 已加载）
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL,  # 使用Gemini模型
            messages=messages_for_api,  # 包含完整上下文和历史的消息列表
            temperature=0.5,  # 中等温度，平衡创造性和准确性
        )
        
        # ========== 提取并返回回答 ==========
        ai_response = response.choices[0].message.content
        return ai_response

    except Exception as e:
        # ========== 错误处理 ==========
        # 如果对话失败，返回错误信息
        error_message = f"对话时出错: {str(e)}"
        return error_message
